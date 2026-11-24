"""Extract text runs (and PPTX structure) from a render.py output directory.

Usage:
    python scripts/extract_text.py OUTPUT_DIR

Reads OUTPUT_DIR/manifest.json and source.pdf; writes OUTPUT_DIR/text.json with:
    fonts   per PDF font: base name, cap height (em) from embedded font metrics when available
    pages   per page: spans with text, font, size_pt, bold/italic, color (#rrggbb), alpha,
            bbox and origin (PDF points, origin top-left), direction
    pptx    (PPTX sources only) per slide: hidden, title, non-text shapes with alt text /
            decorative flags; requested fonts and which of them are missing from the PDF
            (i.e. substituted by the renderer)

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

def cap_height_em(buf: bytes) -> tuple[float | None, str | None]:
    """Cap height as a fraction of the em, and where it came from ('os2' or 'glyph')."""
    try:
        from fontTools.ttLib import TTFont
        font = TTFont(io.BytesIO(buf), lazy=True)
        upm = font["head"].unitsPerEm
        os2 = font["OS/2"] if "OS/2" in font else None
        if os2 is not None and os2.version >= 2 and getattr(os2, "sCapHeight", 0) > 0:
            return os2.sCapHeight / upm, "os2"
        if "glyf" in font:
            cmap = font.getBestCmap() or {}
            for ch in FLAT_TOP_CAPS:
                g = cmap.get(ord(ch))
                if g:
                    glyph = font["glyf"][g]
                    if getattr(glyph, "yMax", 0) > 0:
                        return glyph.yMax / upm, "glyph"
    except Exception:
        pass  # bare CFF / Type1 / Type3 fonts: leave to the default
    return None, None


def font_table(doc: pymupdf.Document) -> dict[str, dict]:
    """PDF font name (as it appears in spans) -> metrics."""
    table: dict[str, dict] = {}
    for page in doc:
        for xref, ext, ftype, name, *_ in page.get_fonts():
            base = base_font_name(name)
            if base in table:
                continue
            cap, src = None, None
            if xref:
                try:
                    _, _, _, buf = doc.extract_font(xref)
                    if buf:
                        cap, src = cap_height_em(buf)
                except Exception:
                    pass
            table[base] = {"type": ftype, "embedded": ext not in ("n/a", ""),
                           "cap_height_em": cap, "cap_height_source": src}
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

def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


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


def _theme_fonts(prs) -> dict[str, str]:
    """Theme major/minor latin fonts, keyed by the '+mj-lt' / '+mn-lt' aliases runs use."""
    from pptx.opc.constants import RELATIONSHIP_TYPE as RT
    fonts = {}
    try:
        theme = prs.slide_master.part.part_related_by(RT.THEME)
        xml = theme.blob.decode("utf-8", "replace")
        for key, tag in (("+mj-lt", "majorFont"), ("+mn-lt", "minorFont")):
            m = re.search(rf"<a:{tag}>\s*<a:latin typeface=\"([^\"]+)\"", xml)
            if m:
                fonts[key] = m.group(1)
    except Exception:
        pass
    return fonts


def pptx_structure(src: Path, pdf_fonts: list[str]) -> dict | None:
    if src.suffix.lower() not in {".pptx", ".pptm"} or not src.exists():
        return None
    from pptx import Presentation
    prs = Presentation(str(src))
    theme = _theme_fonts(prs)
    requested = set(theme.values())
    for xml_part in [prs.slide_master.part] + [s.part for s in prs.slides]:
        for typeface in xml_part._element.xpath(".//a:latin/@typeface"):
            requested.add(theme.get(typeface, typeface))
    requested = {f for f in requested if f and not f.startswith("+")}
    pdf_norm = [_norm(f) for f in pdf_fonts]
    missing = sorted(f for f in requested if not any(p.startswith(_norm(f)) for p in pdf_norm))

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
    return {
        "theme_fonts": theme,
        "requested_fonts": sorted(requested),
        # Requested fonts not found in the PDF: either unused or substituted by the renderer.
        "fonts_not_in_pdf": missing,
        "slides": slides,
    }


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
        "pptx": pptx_structure(Path(manifest["source"]), manifest["pdf_fonts"])
        if manifest["source_type"] == "pptx" else None,
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
