"""Rate text size by the visual angle of its cap height (rubric items FS-1 and FS-2).

Usage:
    python scripts/font_size.py OUTPUT_DIR [--preset NAME] [--kind slides|poster]
                                [--print-size 48x36in|120x90cm]

Needs OUTPUT_DIR/manifest.json and text.json (from render.py and extract_text.py).
Writes OUTPUT_DIR/font_size.json, which contains:
    preset, thresholds   which viewing preset and level bounds (arcmin) were used
    units                per slide (or per text block, for posters): level of each text role
    items                FS-1 body text, FS-2 supporting text; level 1-4 and confidence
    findings             one-line issues, e.g. "FS-1: 14 slides have body text below L3, e.g. 4, 9, 12"
    notices              limits of this measurement (e.g. assumed poster print size)

Angle: 2 * atan(cap / (2 * distance)), where cap = size_pt * cap_height_em.
  slides:  cap and distance are relative to the slide height (default preset: 8H).
  posters: cap is the printed size in metres (page size scaled to --print-size), distance in
           metres (default preset: 1.5 m).
cap_height_em comes from the font metrics in text.json. Without metrics it is 0.7 (DESIGN.md).

Text roles:
  body        everything else (titles, bullets, labels, chart text)
  supporting  footers (near the top/bottom edge and repeated across slides, or bare slide numbers),
              citations (URLs, doi:, "Source:", "(2014)"), and superscripts
Hidden slides are measured but not scored. Text inside images or drawn as outlines can't be
measured here (needs OCR).
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
DEFAULT_CAP_EM = 0.7
LEVEL_TOLERANCE = 0.01   # 39.96 pt counts as 40 pt: allow 1% below a bound
ITEM_PERCENTILE = 0.10   # item level = level reached by at least 90% of scored units
TARGET_LEVEL = 3         # findings list units below this level
INVISIBLE_ARCMIN = 1.0   # below this, text can't be seen at all: artifact, not scored (FS-TINY)
EDGE_TOP, EDGE_BOTTOM = 0.10, 0.88  # page-height fractions for header / footer bands
REPEAT_SHARE = 0.25      # a footer text repeats on at least this share of slides (min 3)
CITATION = re.compile(r"https?://|www\.|doi:|\b(source|image|photo|credit)s?:|\bet al\.|\((19|20)\d\d[a-z]?\)",
                      re.IGNORECASE)


# ---------- presets ----------

def load_presets(path: Path = SKILL / "rubrics" / "presets.md") -> dict[str, dict]:
    """Parse the markdown table in presets.md."""
    rows = [l for l in path.read_text(encoding="utf-8").splitlines() if l.startswith("|")]
    header = [c.strip() for c in rows[0].strip("|").split("|")]
    presets = {}
    for line in rows[2:]:
        r = dict(zip(header, (c.strip() for c in line.strip("|").split("|"))))
        dist = r["distance"]
        presets[r["preset"]] = {
            "name": r["preset"], "kind": r["kind"],
            "distance": float(dist.rstrip("Hh")), "distance_unit": "H" if dist[-1] in "Hh" else "m",
            "bounds": [float(r["L2"]), float(r["L3"]), float(r["L4"])],
            "default": r.get("default", "").lower() == "yes",
        }
    return presets


def parse_print_size(text: str) -> tuple[float, float]:
    """'48x36in' or '120x90cm' -> (width, height) in metres."""
    m = re.fullmatch(r"\s*([\d.]+)\s*[x×]\s*([\d.]+)\s*(in|cm|mm|m)\s*", text, re.IGNORECASE)
    if not m:
        raise ValueError(f"print size must look like 48x36in or 120x90cm, not {text!r}")
    scale = {"in": 0.0254, "cm": 0.01, "mm": 0.001, "m": 1.0}[m.group(3).lower()]
    return float(m.group(1)) * scale, float(m.group(2)) * scale


# ---------- geometry ----------

def cap_angle_arcmin(cap: float, distance: float) -> float:
    """Visual angle in arcminutes of an object of height `cap` at `distance` (same units)."""
    return math.degrees(2 * math.atan(cap / (2 * distance))) * 60


def level_for(angle: float, bounds: list[float]) -> int:
    lvl = 1
    for i, b in enumerate(bounds, start=2):
        if angle >= b * (1 - LEVEL_TOLERANCE):
            lvl = i
    return lvl


# ---------- roles ----------

def _norm_text(t: str) -> str:
    return re.sub(r"\d+", "#", t.strip().lower())


def assign_roles(pages: list[dict], kind: str) -> None:
    """Add 'role' ('body' or 'supporting') and 'role_reason' to every span."""
    n = len(pages)
    repeats: Counter = Counter()
    if kind == "slides" and n >= 3:
        for p in pages:
            H = p["height_pt"]
            seen = {_norm_text(s["text"]) for s in p["spans"]
                    if s["bbox"][1] >= EDGE_BOTTOM * H or s["bbox"][3] <= EDGE_TOP * H}
            repeats.update(seen)
    min_repeat = max(3, math.ceil(REPEAT_SHARE * n))
    for p in pages:
        H = p["height_pt"]
        for s in p["spans"]:
            text = s["text"].strip()
            in_band = s["bbox"][1] >= EDGE_BOTTOM * H or s["bbox"][3] <= EDGE_TOP * H
            reason = None
            if s.get("superscript"):
                reason = "superscript"
            elif kind == "slides" and in_band and (re.fullmatch(r"\d{1,3}", text)
                                                   or repeats[_norm_text(text)] >= min_repeat):
                reason = "footer"
            elif CITATION.search(text):
                reason = "citation"
            s["role"] = "supporting" if reason else "body"
            s["role_reason"] = reason


BULLET_START = re.compile(r"^\s*([●○■□◆◇▪▫•◦‣∙·–—\-*➢➤►▸✓✔]|\(?\d{1,2}[.)]|\(?[a-zA-Z][.)]\s)")
KIND_PLURAL = {"title": "titles", "bullet": "bullets", "sub-bullet": "sub-bullets",
               "chart/table": "chart/table text", "label": "short labels", "text": "other text"}
LABEL_WORDS = 5  # a block this short is a label (table cell, diagram or chart label)
KIND_PLURAL["image text"] = "text in images or shapes"


def load_ocr(out_dir: Path) -> dict:
    """ocr.json (from ocr.py) as {available, words_by_page, unread}; empty if OCR wasn't run."""
    try:
        r = json.loads((out_dir / "ocr.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"ran": False, "available": False, "words_by_page": {}, "unread": []}
    by_page: dict = defaultdict(list)
    for w in r["words"]:
        by_page[w["page"]].append(w)
    return {"ran": True, "available": r["available"], "words_by_page": by_page,
            "unread": r["unread"], "count": len(r["words"])}


def ocr_lines(ocr: dict, page: int) -> list[dict]:
    """OCR words on a page grouped into lines, each with its median cap height (robust to a
    single misread word)."""
    lines: dict = defaultdict(list)
    for w in ocr["words_by_page"].get(page, []):
        lines[(w.get("region", "page"), w["line"])].append(w)
    out = []
    for (region, _), ws in lines.items():
        caps = sorted(w["cap_pt"] for w in ws)
        out.append({"text": " ".join(w["text"] for w in ws), "cap_pt": caps[len(caps) // 2],
                    "region": region, "words": ws})
    return out


def ocr_notices(ocr: dict, unit: str) -> list[dict]:
    """Notices about text in images: what OCR found, what it couldn't read, or that it didn't run."""
    if not ocr["available"]:
        why = "OCR isn't available on this computer" if ocr["ran"] else "OCR wasn't run"
        return [{"code": "OCR-OFF", "level": "info",
                 "message": f"Text inside images and text drawn as shapes was not measured ({why}).",
                 "advice": "Check those by eye."}]
    out = []
    pages = sorted(ocr["words_by_page"])
    if pages:
        out.append({"code": "OCR-FOUND", "level": "info",
                    "message": f"{ocr['count']} words were found by OCR in images or shapes on {unit}s "
                               f"{', '.join(map(str, pages[:8]))}{'…' if len(pages) > 8 else ''}. "
                               "Their size and contrast are estimates (medium confidence).",
                    "advice": None})
    if ocr["unread"]:
        up = sorted({u["page"] for u in ocr["unread"]})
        out.append({"code": "OCR-UNREAD", "level": "warning",
                    "message": f"{len(ocr['unread'])} areas look like text drawn as shapes but couldn't be "
                               f"read, on {unit}s {', '.join(map(str, up[:8]))}.",
                    "advice": "Check these by eye; unreadable text may also be hard for viewers."})
    return out


def _ws(t: str) -> str:
    return " ".join(t.split()).lower()


def assign_kinds(pages: list[dict], pptx: dict | None) -> None:
    """Add 'kind' to every span: title, bullet, sub-bullet, chart/table, label, or text.

    title:        matches the PPTX title placeholder, or (no PPTX title) the largest text in the
                  top quarter of the page
    (sub-)bullet: lines starting with a bullet glyph or list number; indent rank 0 = bullet,
                  deeper = sub-bullet; wrapped lines inherit from the line above in the same block
    chart/table:  inside a PPTX chart or table frame
    label:        a whole text block of at most LABEL_WORDS words (table cells, diagram and
                  chart labels); not one of the above
    text:         anything else, e.g. paragraphs and their wrapped lines
    """
    slides = {s["index"]: s for s in (pptx or {}).get("slides", [])}
    for p in pages:
        W, H = p["width_pt"], p["height_pt"]
        sl = slides.get(p["index"], {})
        title = _ws(sl.get("title") or "")
        frames = [sh["bbox"] for sh in sl.get("shapes", [])
                  if sh.get("bbox") and sh.get("type") in ("CHART", "TABLE")]
        max_size = max((s["size_pt"] for s in p["spans"] if re.search(r"\w", s["text"])), default=0)

        # bullet lines and their indents
        lines: dict = defaultdict(list)
        for s in p["spans"]:
            lines[(s["block"], s["line"])].append(s)
        bullet_x = {}
        for key, spans in lines.items():
            first = min(spans, key=lambda s: s["bbox"][0])
            if BULLET_START.match(first["text"]):
                bullet_x[key] = first["bbox"][0]
        tol = 0.012 * W
        indents: list[float] = []
        for x in sorted(bullet_x.values()):
            if not indents or x - indents[-1] > tol:
                indents.append(x)

        def indent_rank(x: float) -> int:
            return min(range(len(indents)), key=lambda i: abs(indents[i] - x))

        block_words: Counter = Counter()
        for s in p["spans"]:
            block_words[s["block"]] += len(s["text"].split())
        prev_kind: dict = {}  # block -> kind of the last bullet line
        for key in sorted(lines):
            block = key[0]
            if key in bullet_x:
                line_kind = "bullet" if indent_rank(bullet_x[key]) == 0 else "sub-bullet"
                prev_kind[block] = line_kind
            else:
                line_kind = prev_kind.get(block)
            for s in lines[key]:
                text = _ws(s["text"])
                cx, cy = (s["bbox"][0] + s["bbox"][2]) / 2, (s["bbox"][1] + s["bbox"][3]) / 2
                if title and len(text) >= 3 and text in title:
                    k = "title"
                elif not title and s["bbox"][3] <= 0.25 * H and s["size_pt"] >= 0.99 * max_size:
                    k = "title"
                elif any(x0 <= cx <= x1 and y0 <= cy <= y1 for x0, y0, x1, y1 in frames):
                    k = "chart/table"
                elif line_kind:
                    k = line_kind
                elif block_words[block] <= LABEL_WORDS:
                    k = "label"
                else:
                    k = "text"
                s["kind"] = k


# ---------- measurement ----------

def measure(out_dir: Path, preset_name: str | None = None, kind: str | None = None,
            print_size: str | None = None) -> Path:
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    text = json.loads((out_dir / "text.json").read_text(encoding="utf-8"))
    kind = kind or manifest["kind_guess"]
    presets = load_presets()
    preset = presets[preset_name] if preset_name else next(p for p in presets.values() if p["kind"] == kind and p["default"])
    if preset["kind"] != kind:
        raise ValueError(f"preset {preset['name']} is for {preset['kind']}, not {kind}")
    bounds = preset["bounds"]
    notices = []

    # poster print scale: printed metres per PDF point
    m_per_pt = 0.0254 / 72
    if kind == "poster":
        page0 = manifest["pages"][0]
        if print_size:
            pw, ph = parse_print_size(print_size)
            w, h = page0["width_pt"], page0["height_pt"]
            if (pw > ph) != (w > h):
                pw, ph = ph, pw
            m_per_pt = ph / h
            if abs((pw / ph) / (w / h) - 1) > 0.02:
                notices.append({"code": "FS-ASPECT", "level": "warning",
                                "message": f"Print size {print_size} has a different shape than the "
                                           "page; scaled by height.", "advice": None})
        else:
            notices.append({"code": "FS-PRINT-SIZE", "level": "info",
                            "message": f"Print size not given, so the poster is assumed to print at "
                                       f"its page size ({page0['width_pt'] / 72:.0f} x "
                                       f"{page0['height_pt'] / 72:.0f} in).",
                            "advice": "Give the actual print size for accurate results."})

    fonts = text["fonts"]
    hidden = {p["index"]: p["hidden"] for p in manifest["pages"]}
    assign_roles(text["pages"], kind)
    assign_kinds(text["pages"], text.get("pptx"))
    substituted = manifest.get("fonts", {}).get("substituted") or []
    default_cap_spans = 0
    tiny: list[tuple] = []  # (page, text, size): too small to see at all

    ocr = load_ocr(out_dir)
    units = []  # slides: one per page; posters: one per text block
    for p in text["pages"]:
        groups: dict = defaultdict(list)
        for s in p["spans"]:
            if not re.search(r"\w", s["text"]):
                continue  # bullets, punctuation
            f = fonts.get(s["font"], {})
            cap_em = f.get("cap_height_em") or DEFAULT_CAP_EM
            if not f.get("cap_height_em"):
                default_cap_spans += 1
            cap_pt = s["size_pt"] * cap_em
            if kind == "slides":
                angle = cap_angle_arcmin(cap_pt / p["height_pt"], preset["distance"])
            else:
                angle = cap_angle_arcmin(cap_pt * m_per_pt, preset["distance"])
            if angle < INVISIBLE_ARCMIN:
                tiny.append((p["index"], s["text"].strip()[:40], s["size_pt"]))
                continue
            font = s["font"]
            if substituted and re.fullmatch(r"\d+(,\w+)?", font):
                # PowerPoint names substitute fonts "1", "2,Bold", ...
                font = f"substitute for {' / '.join(substituted)}"
            rec = {"text": s["text"].strip()[:80], "size_pt": s["size_pt"], "font": font,
                   "cap_em": round(cap_em, 3), "arcmin": round(angle, 2),
                   "level": level_for(angle, bounds), "role": s["role"], "reason": s["role_reason"],
                   "kind": s["kind"]}
            key = p["index"] if kind == "slides" else (p["index"], s["block"])
            groups[key].append(rec)
        for line in ocr_lines(ocr, p["index"]):
            cap_pt = line["cap_pt"]
            angle = (cap_angle_arcmin(cap_pt / p["height_pt"], preset["distance"]) if kind == "slides"
                     else cap_angle_arcmin(cap_pt * m_per_pt, preset["distance"]))
            if angle < INVISIBLE_ARCMIN:
                continue
            rec = {"text": line["text"][:80], "size_pt": round(cap_pt / DEFAULT_CAP_EM, 1),
                   "font": "text in image (OCR)", "cap_em": None, "arcmin": round(angle, 2),
                   "level": level_for(angle, bounds), "role": "body", "reason": None,
                   "kind": "image text", "ocr": True}
            # Posters: one unit per picture (or shape cluster), not per OCR line.
            key = p["index"] if kind == "slides" else (p["index"], f"ocr-{line['region']}")
            groups[key].append(rec)
        for key, recs in groups.items():
            unit = {"page": p["index"], "hidden": hidden.get(p["index"], False)}
            if kind == "poster":
                unit["block"] = key[1]
            for role in ("body", "supporting"):
                rs = [r for r in recs if r["role"] == role]
                if rs:
                    worst = min(rs, key=lambda r: r["arcmin"])
                    unit[role] = {"level": worst["level"], "smallest": worst, "spans": len(rs)}
            units.append(unit)

    items, findings = {}, []
    unit_word = ("slide", "slides") if kind == "slides" else ("text block", "text blocks")
    # Point size (at 0.7 em cap height) that reaches Level TARGET_LEVEL on these pages.
    comfy_cap = 2 * math.tan(math.radians(bounds[TARGET_LEVEL - 2] / 60) / 2) * preset["distance"]
    page_h = text["pages"][0]["height_pt"]
    comfy_pt = (comfy_cap * page_h if kind == "slides" else comfy_cap / m_per_pt) / DEFAULT_CAP_EM
    for item_id, role, label in (("FS-1", "body", "body text"), ("FS-2", "supporting", "supporting text")):
        scored = [u for u in units if role in u and not u["hidden"]]
        if not scored:
            items[item_id] = {"role": role, "level": None, "units": 0}
            continue
        levels = sorted(u[role]["level"] for u in scored)
        item_level = levels[int(ITEM_PERCENTILE * len(levels))]
        counts = Counter(levels)
        low = [u for u in scored if u[role]["level"] < TARGET_LEVEL]
        confidence = "high" if not default_cap_spans and not (kind == "poster" and not print_size) else "medium"
        if any(u[role]["smallest"].get("ocr") for u in low):
            confidence = "medium"  # OCR sizes are estimates (about +-10%)
        items[item_id] = {"role": role, "level": item_level, "units": len(scored),
                          "level_counts": {f"L{k}": counts.get(k, 0) for k in (1, 2, 3, 4)},
                          "confidence": confidence}
        if low:
            low.sort(key=lambda u: u[role]["smallest"]["arcmin"])
            worst = low[0][role]["smallest"]
            where = [str(u["page"]) if kind == "slides" else f'poster {u["page"]}' for u in low]
            sample = list(dict.fromkeys(where))[:3]
            if kind == "slides":
                sample.sort(key=int)
            # Name what is small: supporting text by reason, body text by kind (with counts).
            if role == "supporting":
                reasons = Counter(u[role]["smallest"]["reason"] for u in low)
                parts = [(f"{r}s", n) for r, n in reasons.most_common()]
            else:
                kc = Counter(u[role]["smallest"]["kind"] for u in low)
                parts = [(KIND_PLURAL[k], n) for k, n in kc.most_common()]
            what = ", ".join(f"{name} ({n} {unit_word[n != 1]})" if i == 0 else f"{name} ({n})"
                             for i, (name, n) in enumerate(parts))
            n_low = len(low)
            headline = (f"{n_low} {unit_word[n_low != 1]} {'has' if n_low == 1 else 'have'} "
                        f"{label} smaller than comfortable reading size (about {comfy_pt:.0f} pt "
                        f"in this {'deck' if kind == 'slides' else 'poster'}).")
            examples = (("slide " if len(sample) == 1 else "slides ") if kind == "slides" else "") + ", ".join(sample)
            size = (f"about {worst['size_pt']:g} pt, text in an image or shape" if worst.get("ocr")
                    else f"{worst['size_pt']:g} pt {worst['font']}")
            details = (f"Smallest text is in {what}. For example: {examples}. Smallest: "
                       f"{size} ({worst['arcmin']:.1f}′, \"{worst['text'][:40]}\").")
            findings.append({
                "id": item_id, "level": min(u[role]["level"] for u in low), "count": n_low,
                "confidence": confidence, "headline": headline, "details": details,
                "summary": f"{item_id}: {headline} {details}",
                "units": [u["page"] if kind == "slides" else [u["page"], u["block"]] for u in low],
            })
    findings.sort(key=lambda f: (f["level"], -f["count"]))

    if default_cap_spans:
        notices.append({"code": "FS-CAP-DEFAULT", "level": "info",
                        "message": f"{default_cap_spans} text runs use fonts without cap-height "
                                   f"metrics; assumed {DEFAULT_CAP_EM} em.", "advice": None})
    if tiny:
        pages_tiny = sorted({t[0] for t in tiny})
        notices.append({"code": "FS-TINY", "level": "info",
                        "message": f"{len(tiny)} text runs are too small to see at all (under "
                                   f"{INVISIBLE_ARCMIN}′, e.g. {tiny[0][2]:g} pt \"{tiny[0][1]}\") and were "
                                   f"not scored, on pages {', '.join(map(str, pages_tiny[:5]))}. These "
                                   "are often hidden metadata, e.g. from embedded videos.",
                        "advice": "Check that this text isn't meant to be read."})
    notices += ocr_notices(ocr, "slide" if kind == "slides" else "poster")

    result = {
        "measure": "font_size", "kind": kind, "preset": preset,
        "print_size": print_size, "m_per_pt": m_per_pt if kind == "poster" else None,
        "default_cap_em": DEFAULT_CAP_EM, "item_percentile": ITEM_PERCENTILE,
        "items": items, "findings": findings, "notices": notices, "units": units,
    }
    path = out_dir / "font_size.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--preset")
    ap.add_argument("--kind", choices=["slides", "poster"])
    ap.add_argument("--print-size", help="poster print size, e.g. 48x36in or 120x90cm")
    a = ap.parse_args(argv)
    try:
        path = measure(a.out_dir, a.preset, a.kind, a.print_size)
    except (ValueError, KeyError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    res = json.loads(path.read_text(encoding="utf-8"))
    for item_id, it in res["items"].items():
        print(f"{item_id} ({it['role']}): level {it['level']}  {it.get('level_counts', '')}")
    for f in res["findings"]:
        print(f["summary"])
    for n in res["notices"]:
        print(f"[{n['level']}] {n['code']}: {n['message']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # Windows consoles and pipes default to cp1252
        stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
