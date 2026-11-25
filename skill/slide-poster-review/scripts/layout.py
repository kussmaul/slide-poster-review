"""Check layout and consistency (rubric items LY-1 to LY-4); collect hints for CL-1 and DG-1.

Usage:
    python scripts/layout.py OUTPUT_DIR [--kind slides|poster]

Needs manifest.json and text.json (render.py, extract_text.py). Writes OUTPUT_DIR/layout.json
(same layout as font_size.json: items, findings, notices, units) plus `hints` for the judged
items CL-1 (cognitive load) and DG-1 (data graphics).

LY-1  Text collides: text from different text blocks overlapping (e.g. a body line running into
      the footer), or text cut off at the page edge. Boxes are the letters' ink area (cap height
      above the baseline, descenders below), so lines that merely sit close don't count.
        Level 4  none                  Level 3  on one slide, or up to 5% of slides
        Level 2  up to 10% of slides   Level 1  more than 10%
      With a .pptx, also text running out of a shape with a visible fill or outline (e.g. a
      colored box). Text boxes without fill or outline are skipped: their overflow shows only as
      a collision or cut-off text. Text entirely off the slide is noted (LY-OFFPAGE), not scored.
LY-2  Titles stand out: on each slide, the title's cap height vs. the largest body text
      (bullets, paragraphs; not labels or chart text).
        Level 4  title 1.2x or more    Level 3  1.1x or more
        Level 2  about the same size   Level 1  body text larger than the title
      Item level = level reached by 90% of slides with a title and body text. Without a .pptx the
      title is taken to be the largest text at the top, so Level 1 can't occur (medium confidence).
LY-3  Few fonts: font families in body text, each with at least 2% of the characters (symbol and
      emoji fonts left out). 1-2 families: Level 4; 3: Level 3; 4: Level 2; 5 or more: Level 1.
LY-4  Titles in a consistent place: within each slide layout (or the whole deck without a
      .pptx), titles whose position or size differ from the most common one (by more than 2% of
      the page, or 10% in size; e.g. shrunk by autofit). Share of titled slides that differ:
        Level 4  none                  Level 3  up to 10%
        Level 2  up to 25%             Level 1  more than 25%
Posters: LY-1 and LY-3 only. Hidden slides are not scored.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import font_size as fs  # noqa: E402  (roles, kinds, item percentile)
from render import base_font_name  # noqa: E402

CAP_DEFAULT = 0.72
DESCENT = 0.21                     # descender depth below the baseline, in em
MIN_OVERLAP_PT = 2.0
MIN_OVERLAP_SHARE = 0.25           # of the smaller box's height
EDGE_TOL_PT = 1.0
OVERFLOW_MIN_PT, OVERFLOW_SHARE = 2.0, 0.15   # text this far past its shape's edge overflows
HIERARCHY_BOUNDS = (0.99, 1.1, 1.2)   # L2, L3, L4 lower bounds of title / body cap ratio
FONT_MIN_SHARE = 0.02
POS_TOL, SIZE_TOL = 0.02, 0.10
COLOR_TOL = 60                     # max RGB channel difference for "this text's color"
COVERED_SHARE = 0.02               # below this share of its color in the overlap, a text is covered
SYMBOL_FONT = re.compile(r"symbol|wingding|webding|dingbat|emoji|marlett|fontawesome|materialicons", re.I)
STYLE_WORDS = re.compile(r"(bold|italic|oblique|light|medium|regular|semibold|demibold|black|heavy|"
                         r"thin|condensed|narrow)+$", re.I)  # only at the end: 'ArialBold' -> 'Arial' 
BODY_KINDS = {"bullet", "sub-bullet", "text"}


def font_family(name: str) -> str:
    """'ABCDEF+Arial-BoldItalicMT' -> 'Arial'; 'Calibri,Bold' -> 'Calibri'."""
    n = base_font_name(name)
    n = re.split(r"[-,]", n)[0]
    n = re.sub(r"(PSMT|PS|MT)$", "", n)
    n = STYLE_WORDS.sub("", n) or n
    n = n.strip() or name
    return "(unnamed font)" if re.fullmatch(r"[\d\W_]*", n) else n


def _has_letters(t: str) -> bool:
    return re.search(r"[^\W\d_]", t) is not None


def ink_box(s: dict, cap_em: float) -> tuple[float, float, float, float]:
    x0, _, x1, _ = s["bbox"]
    base, size = s["origin"][1], s["size_pt"]
    return (x0 + 0.5, base - cap_em * size, x1 - 0.5, base + DESCENT * size)


def _color_share(img, box_px, hex_color: str) -> float:
    """Share of pixels in a box within COLOR_TOL of a text color."""
    import numpy as np
    x0, y0, x1, y1 = (int(round(v)) for v in box_px)
    region = img[max(0, y0):max(0, y1), max(0, x0):max(0, x1)]
    if region.size == 0:
        return 1.0
    rgb = np.array([int(hex_color[i:i + 2], 16) for i in (1, 3, 5)])
    return float((np.abs(region.astype(int) - rgb).max(axis=-1) < COLOR_TOL).mean())


def visible_overlap(img, scale: tuple[float, float], a: dict, b: dict, box: tuple) -> bool:
    """False if one of two overlapping spans is covered there (e.g. by an opaque shape), so the
    overlap isn't visible. True if both show, or if their colors are too alike to tell."""
    if img is None:
        return True
    ca, cb = a["color"], b["color"]
    if max(abs(int(ca[i:i + 2], 16) - int(cb[i:i + 2], 16)) for i in (1, 3, 5)) < COLOR_TOL:
        return True
    sx, sy = scale
    px = (box[0] * sx, box[1] * sy, box[2] * sx, box[3] * sy)
    return min(_color_share(img, px, ca), _color_share(img, px, cb)) >= COVERED_SHARE


