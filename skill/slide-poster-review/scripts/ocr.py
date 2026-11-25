"""Find text that the PDF doesn't store as text: inside images, or drawn as shapes (OCR).

Usage:
    python scripts/ocr.py OUTPUT_DIR [--force]

Needs manifest.json, text.json, pages/*.png. Writes OUTPUT_DIR/ocr.json (and OUTPUT_DIR/ocr/ for
rotated crops), which font_size.py and contrast.py read. Reuses an earlier ocr.json for the same
render unless --force.

Engine: Windows' built-in OCR (scripts/ocr_win.ps1). Where it isn't available, ocr.json says so
and the review continues without it.

Pass 1   OCR every page image. Words that overlap text the PDF already has are dropped; the rest
         are text inside images or drawn as shapes.
Pass 2   Text drawn as shapes at an angle (e.g. rotated chart axis labels) isn't read by pass 1.
         Find clusters of small glyph-like filled shapes with no OCR words, render each cluster
         rotated by +-45 and +-90 degrees, OCR again, and keep the best rotation.
Unread   Clusters still unread are listed as "possible text not read".

Each word gets a cap-height estimate in PDF points (cap_pt) from its box height: words with
capitals, digits, or ascenders but no descenders are about cap height; others are scaled.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pymupdf

SCRIPTS = Path(__file__).resolve().parent
OCR_VERSION = 2
ROTATIONS = (45, -45, 90, -90)
ROT_ZOOM = 4.0           # render rotated crops at 288 dpi
DESCENDERS = set("gjpqy,;")
TALL = re.compile(r"[A-Z0-9bdfhklt]")


# ---------- engine ----------

def ocr_available() -> bool:
    if os.name != "nt" or not shutil.which("powershell"):
        return False
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                        str(SCRIPTS / "ocr_win.ps1")], capture_output=True, text=True, timeout=60)
    return r.returncode == 0


def run_ocr(images: list[Path]) -> dict[str, list]:
    """{image path: lines}, each line a list of {text, x, y, w, h} in image pixels."""
    if not images:
        return {}
    with tempfile.TemporaryDirectory() as tmp:
        jobs, out = Path(tmp, "jobs.json"), Path(tmp, "out.json")
        jobs.write_text(json.dumps([str(Path(i).resolve()) for i in images]), encoding="utf-8")
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                            str(SCRIPTS / "ocr_win.ps1"), str(jobs), str(out)],
                           capture_output=True, text=True, timeout=1800)
        if r.returncode != 0 or not out.exists():
            raise RuntimeError(f"OCR failed: {r.stderr.strip()}")
        data = json.loads(out.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict):  # PowerShell unwraps one-element arrays
        data = [data]
    res = {}
    for item in data:
        lines = item.get("lines") or []
        if isinstance(lines, dict):
            lines = [[lines]]
        res[str(Path(item["image"]).resolve())] = [l if isinstance(l, list) else [l] for l in lines]
    return res


# ---------- helpers ----------

def cap_px(word: str, h: float) -> float:
    """Estimate cap height from an OCR word box height."""
    letters = [c for c in word if c.isalnum()]
    has_desc = any(c in DESCENDERS for c in word)
    has_tall = bool(TALL.search(word))
    if has_tall and not has_desc:
        return h * 0.95          # box = cap/ascender height
    if has_tall and has_desc:
        return h * 0.70          # box = ascender to descender
    if has_desc:
        return h * 0.95          # x-height to descender: about cap height
    return h * 1.40 if letters else h  # x-height only


WORDLIKE = re.compile(r"^[(\"'“‘]?([A-Z]?[a-z]{2,}|[A-Z]{2,}|\d[\d.,:%/–-]*)[)\"'”’.,:;!?%]*$")


def useful(text: str) -> bool:
    return sum(c.isalnum() for c in text) >= 2


def real_line(words: list[dict]) -> bool:
    """Keep an OCR line only if some word looks like a real word or number (drops image noise)."""
    return any(WORDLIKE.match(w["text"]) for w in words)


def region_of(box_pt: tuple, image_rects: list) -> str:
    """Which picture on the page a word is in: 'img<k>', or 'page' if none."""
    cx, cy = (box_pt[0] + box_pt[2]) / 2, (box_pt[1] + box_pt[3]) / 2
    for k, r in enumerate(image_rects):
        if r[0] <= cx <= r[2] and r[1] <= cy <= r[3]:
            return f"img{k}"
    return "page"


def _overlaps(box: tuple, rects: list) -> bool:
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return any(r[0] - 2 <= cx <= r[2] + 2 and r[1] - 2 <= cy <= r[3] + 2 for r in rects)


def glyph_clusters(page: pymupdf.Page) -> list[pymupdf.Rect]:
    """Regions with >= 3 small glyph-like filled shapes: likely text drawn as outlines."""
    W, H = page.rect.width, page.rect.height
    rects = [g["rect"] for g in page.get_drawings()
             if g.get("type") == "f" and len(g["items"]) >= 8
             and 0.005 * H < g["rect"].height <= 0.05 * H and g["rect"].width <= 0.3 * W]
    clusters: list[list[pymupdf.Rect]] = []
    for r in rects:
        grown = pymupdf.Rect(r.x0 - r.height, r.y0 - r.height, r.x1 + r.height, r.y1 + r.height)
        hit = [c for c in clusters if any(grown.intersects(m) for m in c)]
        merged = [r] + [m for c in hit for m in c]
        clusters = [c for c in clusters if c not in hit] + [merged]
    out = []
    for c in clusters:
        if len(c) >= 3:
            u = pymupdf.Rect(c[0])
            for m in c[1:]:
                u |= m
            out.append(u)
    return out


# ---------- main ----------

def run(out_dir: Path, force: bool = False) -> Path:
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    path = out_dir / "ocr.json"
    if not force and path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        if old.get("cache_key") == manifest.get("cache_key") and old.get("ocr_version") == OCR_VERSION:
            return path
    result = {"cache_key": manifest.get("cache_key"), "ocr_version": OCR_VERSION,
              "engine": "windows", "available": False, "words": [], "unread": []}
    if not ocr_available():
        path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return path
    result["available"] = True
    text = json.loads((out_dir / "text.json").read_text(encoding="utf-8"))
    doc = pymupdf.open(out_dir / manifest["pdf"])
    pages = {p["index"]: p for p in manifest["pages"]}
    span_rects = {p["index"]: [s["bbox"] for s in p["spans"]] for p in text["pages"]}

    # Pass 1: whole pages.
    images = {i: (out_dir / p["image"]).resolve() for i, p in pages.items()}
    pass1 = run_ocr(list(images.values()))
    words = []
    for i, img in images.items():
        mp = pages[i]
        sx, sy = mp["px_per_pt_x"], mp["px_per_pt_y"]
        image_rects = [tuple(info["bbox"]) for info in doc[i - 1].get_image_info()]
        for li, line in enumerate(pass1.get(str(img), [])):
            kept = []
            for w in line:
                box_pt = (w["x"] / sx, w["y"] / sy, (w["x"] + w["w"]) / sx, (w["y"] + w["h"]) / sy)
                if not useful(w["text"]) or _overlaps(box_pt, span_rects.get(i, [])):
                    continue
                kept.append({"page": i, "text": w["text"], "image": mp["image"],
                             "box_px": [w["x"], w["y"], w["w"], w["h"]],
                             "bbox_pt": [round(v, 2) for v in box_pt], "rotation": 0, "line": li,
                             "region": region_of(box_pt, image_rects),
                             "cap_pt": round(cap_px(w["text"], w["h"]) / sy, 3)})
            if kept and real_line(kept):
                words += kept
            elif kept:
                result["dropped_noise"] = result.get("dropped_noise", 0) + 1

    # Pass 2: glyph-like clusters with no words, rotated.
    crops_dir = out_dir / "ocr"
    if crops_dir.exists():
        shutil.rmtree(crops_dir)
    jobs = []  # (page, cluster rect, rotation, png path)
    for i in pages:
        page = doc[i - 1]
        for c in glyph_clusters(page):
            crops_dir.mkdir(exist_ok=True)
            pad = c.height * 0.2
            clip = pymupdf.Rect(c.x0 - pad, c.y0 - pad, c.x1 + pad, c.y1 + pad) & page.rect
            for rot in ROTATIONS:
                png = crops_dir / f"p{i:03d}_{int(c.x0)}_{int(c.y0)}_r{rot:+d}.png"
                page.get_pixmap(matrix=pymupdf.Matrix(ROT_ZOOM, ROT_ZOOM).prerotate(rot),
                                clip=clip, alpha=False).save(png)
                jobs.append((i, clip, rot, png))
    pass2 = run_ocr([j[3] for j in jobs])
    by_cluster: dict = {}
    for i, clip, rot, png in jobs:
        lines = pass2.get(str(png.resolve()), [])
        found = [w for line in lines for w in line if useful(w["text"])]
        score = sum(sum(c.isalnum() for c in w["text"]) for w in found)
        key = (i, tuple(clip))
        if score > by_cluster.get(key, (-1,))[0]:
            by_cluster[key] = (score, rot, png, lines)
    for (i, clip), (score, rot, png, lines) in by_cluster.items():
        # Keep whichever reading of the cluster recognised more: upright (pass 1) or rotated.
        upright = [w for w in words if w["page"] == i and _overlaps(tuple(w["bbox_pt"]), [clip])]
        if score <= sum(sum(c.isalnum() for c in w["text"]) for w in upright):
            continue
        words = [w for w in words if w not in upright]
        if score < 4:
            result["unread"].append({"page": i, "bbox_pt": [round(v, 2) for v in clip]})
            continue
        for li, line in enumerate(lines):
            for w in line:
                if useful(w["text"]):
                    words.append({"page": i, "text": w["text"], "region": f"shapes{int(clip[0])}",
                                  "image": str(png.relative_to(out_dir)).replace("\\", "/"),
                                  "box_px": [w["x"], w["y"], w["w"], w["h"]],
                                  "bbox_pt": [round(v, 2) for v in clip], "rotation": rot,
                                  "line": 1000 + li,
                                  "cap_pt": round(cap_px(w["text"], w["h"]) / ROT_ZOOM, 3)})
    result["words"] = words
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    r = json.loads(run(a.out_dir, a.force).read_text(encoding="utf-8"))
    if not r["available"]:
        print("OCR not available; text in images was not checked.", file=sys.stderr)
        return 0
    rotated = sum(1 for w in r["words"] if w["rotation"])
    print(f"{len(r['words'])} words found in images or shapes ({rotated} rotated); "
          f"{len(r['unread'])} areas with possible text not read")
    return 0


if __name__ == "__main__":
    sys.exit(main())
