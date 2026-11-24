"""Extract text runs (and PPTX structure) from a render.py output directory.

Usage:
    python scripts/extract_text.py OUTPUT_DIR

Reads OUTPUT_DIR/manifest.json and source.pdf; writes OUTPUT_DIR/text.json with:
    fonts   per PDF font: base name, cap height (em) from embedded font metrics when available
    pages   per page: spans with text, font, size_pt, bold/italic, color (#rrggbb), alpha,
            bbox and origin (PDF points, origin top-left), direction
    pptx    (PPTX sources only) per slide: hidden, title, layout, notes, and non-text shapes
            with alt text / decorative flags. (Font substitution is reported in manifest.json.)

Not included (needs OCR; see the contrast/OCR step): text inside images, and text the PDF
draws as outlines (e.g. PowerPoint exports rotated chart axis labels as filled paths).
"""
from __future__ import annotations

import io
import json
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


def _shape_records(shapes, in_group: bool = False) -> list[dict]:
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
            out.append({
                "name": sh.name,
                "type": str(st).split(".")[-1].split(" ")[0] if st else None,
                "alt_text": alt,
                "decorative": deco,
                "bbox": bbox,  # PDF points; None inside groups (child coordinates)
                "in_group": in_group,
            })
        if is_group:
            out.extend(_shape_records(sh.shapes, in_group=True))
    return out


def pptx_structure(src: Path) -> dict | None:
    if src.suffix.lower() not in {".pptx", ".pptm"} or not src.exists():
        return None
    from pptx import Presentation
    prs = Presentation(str(src))

    slides = []
    for i, s in enumerate(prs.slides, 1):
        title = s.shapes.title.text_frame.text if s.shapes.title is not None else None
        slides.append({
            "index": i,
            "hidden": s._element.get("show") in ("0", "false"),
            "title": title,
            "layout": s.slide_layout.name,
            "shapes": _shape_records(s.shapes),
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
    return path


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
    sys.exit(main())
