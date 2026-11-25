"""Extract text runs (and PPTX structure) from a render.py output directory.

Usage:
    python scripts/extract_text.py OUTPUT_DIR

Reads OUTPUT_DIR/manifest.json and source.pdf; writes OUTPUT_DIR/outline.md (compact text per
page, for reading the content) and OUTPUT_DIR/text.json with:
    fonts   per PDF font: base name, cap height (em) from embedded font metrics when available
    pages   per page: spans with text, font, size_pt, bold/italic, color (#rrggbb), alpha,
            bbox and origin (PDF points, origin top-left), direction
    pptx    (PPTX sources only) per slide: hidden, title, layout, notes, non-text shapes
            with alt text / decorative flags, and text_boxes (box, visible fill or outline,
            autofit) for overflow checks. (Font substitution is reported in manifest.json.)

Not included (needs OCR; see the contrast/OCR step): text inside images, and text the PDF
draws as outlines (e.g. PowerPoint exports rotated chart axis labels as filled paths).
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render import base_font_name  # noqa: E402

EMU_PER_PT = 12700
FLAT_TOP_CAPS = "HIEFLT"


# ---------- fonts ----------

def cap_height_em(buf: bytes, cap_gid: int | None = None) -> tuple[float | None, str | None]:
    """Cap height as a fraction of the em, and where it came from.

    'os2'        OS/2 sCapHeight
    'glyph'      top of a flat-topped capital found through the font's cmap
    'glyph-gid'  same, but the glyph id comes from the PDF text (subset fonts without a cmap,
                 e.g. Google Slides exports)
    """
    try:
        from fontTools.ttLib import TTFont
        font = TTFont(io.BytesIO(buf), lazy=True)
        upm = font["head"].unitsPerEm
        os2 = font["OS/2"] if "OS/2" in font else None
        if os2 is not None and os2.version >= 2 and getattr(os2, "sCapHeight", 0) > 0:
            return os2.sCapHeight / upm, "os2"
        if "glyf" in font:
            glyf = font["glyf"]
            cmap = font.getBestCmap() if "cmap" in font else None
            for ch in FLAT_TOP_CAPS if cmap else ():
                if (g := cmap.get(ord(ch))) and getattr(glyf[g], "yMax", 0) > 0:
                    return glyf[g].yMax / upm, "glyph"
            order = font.getGlyphOrder()
            if cap_gid is not None and cap_gid < len(order):
                g = glyf[order[cap_gid]]
                if getattr(g, "yMax", 0) > 0:
                    return g.yMax / upm, "glyph-gid"
    except Exception:
        pass  # bare CFF / Type1 / Type3 fonts: leave to the default
    return None, None


def _cap_glyph_ids(doc: pymupdf.Document, fonts: set[str]) -> dict[str, int]:
    """For each font, the glyph id of a flat-topped capital the document actually uses."""
    found: dict[str, tuple[int, int]] = {}  # font -> (rank in FLAT_TOP_CAPS, gid)
    for page in doc:
        for span in page.get_texttrace():
            name = base_font_name(span["font"])
            if name not in fonts:
                continue
            for ucs, gid, *_ in span["chars"]:
                ch = chr(ucs) if ucs > 0 else ""
                if ch and ch in FLAT_TOP_CAPS and gid >= 0:
                    rank = FLAT_TOP_CAPS.index(ch)
                    if name not in found or rank < found[name][0]:
                        found[name] = (rank, gid)
        if all(found.get(f, (99,))[0] == 0 for f in fonts):
            break  # an 'H' for every font
    return {f: gid for f, (_, gid) in found.items()}


def font_table(doc: pymupdf.Document) -> dict[str, dict]:
    """PDF font name (as it appears in spans) -> metrics."""
    table: dict[str, dict] = {}
    buffers: dict[str, bytes] = {}
    for page in doc:
        for xref, ext, ftype, name, *_ in page.get_fonts():
            base = base_font_name(name)
            if base in table:
                continue
            cap, src = None, None
            if xref:
                try:
                    buf = doc.extract_font(xref)[3]
                    if buf:
                        buffers[base] = buf
                        cap, src = cap_height_em(buf)
                except Exception:
                    pass
            table[base] = {"type": ftype, "embedded": ext not in ("n/a", ""),
                           "cap_height_em": cap, "cap_height_source": src}
    unresolved = {f for f, v in table.items() if v["cap_height_em"] is None and f in buffers}
    if unresolved:
        for f, gid in _cap_glyph_ids(doc, unresolved).items():
            cap, src = cap_height_em(buffers[f], gid)
            table[f].update(cap_height_em=cap, cap_height_source=src)
    # Still unknown (e.g. no flat-topped capital used in that face): borrow from a sibling
    # face of the same family (Calibri <- Calibri-Bold). Differences between faces are ~1%.
    for f, v in table.items():
        if v["cap_height_em"] is None:
            fam = f.split("-")[0].split(",")[0]
            sib = next((w for g, w in table.items() if g != f and w["cap_height_source"]
                        and w["cap_height_source"] != "family" and g.split("-")[0].split(",")[0] == fam), None)
            if sib:
                v.update(cap_height_em=sib["cap_height_em"], cap_height_source="family")
    return table


# ---------- PDF text runs ----------

def page_spans(page: pymupdf.Page) -> list[dict]:
    flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES
    spans = []
    for b, block in enumerate(page.get_text("dict", flags=flags)["blocks"]):
        for l, line in enumerate(block.get("lines", [])):
            for span in line["spans"]:
                if not span["text"].strip():
                    continue
                c = span["color"]
                spans.append({
                    "text": span["text"],
                    "font": span["font"],
                    "size_pt": round(span["size"], 3),
                    "bold": bool(span["flags"] & pymupdf.TEXT_FONT_BOLD),
                    "italic": bool(span["flags"] & pymupdf.TEXT_FONT_ITALIC),
                    "superscript": bool(span["flags"] & pymupdf.TEXT_FONT_SUPERSCRIPT),
                    "color": f"#{c:06x}",
                    "alpha": span.get("alpha", 255),
                    "bbox": [round(v, 2) for v in span["bbox"]],
                    "origin": [round(v, 2) for v in span["origin"]],
                    "dir": [round(v, 4) for v in line["dir"]],
                    "block": b,
                    "line": l,
                })
    return spans


# ---------- PPTX structure ----------

def _alt_text(shape) -> tuple[str | None, bool]:
    """(alt text, decorative) from the shape's cNvPr element."""
    el = shape._element
    cnv = el.xpath("./*[1]/p:cNvPr") or el.xpath(".//p:cNvPr")
    if not cnv:
        return None, False
    descr = cnv[0].get("descr") or None
    decorative = any(d.get("val") in ("1", "true") for d in cnv[0].xpath(".//*[local-name()='decorative']"))
    return descr, decorative