def paint_order(pdf_page) -> dict:
    """Opaque filled shapes and text, each with its drawing sequence number (later = on top)."""
    fills = [(tuple(d["rect"]), d["seqno"]) for d in pdf_page.get_drawings()
             if d.get("fill") is not None and (d.get("fill_opacity") or 1) >= 0.99]
    texts = [(tuple(t["bbox"]), t["seqno"]) for t in pdf_page.get_texttrace()]
    return {"fills": fills, "texts": texts}


def _covered_by_shape(order: dict | None, box: tuple) -> bool:
    """True if an opaque shape covering `box` is drawn after some text in it."""
    if not order:
        return False
    def meets(r):
        return r[0] < box[2] and r[2] > box[0] and r[1] < box[3] and r[3] > box[1]
    seqs = [q for r, q in order["texts"] if meets(r)]
    if not seqs:
        return False
    first = min(seqs)
    return any(q > first and r[0] <= box[0] + 1 and r[1] <= box[1] + 1 and r[2] >= box[2] - 1
               and r[3] >= box[3] - 1 for r, q in order["fills"])


def _pieces(s: dict) -> list[dict]:
    """A span split at runs of 3+ spaces (e.g. "Yes      No" laid out as one span), with x
    positions estimated in proportion to character counts."""
    t = s["text"]
    if not re.search(r"\S\s{3,}\S", t):
        return [s]
    x0, x1 = s["bbox"][0], s["bbox"][2]
    per = (x1 - x0) / max(1, len(t))
    out = []
    for m in re.finditer(r"\S+(?:\s{1,2}\S+)*", t):
        if _has_letters(m.group()):
            out.append({**s, "text": m.group(), "bbox": [x0 + per * m.start(), s["bbox"][1],
                                                         x0 + per * m.end(), s["bbox"][3]]})
    return out


