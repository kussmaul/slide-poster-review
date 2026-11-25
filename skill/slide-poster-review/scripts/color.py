"""Check use of color (WCAG 1.4.1 Use of Color; rubric items CO-1 and CO-2).

Usage:
    python scripts/color.py OUTPUT_DIR [--kind slides|poster]

Needs manifest.json, text.json, pages/*.png (render.py, extract_text.py). Writes
OUTPUT_DIR/color.json (same layout as font_size.json: items, findings, notices, units) and, for
flagged pages, simulated views in OUTPUT_DIR/color/ (e.g. p003-deutan.png) for the agent to look
at when judging CO-3.

CO-1  Colors that look alike with color-vision deficiency. On each page, find the main saturated
      colors (each covering at least 0.4% of the page). A pair that is clearly different with
      normal vision (CIELAB delta E > 25) but nearly the same in simulation (delta E < 10) is
      confusable. Simulation: Vienot 1999 for protanopia and deuteranopia, Brettel 1997 for
      tritanopia, Machado 2009 at severity 0.6 for moderate red-green deficiency (DaltonLens).
      Photos are left out: their colors rarely carry meaning (a red shirt on green grass). An
      image counts as a photo unless most of its pixels (80%) are in a few flat colors, as in
      charts and diagrams pasted as pictures. For .pptx files, the colors of each native chart's
      series (or of its points, for pie charts) are also read from the file and compared in
      pairs, so thin lines and small legend keys count even when they cover little of the page.
        Level 4  no confusable pairs
        Level 3  confusable only with tritanopia (blue-yellow; about 1 in 10,000 people)
        Level 2  confusable with protanopia or deuteranopia (red-green; about 2% of men)
        Level 1  confusable even with moderate red-green deficiency (about 6% more men)
      This shows where color *could* be the only cue. Whether meaning is lost is judged (CO-3).

CO-2  Text emphasized by color alone: words in a line whose color differs from the main color
      of their text block (delta E > 20) with no other cue: same weight, style, and size, and not
      underlined. Black vs. grey is a lightness difference, not a color cue, and isn't counted.
        Level 4  none
        Level 3  the words also differ in lightness from the surrounding text by 3:1 or more
        Level 2  less than 3:1, but still distinct in every simulation
        Level 1  indistinguishable from the surrounding text in some simulation

Units are pages (slides, or a whole poster). Item level = level reached by 90% of units.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np
import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contrast as ct  # noqa: E402  (colour math, page loading)
import font_size as fs  # noqa: E402  (item percentile)

SAT_MIN = 40          # max-min RGB channel spread: below this a colour counts as grey
QUANT = 24            # RGB bin size for the page palette
MIN_AREA = 0.004      # a palette colour must cover this share of the page
MERGE_DE = 12         # palette bins closer than this are one colour
DISTINCT_DE = 25      # clearly different with normal vision
CONFUSE_DE = 10       # nearly the same in simulation
EMPH_DE = 20          # a span this far from its line's main colour is colour emphasis
MODERATE = 0.6        # severity used for "moderate" red-green deficiency
FLAT_SHARE = 0.8      # an image with this share of pixels in its top 8 colours is a graphic, not a photo
NEUTRAL_CHROMA = 10   # CIELAB chroma below this = black, white, or grey
SAMPLE_PX = 900       # palette sampled from a page scaled to about this many px on the long side
VIEW_PX = 1600        # simulated views saved at most this wide

TYPES = {"protan": "protanopia", "deutan": "deuteranopia", "tritan": "tritanopia",
         "protan-moderate": "moderate protanomaly", "deutan-moderate": "moderate deuteranomaly"}


# ---------- colour math ----------

def srgb_to_lab(rgb) -> np.ndarray:
    """CIELAB (D65) of sRGB values 0-255, any shape ... x 3."""
    c = np.asarray(rgb, dtype=float) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]),
                     200 * (f[..., 1] - f[..., 2])], axis=-1)


def delta_e(a, b) -> np.ndarray:
    """CIE76 colour difference."""
    return np.sqrt(((srgb_to_lab(a) - srgb_to_lab(b)) ** 2).sum(axis=-1))


_SIMS = None


def _simulators():
    global _SIMS
    if _SIMS is None:
        from daltonlens import simulate as s
        _SIMS = (s, s.Simulator_Vienot1999(), s.Simulator_Brettel1997(), s.Simulator_Machado2009())
    return _SIMS


def simulate(rgb: np.ndarray, cvd: str) -> np.ndarray:
    """Simulated appearance of uint8 RGB (H x W x 3, or N x 3) for one type in TYPES."""
    s, vienot, brettel, machado = _simulators()
    arr = np.asarray(rgb, dtype=np.uint8)
    flat = arr.ndim == 2
    img = arr[None, ...] if flat else arr
    d = {"protan": s.Deficiency.PROTAN, "deutan": s.Deficiency.DEUTAN,
         "tritan": s.Deficiency.TRITAN}[cvd.split("-")[0]]
    if cvd.endswith("moderate"):
        out = machado.simulate_cvd(img, d, severity=MODERATE)
    elif d == s.Deficiency.TRITAN:
        out = brettel.simulate_cvd(img, d, severity=1.0)
    else:
        out = vienot.simulate_cvd(img, d, severity=1.0)
    return out[0] if flat else out


def confusions(a, b) -> list[str]:
    """CVD types under which two colours that differ with normal vision look nearly the same."""
    pair = np.array([a, b], dtype=np.uint8)
    out = []
    for cvd in TYPES:
        sa, sb = simulate(pair, cvd)
        if delta_e(sa, sb) < CONFUSE_DE:
            out.append(cvd)
    return out


def level_for(types: list[str]) -> int:
    if any(t.endswith("moderate") for t in types):
        return 1
    if "protan" in types or "deutan" in types:
        return 2
    return 3 if types else 4


# ---------- CO-1: page palette ----------

def is_photo(region: np.ndarray) -> bool:
    """True for a photo-like image region (many colours), False for flat graphics."""
    q = region.reshape(-1, 3).astype(int) // 16
    if len(q) < 100:
        return False
    _, counts = np.unique(q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2], return_counts=True)
    return np.sort(counts)[::-1][:8].sum() / len(q) < FLAT_SHARE


def palette(img: np.ndarray, skip: list = ()) -> list[dict]:
    """Main saturated colours on a page: [{rgb, share}], largest first. `skip`: pixel boxes
    (x0, y0, x1, y1) to leave out, e.g. photos."""
    step = max(1, round(max(img.shape[:2]) / SAMPLE_PX))
    small = img[::step, ::step]
    keep = np.ones(small.shape[:2], dtype=bool)
    for x0, y0, x1, y1 in skip:
        keep[max(0, int(y0) // step):int(y1) // step + 1, max(0, int(x0) // step):int(x1) // step + 1] = False
    px = small[keep].astype(int)
    total = small.shape[0] * small.shape[1]
    px = px[(px.max(axis=1) - px.min(axis=1)) > SAT_MIN]
    if not len(px):
        return []
    q = px // QUANT
    keys = q[:, 0] * 10000 + q[:, 1] * 100 + q[:, 2]
    uniq, inv, counts = np.unique(keys, return_inverse=True, return_counts=True)
    bins = []
    for k in np.argsort(-counts):
        if counts[k] / total < MIN_AREA / 4:
            break
        bins.append({"rgb": px[inv == k].mean(axis=0), "n": int(counts[k])})
    merged: list[dict] = []
    for b in bins:  # largest first: smaller nearby bins join it
        for m in merged:
            if delta_e(m["rgb"], b["rgb"]) < MERGE_DE:
                m["n"] += b["n"]
                break
        else:
            merged.append(dict(b))
    return [{"rgb": m["rgb"], "share": m["n"] / total} for m in merged if m["n"] / total >= MIN_AREA]


def chart_pairs(charts: list[dict]) -> list[dict]:
    """Confusable pairs among the colours that tell one native chart's series (or points) apart."""
    pairs = []
    for ch in charts:
        cols = [(c["name"], ct.hex_rgb(c["rgb"])) for c in ch.get("colors", []) if c.get("rgb")]
        for (na, a), (nb, b) in combinations(cols, 2):
            de = float(delta_e(a, b))
            if de <= DISTINCT_DE:
                continue
            types = confusions(a, b)
            if types:
                pairs.append({"colors": [ct.rgb_hex(a), ct.rgb_hex(b)], "names": [na, nb], "source": "chart",
                              "delta_e": round(de, 1), "types": types, "level": level_for(types)})
    return sorted(pairs, key=lambda p: p["level"])