IMAGE_TYPES = {"PICTURE", "LINKED_PICTURE", "CHART", "MEDIA", "EMBEDDED_OLE_OBJECT",
               "LINKED_OLE_OBJECT", "DIAGRAM", "SMART_ART"}


def _chart_info(sh) -> dict | None:
    """Chart facts the agent uses for data-graphics judgments (DG-1)."""
    try:
        ch = sh.chart
    except Exception:
        return None
    # Read the XML directly: python-pptx can't open some plot types (3-D charts among them).
    C = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"
    chart_el = ch._chartSpace.find(f"{C}chart")
    area = chart_el.find(f"{C}plotArea")
    plots = [el for el in area if el.tag.endswith("Chart")]
    try:
        kind = str(ch.chart_type).split(".")[-1].split(" ")[0]
    except Exception:
        kind = plots[0].tag.replace(C, "") if plots else "unknown"  # e.g. 'bar3DChart'
    info = {"chart_type": kind,
            "has_title": chart_el.find(f"{C}title") is not None,
            "has_legend": chart_el.find(f"{C}legend") is not None,
            "series": sum(len(p.findall(f"{C}ser")) for p in plots)}
    info["is_3d"] = "THREE_D" in kind or "3D" in kind
    for axis, tags in (("category_axis", ("catAx", "dateAx")), ("value_axis", ("valAx",))):
        ax = next((a for t in tags for a in area.findall(f"{C}{t}")), None)
        if ax is None:  # pie and doughnut charts have no axes
            continue
        info[f"{axis}_title"] = ax.find(f"{C}title") is not None
        if axis == "value_axis":
            mn = ax.find(f"{C}scaling/{C}min")
            info["value_axis_min"] = float(mn.get("val")) if mn is not None else None  # None: automatic
    shown = [d for p in plots for d in p.iter(f"{C}dLbls")
             for v in d.findall(f"{C}showVal") + d.findall(f"{C}showPercent") if v.get("val") in ("1", "true")]
    info["data_labels"] = bool(shown)
    return info