def collisions(page: dict, fonts: dict, img=None, scale=(1.0, 1.0), order: dict | None = None
               ) -> tuple[list[dict], list[dict]]:
    """(collisions, covered): pairs of visibly overlapping spans from different text blocks plus
    spans cut off at the edge; and overlaps where one text is hidden under the other or a shape."""
    W, H = page["width_pt"], page["height_pt"]
    spans = [piece for s in page["spans"] if _has_letters(s["text"]) and s.get("dir", [1, 0]) == [1.0, 0.0]
             and not s.get("superscript") for piece in _pieces(s)]
    boxes = [ink_box(s, (fonts.get(s["font"]) or {}).get("cap_height_em") or CAP_DEFAULT) for s in spans]
    out, covered = [], []
    for i in range(len(spans)):
        a, ba = spans[i], boxes[i]
        if ba[0] < -EDGE_TOL_PT or ba[2] > W + EDGE_TOL_PT or ba[1] < -EDGE_TOL_PT or ba[3] > H + EDGE_TOL_PT:
            out.append({"type": "edge", "text": a["text"].strip()[:50], "role": a.get("role")})
        for j in range(i + 1, len(spans)):
            b, bb = spans[j], boxes[j]
            if (a["block"], a["line"]) == (b["block"], b["line"]):
                continue  # PyMuPDF merges overlapping text boxes into one block, so compare lines
            w = min(ba[2], bb[2]) - max(ba[0], bb[0])
            h = min(ba[3], bb[3]) - max(ba[1], bb[1])
            if w > MIN_OVERLAP_PT and h > MIN_OVERLAP_SHARE * min(ba[3] - ba[1], bb[3] - bb[1]):
                rec = {"type": "overlap", "text": [a["text"].strip()[:50], b["text"].strip()[:50]],
                       "roles": [a.get("role"), b.get("role")]}
                box = (max(ba[0], bb[0]), max(ba[1], bb[1]), min(ba[2], bb[2]), min(ba[3], bb[3]))
                hidden = _covered_by_shape(order, box) or not visible_overlap(img, scale, a, b, box)
                (covered if hidden else out).append(rec)
    return out, covered


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip().lower()


def overflows(page: dict, fonts: dict, boxes: list[dict]) -> list[dict]:
    """Text that spills out of a shape with a visible fill or outline (.pptx only). Invisible text
    boxes are skipped: their overflow only shows as a collision or cut-off text. So are shapes
    that resize to fit their text, since the stored size may be out of date."""
    texts = [_norm(bx["text"]) for bx in boxes]
    worst: dict[int, tuple[float, str]] = {}
    for s in page["spans"]:
        t = _norm(s["text"])
        if len(t) < 4 or s.get("dir", [1, 0]) != [1.0, 0.0]:
            continue
        ib = ink_box(s, (fonts.get(s["font"]) or {}).get("cap_height_em") or CAP_DEFAULT)
        # A span belongs to the nearest shape whose text contains it (the same words may be in
        # several shapes); how far its ink reaches past that shape's edges.
        cands = [(max(bx["bbox"][1] - ib[1], ib[3] - bx["bbox"][3], bx["bbox"][0] - ib[0], ib[2] - bx["bbox"][2]), k)
                 for k, bx in enumerate(boxes) if t in texts[k]
                 # overflow stays in its shape's column: at least half the span is within its width
                 and min(ib[2], bx["bbox"][2]) - max(ib[0], bx["bbox"][0]) >= 0.5 * (ib[2] - ib[0])]
        if not cands:
            continue
        past, k = min(cands)
        bx = boxes[k]
        if not (bx["filled"] or bx["outlined"]) or bx["autofit"] == "shape":
            continue
        if past > max(OVERFLOW_MIN_PT, OVERFLOW_SHARE * s["size_pt"]) and past > worst.get(k, (0, ""))[0]:
            worst[k] = (past, s["text"].strip()[:50])
    return [{"type": "overflow", "text": w[1], "shape": boxes[k]["name"], "by_pt": round(w[0], 1)}
            for k, w in sorted(worst.items())]


def off_page(page: dict, boxes: list[dict]) -> list[str]:
    """Text shapes placed entirely off the slide: not shown, and not in the PDF."""
    W, H = page["width_pt"], page["height_pt"]
    return [bx["text"].strip()[:50] for bx in boxes
            if bx["bbox"][2] <= 0 or bx["bbox"][0] >= W or bx["bbox"][3] <= 0 or bx["bbox"][1] >= H]