def confusable_pairs(colors: list[dict]) -> list[dict]:
    pairs = []
    for a, b in combinations(colors, 2):
        de = float(delta_e(a["rgb"], b["rgb"]))
        if de <= DISTINCT_DE:
            continue
        types = confusions(np.round(a["rgb"]), np.round(b["rgb"]))
        if types:
            pairs.append({"colors": [ct.rgb_hex(a["rgb"]), ct.rgb_hex(b["rgb"])],
                          "shares": [round(a["share"], 4), round(b["share"], 4)],
                          "delta_e": round(de, 1), "types": types, "level": level_for(types)})
    return sorted(pairs, key=lambda p: (p["level"], -min(p["shares"])))


def save_view(img: np.ndarray, cvd: str, path: Path) -> None:
    step = max(1, -(-img.shape[1] // VIEW_PX))
    small = np.ascontiguousarray(img[::step, ::step].astype(np.uint8))
    sim = np.ascontiguousarray(simulate(small, cvd).astype(np.uint8))
    pix = pymupdf.Pixmap(pymupdf.csRGB, sim.shape[1], sim.shape[0], sim.tobytes(), False)
    path.parent.mkdir(exist_ok=True)
    pix.save(path)


# ---------- CO-2: colour-only emphasis ----------

def _is_bold(s):
    return s.get("bold") or "bold" in s["font"].lower() or "black" in s["font"].lower()


def _is_italic(s):
    return s.get("italic") or re.search(r"italic|oblique", s["font"], re.I) is not None


def underlined(span: dict, rules: list) -> bool:
    """True if a thin horizontal shape runs under most of the span (drawn underline)."""
    x0, _, x1, _ = span["bbox"]
    base, size = span["origin"][1], span["size_pt"]
    for r in rules:
        if (r[1] >= base - 0.05 * size and r[1] <= base + 0.35 * size
                and min(x1, r[2]) - max(x0, r[0]) >= 0.7 * (x1 - x0)):
            return True
    return False


def thin_rules(page: pymupdf.Page) -> list:
    out = []
    for d in page.get_drawings():
        r = d["rect"]
        if r.width > 3 and r.height < 3:
            out.append((r.x0, r.y0, r.x1, r.y1))
    return out


def chroma(rgb) -> float:
    lab = srgb_to_lab(rgb)
    return float(np.hypot(lab[..., 1], lab[..., 2]))


def emphasis_spans(spans: list[dict], rules: list, links: list) -> list[dict]:
    """Spans that differ from their text block's main colour only by colour. Only lines that
    mix colours are checked, so a whole line or block in another colour (e.g. a heading) isn't."""
    blocks, lines = defaultdict(Counter), defaultdict(list)
    for s in spans:
        if re.search(r"\w", s["text"]) and s.get("dir", [1, 0]) == [1.0, 0.0]:
            lines[(s["block"], s["line"])].append(s)
            blocks[s["block"]][s["color"]] += len(s["text"].strip())
    out = []
    for (block, _), ss in lines.items():
        if len({s["color"] for s in ss}) < 2:
            continue
        main = blocks[block].most_common(1)[0][0]
        if main not in {s["color"] for s in ss}:
            main = Counter({c: n for c, n in blocks[block].items()
                            if c in {s["color"] for s in ss}}).most_common(1)[0][0]
        ref = next(s for s in ss if s["color"] == main)
        for s in ss:
            if s["color"] == main or len(re.sub(r"\W", "", s["text"])) < 2:
                continue
            a, b = ct.hex_rgb(s["color"]), ct.hex_rgb(main)
            if float(delta_e(a, b)) <= EMPH_DE or max(chroma(a), chroma(b)) < NEUTRAL_CHROMA:
                continue
            if (_is_bold(s) != _is_bold(ref) or _is_italic(s) != _is_italic(ref)
                    or abs(s["size_pt"] - ref["size_pt"]) > 0.1 * ref["size_pt"]
                    or underlined(s, rules)):
                continue
            cx, cy = (s["bbox"][0] + s["bbox"][2]) / 2, (s["bbox"][1] + s["bbox"][3]) / 2
            is_link = any(l[0] <= cx <= l[2] and l[1] <= cy <= l[3] for l in links)
            lum_ratio = float(ct.contrast_ratio(ct.rel_luminance(a), ct.rel_luminance(b)))
            sims = [t for t in ("protan", "deutan", "tritan")
                    if delta_e(*simulate(np.array([a, b], dtype=np.uint8), t)) < CONFUSE_DE]
            level = 3 if lum_ratio >= 3 else 1 if sims else 2
            out.append({"text": s["text"].strip()[:60], "color": s["color"], "line_color": main,
                        "lightness_ratio": round(lum_ratio, 2), "types": sims, "link": is_link,
                        "level": level})
    return out


# ---------- measurement ----------

def _where(units: list[dict], kind: str) -> str:
    pages = [str(u["page"]) for u in units][:3]
    word = ("slide", "slides") if kind == "slides" else ("poster", "posters")
    return f"{word[len(pages) != 1]} " + ", ".join(pages)


def _types_text(types: list[str]) -> str:
    names = []
    if any(t.startswith("protan") for t in types) or any(t.startswith("deutan") for t in types):
        names.append("red-green")
    if "tritan" in types:
        names.append("blue-yellow")
    return " or ".join(names) + " color blindness"


def measure(out_dir: Path, kind: str | None = None) -> Path:
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    text = json.loads((out_dir / "text.json").read_text(encoding="utf-8"))
    kind = kind or manifest["kind_guess"]
    doc = pymupdf.open(out_dir / manifest["pdf"])
    mpages = {p["index"]: p for p in manifest["pages"]}
    slides_info = {s["index"]: s for s in (text.get("pptx") or {}).get("slides", [])}
    views = out_dir / "color"
    for old in views.glob("*.png") if views.exists() else []:
        old.unlink()

    units = []
    for p in text["pages"]:
        i = p["index"]
        mp = mpages[i]
        img = ct.load_page(out_dir / mp["image"])
        page = doc[i - 1]
        sx, sy = mp["px_per_pt_x"], mp["px_per_pt_y"]
        boxes = [(b[0] * sx, b[1] * sy, b[2] * sx, b[3] * sy)
                 for b in (info["bbox"] for info in page.get_image_info())]
        photos = [b for b in boxes if is_photo(img[max(0, int(b[1])):int(b[3]):2, max(0, int(b[0])):int(b[2]):2])]
        charts = [sh["chart"] for sh in slides_info.get(i, {}).get("shapes", []) if sh.get("chart")]
        pairs = sorted(chart_pairs(charts) + confusable_pairs(palette(img, photos)), key=lambda x: x["level"])
        links = [tuple(l["from"]) for l in page.get_links()]
        emph = emphasis_spans(p["spans"], thin_rules(page), links)
        unit = {"page": i, "hidden": mp["hidden"],
                "CO-1": {"level": min([x["level"] for x in pairs], default=4), "pairs": pairs[:5],
                         "photos_skipped": len(photos)},
                "CO-2": {"level": min([x["level"] for x in emph], default=4), "spans": emph[:5]}}
        if pairs and not mp["hidden"]:
            worst = pairs[0]["types"]
            cvd = next(t for t in ("deutan", "protan", "tritan") if t in worst or f"{t}-moderate" in worst)
            name = f"p{i:03d}-{cvd}.png"
            save_view(img, cvd, views / name)
            unit["CO-1"]["view"] = f"color/{name}"
        units.append(unit)

    unit_word = ("slide", "slides") if kind == "slides" else ("poster", "posters")
    items, findings = {}, []
    scored = [u for u in units if not u["hidden"]]
    for iid in ("CO-1", "CO-2"):
        if not scored:
            items[iid] = {"level": None, "units": 0}
            continue
        levels = sorted(u[iid]["level"] for u in scored)
        counts = Counter(levels)
        items[iid] = {"level": levels[int(fs.ITEM_PERCENTILE * len(levels))], "units": len(scored),
                      "confidence": "medium" if iid == "CO-1" else "high",
                      "level_counts": {f"L{k}": counts.get(k, 0) for k in (1, 2, 3, 4)}}
        low = sorted((u for u in scored if u[iid]["level"] < 4), key=lambda u: (u[iid]["level"], u["page"]))
        if not low:
            continue
        n = len(low)
        has = "has" if n == 1 else "have"
        if iid == "CO-1":
            all_types = sorted({t for u in low for x in u[iid]["pairs"] for t in x["types"]})
            ex = low[0]
            pair = ex[iid]["pairs"][0]
            headline = (f"{n} {unit_word[n != 1]} {has} colors that look alike to people with "
                        f"{_types_text(all_types)}.")
            named = f" (chart series {pair['names'][0]!r} and {pair['names'][1]!r})" if pair.get("names") else ""
            details = (f"For example: {_where(sorted(low, key=lambda u: u['page']), kind)}. "
                       f"On {unit_word[0]} {ex['page']}, {pair['colors'][0]} and {pair['colors'][1]}{named} "
                       f"look alike ({', '.join(TYPES[t] for t in pair['types'])}). "
                       f"Simulated view: {ex[iid].get('view', '')}. "
                       "This matters if the colors carry meaning, e.g. in a chart or legend.")
        else:
            spans = [x for u in low for x in u[iid]["spans"]]
            n_links = sum(x["link"] for x in spans)
            worst = min(spans, key=lambda x: (x["level"], x["lightness_ratio"]))
            headline = f"{n} {unit_word[n != 1]} {has} words emphasized by color alone."
            details = (f"For example: {_where(sorted(low, key=lambda u: u['page']), kind)}"
                       f" (\"{worst['text'][:40]}\", {worst['color']} in {worst['line_color']} text"
                       + (f"; looks the same with {_types_text(worst['types'])}" if worst["types"] else "")
                       + ")." + (f" {n_links} of these are links." if n_links else ""))
        findings.append({"id": iid, "level": min(u[iid]["level"] for u in low), "count": n,
                         "confidence": items[iid]["confidence"], "headline": headline,
                         "details": details, "summary": f"{iid}: {headline} {details}",
                         "units": [u["page"] for u in low]})
    findings.sort(key=lambda f: (f["level"], -f["count"]))
    result = {"measure": "color", "kind": kind,
              "thresholds": {"distinct_de": DISTINCT_DE, "confuse_de": CONFUSE_DE,
                             "emphasis_de": EMPH_DE, "min_area": MIN_AREA, "moderate": MODERATE},
              "items": items, "findings": findings, "notices": [], "units": units}
    path = out_dir / "color.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


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
        print(f"{iid}: level {it['level']}  {it.get('level_counts', '')}")
    for f in res["findings"]:
        print(f["summary"])
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # Windows consoles and pipes default to cp1252
        stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