def _media_kind(sh, st_name: str | None) -> str | None:
    """'image' for anything that needs alt text: pictures, charts, media, OLE objects, SmartArt,
    and placeholders filled with one of these. None otherwise."""
    if st_name in IMAGE_TYPES:
        return "image"
    if st_name == "PLACEHOLDER":
        if hasattr(sh, "image") or getattr(sh, "has_chart", False):
            try:
                if getattr(sh, "has_chart", False) or sh.image is not None:
                    return "image"
            except Exception:
                return None
        return None
    if st_name is None and sh._element.tag.endswith("graphicFrame"):
        return "image"  # SmartArt and other graphic frames python-pptx doesn't name
    return None


def _shape_records(shapes, in_group: bool = False, group: str | None = None) -> list[dict]:
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    out = []
    for sh in shapes:
        st = sh.shape_type
        is_group = st == MSO_SHAPE_TYPE.GROUP
        # Text boxes and any shape carrying text are covered by the PDF spans; record the rest
        # (pictures, charts, tables, SmartArt, groups, empty autoshapes) for alt-text checks.
        is_text = st == MSO_SHAPE_TYPE.TEXT_BOX or (sh.has_text_frame and sh.text_frame.text.strip())
        if not is_text:
            alt, deco = _alt_text(sh)
            bbox = None
            if not in_group and sh.width is not None:
                bbox = [round(v / EMU_PER_PT, 2) for v in
                        (sh.left, sh.top, sh.left + sh.width, sh.top + sh.height)]
            st_name = str(st).split(".")[-1].split(" ")[0] if st else None
            rec = {
                "name": sh.name,
                "type": st_name,
                "media": _media_kind(sh, st_name),  # "image" if it needs alt text
                "alt_text": alt,
                "decorative": deco,
                "bbox": bbox,  # PDF points; None inside groups (child coordinates)
                "in_group": in_group,
                "group": group,  # name of the enclosing top-level group
            }
            if getattr(sh, "has_chart", False):
                rec["chart"] = _chart_info(sh)
            out.append(rec)
        if is_group:
            out.extend(_shape_records(sh.shapes, in_group=True, group=group or sh.name))
    return out


A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
P_NS = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
PAINTS = ("solidFill", "gradFill", "pattFill", "blipFill")


def _visible_box(sh) -> tuple[bool, bool]:
    """(filled, outlined): whether a shape's own fill or outline shows, from its spPr, else its
    theme style reference (autoshapes are filled and outlined by default; text boxes are not)."""
    el = sh._element
    sp_pr = el.find(f"{P_NS}spPr")
    style = el.find(f"{P_NS}style")

    def ref_idx(tag):
        r = style.find(f"{A_NS}{tag}") if style is not None else None
        return int(r.get("idx", "0")) if r is not None else 0

    filled = outlined = False
    if sp_pr is not None:
        if sp_pr.find(f"{A_NS}noFill") is not None:
            filled = False
        elif any(sp_pr.find(f"{A_NS}{t}") is not None for t in PAINTS):
            filled = True
        else:
            filled = ref_idx("fillRef") > 0
        ln = sp_pr.find(f"{A_NS}ln")
        if ln is not None and ln.find(f"{A_NS}noFill") is not None:
            outlined = False
        elif ln is not None and any(ln.find(f"{A_NS}{t}") is not None for t in PAINTS):
            outlined = True
        else:
            outlined = ref_idx("lnRef") > 0
    return filled, outlined


def _text_box_records(shapes) -> list[dict]:
    """Top-level shapes with text: box, visible fill/outline, autofit. For overflow checks (LY-1)
    and text placed off the slide. Group members are skipped (child coordinates)."""
    out = []
    for sh in shapes:
        if not (sh.has_text_frame and sh.text_frame.text.strip()) or sh.width is None or sh.left is None:
            continue
        body = sh._element.find(f".//{A_NS}bodyPr")
        autofit = None
        if body is not None:
            autofit = ("shape" if body.find(f"{A_NS}spAutoFit") is not None else
                       "shrink" if body.find(f"{A_NS}normAutofit") is not None else None)
        filled, outlined = _visible_box(sh)
        out.append({"name": sh.name, "text": sh.text_frame.text[:300],
                    "bbox": [round(v / EMU_PER_PT, 2) for v in
                             (sh.left, sh.top, sh.left + sh.width, sh.top + sh.height)],
                    "filled": filled, "outlined": outlined, "autofit": autofit})
    return out