def _cap(s: dict, fonts: dict) -> float:
    return s["size_pt"] * ((fonts.get(s["font"]) or {}).get("cap_height_em") or CAP_DEFAULT)


def _level(value: float, bounds: tuple) -> int:
    return 1 + sum(value >= b for b in bounds)


def _share_level(n: int, total: int, bounds: tuple[float, float, float], one_is_l3: bool = False) -> int:
    """Level from the share of units with a problem: bounds are the L4, L3, L2 upper limits."""
    if n == 0:
        return 4
    share = n / total
    if share <= bounds[1] or (one_is_l3 and n == 1):
        return 3
    return 2 if share <= bounds[2] else 1


def _where(pages: list[int], kind: str) -> str:
    word = ("slide", "slides") if kind == "slides" else ("page", "pages")
    return f"{word[len(pages) != 1]} " + ", ".join(map(str, pages[:3]))


def measure(out_dir: Path, kind: str | None = None) -> Path:
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    text = json.loads((out_dir / "text.json").read_text(encoding="utf-8"))
    kind = kind or manifest["kind_guess"]
    fonts = text["fonts"]
    pptx = text.get("pptx")
    slides_info = {s["index"]: s for s in (pptx or {}).get("slides", [])}
    hidden = {p["index"]: p["hidden"] for p in manifest["pages"]}
    mpages = {p["index"]: p for p in manifest["pages"]}
    import pymupdf
    doc = pymupdf.open(out_dir / manifest["pdf"])
    fs.assign_roles(text["pages"], kind)
    fs.assign_kinds(text["pages"], pptx)
    unit_word = ("slide", "slides") if kind == "slides" else ("page", "pages")

    units, family_chars, titles = [], Counter(), []
    for p in text["pages"]:
        i = p["index"]
        u = {"page": i, "hidden": hidden.get(i, False)}
        mp = mpages.get(i)
        img = None
        if mp and (out_dir / mp["image"]).exists():
            import contrast as ct
            img = ct.load_page(out_dir / mp["image"])
        found, covered = collisions(p, fonts, img, (mp["px_per_pt_x"], mp["px_per_pt_y"]) if mp else (1, 1),
                                    paint_order(doc[i - 1]))
        tboxes = slides_info.get(i, {}).get("text_boxes", [])
        found += overflows(p, fonts, tboxes)
        u["LY-1"] = {"collisions": found, "covered": covered, "off_page": off_page(p, tboxes)}
        u["LY-1"]["level"] = 4 if not u["LY-1"]["collisions"] else 1
        body = [s for s in p["spans"] if s.get("role") == "body" and _has_letters(s["text"])]
        title_spans = [s for s in body if s.get("kind") == "title"]
        main = [s for s in body if s.get("kind") in BODY_KINDS]
        if kind == "slides" and title_spans and main:
            ratio = max(_cap(s, fonts) for s in title_spans) / max(_cap(s, fonts) for s in main)
            u["LY-2"] = {"ratio": round(ratio, 2), "level": _level(ratio, HIERARCHY_BOUNDS)}
        if title_spans and not u["hidden"]:
            x0 = min(s["bbox"][0] for s in title_spans)
            x1 = max(s["bbox"][2] for s in title_spans)
            y0 = min(s["bbox"][1] for s in title_spans)
            y1 = max(s["bbox"][3] for s in title_spans)
            titles.append({"page": i, "layout": slides_info.get(i, {}).get("layout") or "all",
                           "x0": x0 / p["width_pt"], "cx": (x0 + x1) / 2 / p["width_pt"],
                           "x1": x1 / p["width_pt"], "y0": y0 / p["height_pt"],
                           "cy": (y0 + y1) / 2 / p["height_pt"], "y1": y1 / p["height_pt"],
                           "size": max(s["size_pt"] for s in title_spans)})
        if not u["hidden"]:
            for s in body:
                if not SYMBOL_FONT.search(s["font"]):
                    family_chars[font_family(s["font"])] += len(re.sub(r"\s", "", s["text"]))
        # hints for judged items
        words = sum(len(s["text"].split()) for s in main)
        lines = {(s["block"], s["line"]) for s in main}
        shapes = slides_info.get(i, {}).get("shapes", [])
        u["hints"] = {"body_words": words, "body_lines": len(lines),
                      "bullets": len({(s["block"], s["line"]) for s in main if s.get("kind") in ("bullet", "sub-bullet")
                                      and fs.BULLET_START.match(s["text"])}),
                      "images": sum(1 for sh in shapes if sh.get("media") == "image" and not sh.get("chart")),
                      "charts": [sh["chart"] for sh in shapes if sh.get("chart")]}
        units.append(u)

    scored = [u for u in units if not u["hidden"]]
    items, findings, notices = {}, [], []

    def add_finding(iid, level, low, headline, details, confidence):
        findings.append({"id": iid, "level": level, "count": len(low), "confidence": confidence,
                         "headline": headline, "details": details, "summary": f"{iid}: {headline} {details}",
                         "units": [u["page"] for u in low]})

    # LY-1
    low = [u for u in scored if u["LY-1"]["collisions"]]
    level = _share_level(len(low), len(scored), (0, 0.05, 0.10), one_is_l3=True) if scored else None
    items["LY-1"] = {"level": level, "units": len(scored), "confidence": "high"}
    if low:
        n = len(low)
        ex = max(low[0]["LY-1"]["collisions"], key=lambda c: len("".join(c["text"])))
        what = (f"\"{ex['text'][0]}\" overlaps \"{ex['text'][1]}\"" if ex["type"] == "overlap"
                else f"\"{ex['text']}\" runs outside its box" if ex["type"] == "overflow"
                else f"\"{ex['text']}\" is cut off at the edge")
        add_finding("LY-1", level, low,
                    f"{n} {unit_word[n != 1]} {'has' if n == 1 else 'have'} text that overlaps other text, "
                    "runs outside its box, or runs off the page.",
                    f"For example: {_where([u['page'] for u in low], kind)}. On {unit_word[0]} "
                    f"{low[0]['page']}, {what}.", "high")
    parked = [u for u in scored if u["LY-1"]["off_page"]]
    if parked:
        notices.append({"code": "LY-OFFPAGE", "level": "info",
                        "message": f"Text placed entirely off the {unit_word[0]} (not shown or scored) on "
                                   f"{_where([u['page'] for u in parked], kind)}, e.g. "
                                   f"\"{parked[0]['LY-1']['off_page'][0]}\".",
                        "advice": "Check that nothing there was meant to be shown."})

    # LY-2
    with_ratio = [u for u in scored if "LY-2" in u]
    if with_ratio:
        levels = sorted(u["LY-2"]["level"] for u in with_ratio)
        level = levels[int(fs.ITEM_PERCENTILE * len(levels))]
        conf = "high" if pptx else "medium"
        items["LY-2"] = {"level": level, "units": len(with_ratio), "confidence": conf,
                         "level_counts": {f"L{k}": levels.count(k) for k in (1, 2, 3, 4)}}
        low = sorted((u for u in with_ratio if u["LY-2"]["level"] < 3), key=lambda u: (u["LY-2"]["ratio"], u["page"]))
        if low:
            n = len(low)
            add_finding("LY-2", min(u["LY-2"]["level"] for u in low), low,
                        f"On {n} {unit_word[n != 1]}, the title is not clearly larger than the body text.",
                        f"For example: {_where(sorted(u['page'] for u in low), kind)}. On {unit_word[0]} "
                        f"{low[0]['page']}, the title is {low[0]['LY-2']['ratio']:.2f}x the size of the "
                        "largest body text.", conf)
    else:
        items["LY-2"] = {"level": None, "units": 0}

    # LY-3
    total = sum(family_chars.values())
    families = [(f, n / total) for f, n in family_chars.most_common() if total and n / total >= FONT_MIN_SHARE]
    if families:
        n = len(families)
        level = 4 if n <= 2 else 3 if n == 3 else 2 if n == 4 else 1
        items["LY-3"] = {"level": level, "units": len(scored), "confidence": "high",
                         "families": [{"family": f, "share": round(sh, 3)} for f, sh in families]}
        if level < 4:
            add_finding("LY-3", level, [], f"Body text uses {n} font families.",
                        "Fonts: " + ", ".join(f"{f} ({100 * sh:.0f}%)" for f, sh in families[:6]) + ".", "high")
    else:
        items["LY-3"] = {"level": None, "units": 0}

    # LY-4
    if kind == "slides" and len(titles) >= 3:
        off = []
        groups = defaultdict(list)
        for t in titles:
            groups[t["layout"]].append(t)
        for ts in groups.values():
            if len(ts) < 3:
                continue
            anchor = min(("x0", "cx", "x1"), key=lambda k: _outliers([t[k] for t in ts]))
            vanchor = min(("y0", "cy", "y1"), key=lambda k: _outliers([t[k] for t in ts]))
            mx, my = _mode([t[anchor] for t in ts], 0.01), _mode([t[vanchor] for t in ts], 0.01)
            msize = _mode([t["size"] for t in ts], 0.5)
            for t in ts:
                why = []
                if abs(t[anchor] - mx) > POS_TOL or abs(t[vanchor] - my) > POS_TOL:
                    why.append("position")
                if abs(t["size"] - msize) > SIZE_TOL * msize:
                    why.append(f"size {t['size']:.0f} pt vs {msize:.0f} pt")
                if why:
                    off.append({"page": t["page"], "why": why})
        compared = sum(len(ts) for ts in groups.values() if len(ts) >= 3)
        level = _share_level(len(off), compared, (0, 0.10, 0.25)) if compared else None
        items["LY-4"] = {"level": level, "units": compared, "confidence": "medium"}
        for u in units:
            hit = next((o for o in off if o["page"] == u["page"]), None)
            if hit:
                u["LY-4"] = {"level": 2, "differs": hit["why"]}
        if off:
            n = len(off)
            ex = off[0]
            add_finding("LY-4", level, [{"page": o["page"]} for o in off],
                        f"On {n} {unit_word[n != 1]}, the title's position or size differs from the other "
                        "slides with the same layout.",
                        f"For example: {_where([o['page'] for o in off], kind)} ({', '.join(ex['why'])} on "
                        f"{unit_word[0]} {ex['page']}).", "medium")
    else:
        items["LY-4"] = {"level": None, "units": 0}

    hints = {"covered_text": [{"page": u["page"], "text": c["text"]} for u in scored for c in u["LY-1"]["covered"]],
             "slides_over_40_words": [u["page"] for u in scored if u["hints"]["body_words"] > 40],
             "slides_over_6_lines": [u["page"] for u in scored if u["hints"]["body_lines"] > 6],
             "charts": [{"page": u["page"], **c} for u in scored for c in u["hints"]["charts"] if c],
             "median_body_words": sorted(u["hints"]["body_words"] for u in scored)[len(scored) // 2] if scored else 0}
    if not pptx:
        notices.append({"code": "LY-NO-PPTX", "level": "info",
                        "message": "Without the .pptx, titles are guessed from size and position, and "
                                   "charts can't be inspected.", "advice": None})
    findings.sort(key=lambda f: (f["level"], -f["count"]))
    result = {"measure": "layout", "kind": kind, "items": items, "findings": findings,
              "notices": notices, "hints": hints, "units": units}
    path = out_dir / "layout.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _mode(values: list[float], step: float) -> float:
    return Counter(round(v / step) for v in values).most_common(1)[0][0] * step


def _outliers(values: list[float]) -> int:
    """How many values differ from the most common one by more than POS_TOL."""
    m = _mode(values, 0.01)
    return sum(abs(v - m) > POS_TOL for v in values)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--kind", choices=["slides", "poster"])
    a = ap.parse_args(argv)
    try:
        path = measure(a.out_dir, a.kind)
    except (KeyError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    res = json.loads(path.read_text(encoding="utf-8"))
    for iid, it in res["items"].items():
        print(f"{iid}: level {it['level']}  {it.get('level_counts', it.get('families', ''))}")
    for f in res["findings"]:
        print(f["summary"])
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # Windows consoles and pipes default to cp1252
        stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
