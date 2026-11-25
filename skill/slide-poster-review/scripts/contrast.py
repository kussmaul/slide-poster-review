"""Rate text contrast against its rendered background (WCAG 1.4.3; rubric items CT-1 and CT-2).

Usage:
    python scripts/contrast.py OUTPUT_DIR [--preset NAME] [--kind slides|poster]
                               [--print-size 48x36in]

Needs manifest.json, text.json, and pages/*.png (render.py, extract_text.py). Writes
OUTPUT_DIR/contrast.json with the same layout as font_size.json (items, findings, notices, units).

For each text run, the text color comes from the PDF. The background is sampled from the rendered
page inside the run's box, leaving out the glyph pixels. Over images or gradients there is no
single background, so the near-worst case is used: the 10th percentile of contrast across the
background pixels. Such runs are flagged as "over an image, gradient, or other text" (medium
confidence); overlapping text, e.g. a line that overflows into the footer, shows up this way too.
Ratios are WCAG 2.x contrast ratios, compared unrounded (4.49:1 fails 4.5:1) and shown
truncated to 2 decimals.

Levels:          normal text           large text
  Level 4        7:1 or more (AAA)     4.5:1 or more
  Level 3        4.5:1 or more (AA)    3:1 or more
  Level 2        3:1 or more           -
  Level 1        less than 3:1         less than 3:1
"Large" follows WCAG's 18 pt (14 pt bold), converted to a visual angle so it means the same on
slides and posters: cap height 21.5' (16.7' bold) at the preset's viewing distance.
Roles (body vs. supporting) and units (slides, or text blocks on posters) match font_size.py.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import font_size as fs  # noqa: E402  (shared presets, roles, kinds, geometry)

LARGE_ARCMIN, LARGE_BOLD_ARCMIN = 21.5, 16.7
TEXT_MATCH = 80          # RGB distance: a pixel this close to the text color may be a glyph pixel
MIN_GLYPH_SHARE = 0.003  # below this share of glyph-like pixels, the text isn't visible as specified
COMPLEX_LUM_STD = 0.04   # background luminance spread above this = image or gradient
GLYPH_MARGIN = 2         # px around glyphs left out of the background (anti-aliasing)
GLYPH_MATCH = 40         # RGB distance: glyph core pixels are this close to the text colour


# ---------- colour math ----------

def rel_luminance(rgb: np.ndarray) -> np.ndarray:
    """WCAG 2.x relative luminance of sRGB values 0-255 (any shape ... x 3)."""
    c = rgb.astype(float) / 255.0
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return c[..., 0] * 0.2126 + c[..., 1] * 0.7152 + c[..., 2] * 0.0722


def contrast_ratio(l1, l2):
    hi, lo = np.maximum(l1, l2), np.minimum(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def show_ratio(r: float) -> str:
    """Truncate (never round up) to 2 decimals: 4.499 shows as 4.49."""
    return f"{math.floor(r * 100) / 100:.2f}:1"


def hex_rgb(h: str) -> np.ndarray:
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], dtype=float)


def rgb_hex(c) -> str:
    return "#" + "".join(f"{int(round(v)):02x}" for v in c)


def level_for(ratio: float, large: bool) -> int:
    if large:
        return 4 if ratio >= 4.5 else 3 if ratio >= 3 else 1
    return 4 if ratio >= 7 else 3 if ratio >= 4.5 else 2 if ratio >= 3 else 1


# ---------- sampling ----------

def load_page(path: Path) -> np.ndarray:
    pix = pymupdf.Pixmap(str(path))
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    return arr[..., :3].astype(np.int16)


def sample_span(img: np.ndarray, bbox_px: tuple, fg: np.ndarray, alpha: float,
                percentile: float = 10) -> dict | None:
    """Contrast of one text run, or None if its box is empty. `percentile` of the per-pixel
    ratios: 10 = near-worst case (PDF text); 50 = typical (OCR boxes, which also catch nearby
    lines and graphics)."""
    h, w = img.shape[:2]
    x0, y0, x1, y1 = (int(math.floor(bbox_px[0])), int(math.floor(bbox_px[1])),
                      int(math.ceil(bbox_px[2])), int(math.ceil(bbox_px[3])))
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    region = img[y0:y1, x0:x1].astype(float)
    px = region.reshape(-1, 3)
    d = np.sqrt(((px - fg) ** 2).sum(axis=1))
    far = px[d >= 40]
    if len(far) == 0:  # everything is text-colored: text on a same-colored background
        bg = px
        mode = fg
    else:
        q = (far // 8).astype(int)
        keys, counts = np.unique(q[:, 0] * 1024 + q[:, 1] * 32 + q[:, 2], return_counts=True)
        k = keys[counts.argmax()]
        mode = far[(q[:, 0] * 1024 + q[:, 1] * 32 + q[:, 2]) == k].mean(axis=0)
        d_mode = np.sqrt(((mode - fg) ** 2).sum())
        # Glyph pixels, grown by GLYPH_MARGIN px so anti-aliased edges aren't taken as background.
        # Only near-exact matches count as glyph cores, so a background close to the text colour
        # (the low-contrast case) stays in the sample; the margin covers anti-aliasing.
        glyph = (d < min(GLYPH_MATCH, 0.5 * d_mode)).reshape(region.shape[:2])
        grown = glyph.copy()
        for dy in range(-GLYPH_MARGIN, GLYPH_MARGIN + 1):
            for dx in range(-GLYPH_MARGIN, GLYPH_MARGIN + 1):
                grown |= np.roll(np.roll(glyph, dy, axis=0), dx, axis=1)
        bg = px[~grown.reshape(-1)]
        if len(bg) < 0.05 * len(px):  # dense text: fall back to the colour cut alone
            bg = px[d >= 0.9 * d_mode]
        if len(bg) == 0:
            bg = mode[None, :]
    eff_fg = fg if alpha >= 1 else alpha * fg + (1 - alpha) * mode
    glyph_share = float((d < TEXT_MATCH).mean()) if alpha >= 1 else 1.0
    lum_bg = rel_luminance(bg)
    ratios = contrast_ratio(rel_luminance(eff_fg), lum_bg)
    return {
        "ratio": float(np.percentile(ratios, percentile)),
        "fg": rgb_hex(eff_fg), "bg": rgb_hex(mode),
        "complex_bg": bool(lum_bg.std() > COMPLEX_LUM_STD),
        "visible": glyph_share >= MIN_GLYPH_SHARE,
    }


def infer_text_color(img: np.ndarray, box: tuple) -> np.ndarray | None:
    """Text colour inside an OCR word box: the minority side of a luminance split (Otsu)."""
    h, w = img.shape[:2]
    x0, y0 = max(0, int(box[0])), max(0, int(box[1]))
    x1, y1 = min(w, int(math.ceil(box[2]))), min(h, int(math.ceil(box[3])))
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    px = img[y0:y1, x0:x1].reshape(-1, 3).astype(float)
    lum = rel_luminance(px)
    hist, edges = np.histogram(lum, bins=64, range=(0, 1))
    total, best, thr = lum.size, -1.0, 0.5
    cum, cum_mean, mean_all = 0, 0.0, (hist * (edges[:-1] + edges[1:]) / 2).sum()
    for i in range(63):
        cum += hist[i]
        cum_mean += hist[i] * (edges[i] + edges[i + 1]) / 2
        if cum == 0 or cum == total:
            continue
        m0, m1 = cum_mean / cum, (mean_all - cum_mean) / (total - cum)
        between = cum * (total - cum) * (m0 - m1) ** 2
        if between > best:
            best, thr = between, edges[i + 1]
    dark, light = px[lum < thr], px[lum >= thr]
    if len(dark) == 0 or len(light) == 0:
        return None
    text = dark if len(dark) < len(light) else light
    # Use the most extreme half of the text side, so anti-aliased edges don't dilute the colour.
    tl = rel_luminance(text)
    core = text[tl <= np.median(tl)] if text is dark else text[tl >= np.median(tl)]
    return core.mean(axis=0)


# ---------- measurement ----------

def measure(out_dir: Path, preset_name: str | None = None, kind: str | None = None,
            print_size: str | None = None) -> Path:
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    text = json.loads((out_dir / "text.json").read_text(encoding="utf-8"))
    kind = kind or manifest["kind_guess"]
    presets = fs.load_presets()
    preset = presets[preset_name] if preset_name else next(
        p for p in presets.values() if p["kind"] == kind and p["default"])
    m_per_pt = 0.0254 / 72
    if kind == "poster" and print_size:
        pw, ph = fs.parse_print_size(print_size)
        w, h = manifest["pages"][0]["width_pt"], manifest["pages"][0]["height_pt"]
        m_per_pt = (max(pw, ph) if h > w else min(pw, ph)) / h
    fs.assign_roles(text["pages"], kind)
    fs.assign_kinds(text["pages"], text.get("pptx"))
    fonts = text["fonts"]
    mpages = {p["index"]: p for p in manifest["pages"]}

    units, unverified = [], []
    ocr = fs.load_ocr(out_dir)
    crops: dict = {}  # rotated OCR crops, loaded on demand
    for p in text["pages"]:
        mp = mpages[p["index"]]
        img = load_page(out_dir / mp["image"])
        sx, sy = mp["px_per_pt_x"], mp["px_per_pt_y"]
        groups: dict = defaultdict(list)
        for s in p["spans"]:
            if not re.search(r"\w", s["text"]):
                continue
            cap_em = fonts.get(s["font"], {}).get("cap_height_em") or fs.DEFAULT_CAP_EM
            cap_pt = s["size_pt"] * cap_em
            angle = (fs.cap_angle_arcmin(cap_pt / p["height_pt"], preset["distance"]) if kind == "slides"
                     else fs.cap_angle_arcmin(cap_pt * m_per_pt, preset["distance"]))
            if angle < fs.INVISIBLE_ARCMIN:
                continue  # too small to see; reported by font_size (FS-TINY)
            b = list(s["bbox"])
            if s.get("dir", [1, 0]) == [1.0, 0.0]:
                # Horizontal text: sample only the band from baseline to cap height (plus a little),
                # so descenders and neighbouring lines don't count as background.
                base = s["origin"][1]
                b[1] = max(b[1], base - cap_pt * 1.15)
                b[3] = min(b[3], base + s["size_pt"] * 0.05)
            r = sample_span(img, (b[0] * sx, b[1] * sy, b[2] * sx, b[3] * sy),
                            hex_rgb(s["color"]), s.get("alpha", 255) / 255)
            if r is None:
                continue
            if not r["visible"]:
                unverified.append((p["index"], s["text"].strip()[:40]))
                continue
            large = angle >= (LARGE_BOLD_ARCMIN if s.get("bold") else LARGE_ARCMIN)
            rec = {"text": s["text"].strip()[:80], "ratio": round(r["ratio"], 4), "fg": r["fg"],
                   "bg": r["bg"], "complex_bg": r["complex_bg"], "large": large,
                   "level": level_for(r["ratio"], large), "role": s["role"], "kind": s["kind"],
                   "reason": s["role_reason"]}
            groups[p["index"] if kind == "slides" else (p["index"], s["block"])].append(rec)
        for line in fs.ocr_lines(ocr, p["index"]):
            ratios, last = [], None
            for w in line["words"]:
                src = img if w["image"] == mp["image"] else crops.setdefault(
                    w["image"], load_page(out_dir / w["image"]))
                x, y, ww, hh = w["box_px"]
                fg = infer_text_color(src, (x, y, x + ww, y + hh))
                if fg is None:
                    continue
                r = sample_span(src, (x, y, x + ww, y + hh), fg, 1.0, percentile=50)
                if r and r["visible"]:
                    ratios.append(r["ratio"])
                    last = r
            if not ratios:
                continue
            ratio = sorted(ratios)[len(ratios) // 2]
            cap_pt = line["cap_pt"]
            angle = (fs.cap_angle_arcmin(cap_pt / p["height_pt"], preset["distance"]) if kind == "slides"
                     else fs.cap_angle_arcmin(cap_pt * m_per_pt, preset["distance"]))
            large = angle >= LARGE_ARCMIN
            rec = {"text": line["text"][:80], "ratio": round(ratio, 4), "fg": last["fg"], "bg": last["bg"],
                   "complex_bg": last["complex_bg"], "large": large, "level": level_for(ratio, large),
                   "role": "body", "kind": "image text", "reason": None, "ocr": True}
            groups[p["index"] if kind == "slides" else (p["index"], f"ocr-{line['region']}")].append(rec)
        for key, recs in groups.items():
            unit = {"page": p["index"], "hidden": mp["hidden"]}
            if kind == "poster":
                unit["block"] = key[1]
            for role in ("body", "supporting"):
                rs = [r for r in recs if r["role"] == role]
                if rs:
                    worst = min(rs, key=lambda r: (r["level"], r["ratio"]))
                    unit[role] = {"level": worst["level"], "worst": worst, "spans": len(rs)}
            units.append(unit)

    items, findings = {}, []
    unit_word = ("slide", "slides") if kind == "slides" else ("text block", "text blocks")
    for item_id, role, label in (("CT-1", "body", "body text"), ("CT-2", "supporting", "supporting text")):
        scored = [u for u in units if role in u and not u["hidden"]]
        if not scored:
            items[item_id] = {"role": role, "level": None, "units": 0}
            continue
        levels = sorted(u[role]["level"] for u in scored)
        counts = Counter(levels)
        low = sorted((u for u in scored if u[role]["level"] < 3), key=lambda u: u[role]["worst"]["ratio"])
        n_complex = sum(u[role]["worst"]["complex_bg"] for u in low)
        n_ocr = sum(bool(u[role]["worst"].get("ocr")) for u in low)
        n_complex -= sum(bool(u[role]["worst"].get("ocr") and u[role]["worst"]["complex_bg"]) for u in low)
        confidence = "high" if not (n_complex or n_ocr) else "medium"
        items[item_id] = {"role": role, "level": levels[int(fs.ITEM_PERCENTILE * len(levels))],
                          "units": len(scored), "confidence": confidence,
                          "level_counts": {f"L{k}": counts.get(k, 0) for k in (1, 2, 3, 4)}}
        if not low:
            continue
        worst = low[0][role]["worst"]
        where = [str(u["page"]) if kind == "slides" else f'poster {u["page"]}' for u in low]
        sample = list(dict.fromkeys(where))[:3]
        if kind == "slides":
            sample.sort(key=int)
        if role == "body":
            kc = Counter(fs.KIND_PLURAL[u[role]["worst"]["kind"]] for u in low)
        else:
            kc = Counter(f'{u[role]["worst"]["reason"]}s' for u in low)
        what = ", ".join(f"{k} ({n} {unit_word[n != 1]})" if i == 0 else f"{k} ({n})"
                         for i, (k, n) in enumerate(kc.most_common()))
        n_low = len(low)
        headline = (f"{n_low} {unit_word[n_low != 1]} {'has' if n_low == 1 else 'have'} {label} "
                    f"with contrast below 4.5:1 (3:1 for large text).")
        details = (f"Lowest contrast is in {what}. For example: "
                   f"{('slide ' if len(sample) == 1 else 'slides ') if kind == 'slides' else ''}{', '.join(sample)}. Lowest: "
                   + (f"about {show_ratio(worst['ratio'])}, text in an image or shape" if worst.get("ocr")
                      else f"{show_ratio(worst['ratio'])}, {worst['fg']} on {worst['bg']}")
                   + f" (\"{worst['text'][:40]}\").")
        if n_complex:
            details += (f" {n_complex} of these {'is' if n_complex == 1 else 'are'} text over an "
                        "image, gradient, or other text.")
        findings.append({"id": item_id, "level": min(u[role]["level"] for u in low), "count": n_low,
                         "confidence": confidence, "headline": headline, "details": details,
                         "summary": f"{item_id}: {headline} {details}",
                         "units": [u["page"] if kind == "slides" else [u["page"], u["block"]] for u in low]})
    findings.sort(key=lambda f: (f["level"], -f["count"]))

    notices = []
    if unverified:
        pages = sorted({u[0] for u in unverified})
        notices.append({"code": "CT-UNVERIFIED", "level": "info",
                        "message": f"{len(unverified)} text runs couldn't be found in the rendered page in "
                                   f"their stated color (e.g. \"{unverified[0][1]}\"), so their contrast "
                                   f"wasn't measured. They may be covered by another object, or drawn "
                                   f"with effects such as gradients or outlines. Pages: "
                                   f"{', '.join(map(str, pages[:8]))}{'…' if len(pages) > 8 else ''}.",
                        "advice": "Check these by eye."})
    result = {"measure": "contrast", "kind": kind, "preset": preset, "print_size": print_size,
              "large_arcmin": [LARGE_ARCMIN, LARGE_BOLD_ARCMIN],
              "items": items, "findings": findings, "notices": notices, "units": units}
    path = out_dir / "contrast.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--preset")
    ap.add_argument("--kind", choices=["slides", "poster"])
    ap.add_argument("--print-size")
    a = ap.parse_args(argv)
    try:
        path = measure(a.out_dir, a.preset, a.kind, a.print_size)
    except (ValueError, KeyError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    res = json.loads(path.read_text(encoding="utf-8"))
    for iid, it in res["items"].items():
        print(f"{iid} ({it['role']}): level {it['level']}  {it.get('level_counts', '')}")
    for f in res["findings"]:
        print(f["summary"])
    for n in res["notices"]:
        print(f"[{n['level']}] {n['code']}: {n['message']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