def pptx_structure(src: Path) -> dict | None:
    if src.suffix.lower() not in {".pptx", ".pptm"} or not src.exists():
        return None
    from pptx import Presentation
    prs = Presentation(str(src))

    slides = []
    for i, s in enumerate(prs.slides, 1):
        title_shape = s.shapes.title
        title = title_shape.text_frame.text if title_shape is not None else None
        # reading order = shape order; position of the title among shapes a screen reader announces
        announced = [sh for sh in s.shapes
                     if (sh.has_text_frame and sh.text_frame.text.strip()) or sh.shape_type is not None
                     and str(sh.shape_type).split(".")[-1].split(" ")[0] in IMAGE_TYPES | {"GROUP", "TABLE"}]
        title_order = next((i for i, sh in enumerate(announced)
                            if title_shape is not None and sh.shape_id == title_shape.shape_id), None)
        slides.append({
            "index": i,
            "hidden": s._element.get("show") in ("0", "false"),
            "title": title,
            "layout": s.slide_layout.name,
            "title_order": title_order,  # 0 = read first; None = no title placeholder
            "shapes": _shape_records(s.shapes),
            "text_boxes": _text_box_records(s.shapes),
            "has_notes": s.has_notes_slide and bool(s.notes_slide.notes_text_frame.text.strip()),
        })
    return {"slides": slides}


# ---------- main ----------

def extract(out_dir: Path) -> Path:
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    doc = pymupdf.open(out_dir / manifest["pdf"])
    fonts = font_table(doc)
    pages = [{"index": i + 1, "width_pt": p.rect.width, "height_pt": p.rect.height,
              "spans": page_spans(p)} for i, p in enumerate(doc)]
    result = {
        "manifest_version": manifest["manifest_version"],
        "source": manifest["source"],
        "fonts": fonts,
        "pages": pages,
        "pptx": pptx_structure(Path(manifest["source"])),
    }
    path = out_dir / "text.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "outline.md").write_text(outline(result, manifest), encoding="utf-8")
    return path


def outline(result: dict, manifest: dict) -> str:
    """Compact per-page text (one line per text block) for reading the content as a whole."""
    hidden = {p["index"]: p["hidden"] for p in manifest["pages"]}
    titles = {s["index"]: s["title"] for s in (result.get("pptx") or {}).get("slides", [])}
    unit = "Slide" if manifest.get("kind_guess") == "slides" else "Page"
    lines = [f"# Outline: {Path(manifest['source']).name}", ""]
    page_blocks = []
    for p in result["pages"]:
        blocks: dict[int, list[str]] = {}
        for s in p["spans"]:
            blocks.setdefault(s["block"], []).append(s["text"].strip())
        page_blocks.append([" ".join(t for t in texts if t) for texts in blocks.values()])
    # Drop footers: block text repeated on many pages, and bare page numbers.
    norm = lambda t: re.sub(r"\d+", "#", t)  # noqa: E731
    counts: dict[str, int] = {}
    for blocks in page_blocks:
        for t in {norm(b) for b in blocks}:
            counts[t] = counts.get(t, 0) + 1
    min_repeat = max(3, len(page_blocks) // 4)
    dropped = sorted({b for blocks in page_blocks for b in blocks if counts[norm(b)] >= min_repeat
                      and not re.fullmatch(r"\d{1,3}", b)})
    if dropped and len(page_blocks) >= 3:
        lines += [f"Repeated on most pages (omitted below): {'; '.join(d[:80] for d in dropped[:5])}", ""]
    for p, blocks in zip(result["pages"], page_blocks):
        flag = " (hidden)" if hidden.get(p["index"]) else ""
        title = titles.get(p["index"])
        lines.append(f"## {unit} {p['index']}{flag}" + (f": {title}" if title else ""))
        for text in blocks:
            if (not text or text == title or re.fullmatch(r"\d{1,3}", text)
                    or (len(page_blocks) >= 3 and counts[norm(text)] >= min_repeat)):
                continue
            lines.append(f"- {text[:300]}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    out_dir = Path(argv[0])
    if not (out_dir / "manifest.json").exists():
        print(f"error: no manifest.json in {out_dir}; run render.py first", file=sys.stderr)
        return 2
    print(extract(out_dir))
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # Windows consoles and pipes default to cp1252
        stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
