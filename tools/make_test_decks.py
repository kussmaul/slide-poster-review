"""Dev tool: generate small decks with known flaws, plus the levels each should get.

Usage:
    python tools/make_test_decks.py [OUT_DIR]        # default: tests/decks/ (tracked)

tests/decks/ is committed so that the decks evals and tests refer to can be opened directly;
a test regenerates them and fails if the committed copies differ. After changing this file,
run it with no arguments and commit the updated decks.

Writes, for each deck, NAME.pptx and NAME.expected.json:
    flaws-slides.pptx   16:9 slides: text size and contrast, one flaw per slide, plus controls
    flaws-poster.pptx   48x36 in poster: the same flaws as text blocks, plus a red-green chart
    flaws-color.pptx    16:9 slides: colors confusable with color-vision deficiency,
                        emphasis by color alone, links, plus controls
    flaws-text.pptx     16:9 slides: sentence length, acronyms, rare words, plus controls
    flaws-structure.pptx 16:9 slides with real title placeholders: colliding and cut-off text,
                        title hierarchy, alt text, missing titles, reading order, plus controls
    flaws-4x3.pptx      4:3 slides with a footer and slide number on every slide: text size
                        (same levels as 16:9, since both are 7.5 in high), footers as supporting
                        text, and bullets that overflow their box into the footer
    flaws-poster-half.pptx  24x18 in poster file printed at 48x36 in ("print_size"): sizes
                        double when printed
    judged-clear.pptx, judged-poor.pptx  the same short talk done well and badly, and
    judged-middle.pptx  another talk with mixed signals (levels 2-3), judged-low.pptx a third
                        aimed at Level 2 on every item, for evals of
                        the agent's judged items (tools/eval_judgments.py)
    judged-poster-clear.pptx, judged-poster-middle.pptx, judged-poster-poor.pptx
                        conference posters at levels 3-4, 2-3 and 1-2, judged with the
                        conference-poster example rubric

expected.json: {"deck", "kind", "expect": [...]}, each expectation
    {"measure": "font_size" | "contrast" | "color" | "readability", "page": n,
     "key": "body" | "supporting" | "CO-1" | "CO-2" | "RD-2" | "LY-1" | "LY-2",
     "level": n  (or "max_level": n), "marker": "text in the block" (posters), "note": "..."}
    "items" (optional): {item id: level} for deck-level items, e.g. RD-1, RD-3, AC-1.
"print_size" (optional): passed to font_size and contrast, as the user would give it.
"judged" (optional): {item id: [lowest, highest] acceptable level} for the agent's judgments,
"key_ideas": one keyword list per key idea (a stated key idea matches if it contains any
keyword), "intake": the user's answers at intake (context rubric, time limit), and "omit": items
the agent must leave out because an intake fact is missing. Checked by tools/eval_judgments.py,
not by the tests.
"level" is exact; "max_level" means "this flaw is found" where the exact level depends on
rendering (e.g. OCR). Hidden slides are listed under "hidden" and must not be scored.

Sizes use Arial (cap height 0.716 em). Slides at 8H, posters at 1.5 m printed 48x36 in:
    Level 4 >= 40 pt   Level 3 28-38 pt   Level 2 18-27 pt   Level 1 <= 16 pt   (both)
Output is byte-for-byte reproducible, so cached renders are reused.
"""
from __future__ import annotations

import io
import json
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import pymupdf
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
FONT = "Arial"


# ---------- helpers ----------

def rgb(h: str) -> RGBColor:
    return RGBColor.from_string(h.lstrip("#").upper())


def text(slide, x, y, w, h, paras, size=32, color="#000000", bold=False, fill=None):
    """Text box at inches. paras: list of str, or list of runs [(text, {size,color,bold,underline,link})]."""
    if fill:
        shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
        shp.fill.solid()
        shp.fill.fore_color.rgb = rgb(fill)
        shp.line.fill.background()
    else:
        shp = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = shp.text_frame
    tf.word_wrap = True
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        runs = [(para, {})] if isinstance(para, str) else para
        for t, opt in runs:
            r = p.add_run()
            r.text = t
            f = r.font
            f.name = FONT
            f.size = Pt(opt.get("size", size))
            f.bold = opt.get("bold", bold)
            f.color.rgb = rgb(opt.get("color", color))
            if "underline" in opt:
                f.underline = opt["underline"]
            if opt.get("link"):
                r.hyperlink.address = opt["link"]
    return shp


def png_gradient(path: Path, w=1200, h=300) -> Path:
    """Horizontal gradient, dark to light: text over it has no single background."""
    row = np.linspace(20, 235, w).astype(np.uint8)
    arr = np.ascontiguousarray(np.repeat(np.repeat(row[None, :, None], h, 0), 3, 2))
    pymupdf.Pixmap(pymupdf.csRGB, w, h, arr.tobytes(), False).save(path)
    return path


def png_text(path: Path, lines: list[str], fontsize: float, color=(0.55, 0.55, 0.55),
             w_pt=400, h_pt=120, zoom=2) -> Path:
    """Text rendered into a picture (not selectable): found only by OCR."""
    doc = pymupdf.open()
    page = doc.new_page(width=w_pt, height=h_pt)
    for i, line in enumerate(lines):
        page.insert_text((10, 10 + fontsize * (i + 1) * 1.3), line, fontsize=fontsize,
                         fontname="helv", color=color)
    page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).save(path)
    return path


def chart(slide, x, y, w, h, colors, label_size=14, legend=True, labels=False):
    data = CategoryChartData()
    data.categories = ["2023", "2024", "2025"]
    data.add_series("Group A", (42, 55, 61))
    data.add_series("Group B", (38, 47, 70))
    gf = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(x), Inches(y),
                                Inches(w), Inches(h), data)
    ch = gf.chart
    ch.font.name = FONT
    ch.font.size = Pt(label_size)
    ch.has_legend = legend
    if legend:
        ch.legend.position = XL_LEGEND_POSITION.BOTTOM
        ch.legend.include_in_layout = False
    for s, c in zip(ch.plots[0].series, colors):
        s.format.fill.solid()
        s.format.fill.fore_color.rgb = rgb(c)
    if labels:
        ch.plots[0].has_data_labels = True
        ch.plots[0].data_labels.font.size = Pt(label_size)
    return ch


def blank(prs, hidden=False):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    if hidden:
        s._element.set("show", "0")
    return s


def _fixed_zip(data: bytes) -> bytes:
    """Rewrite a zip (pptx, or a chart's embedded xlsx) with fixed timestamps and dates."""
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            body = src.read(info.filename)
            if info.filename.endswith(".xlsx"):
                body = _fixed_zip(body)
            elif info.filename.endswith("core.xml"):
                body = re.sub(rb"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", b"2020-01-01T00:00:00Z", body)
            zi = zipfile.ZipInfo(info.filename, date_time=(2020, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            dst.writestr(zi, body)
    return out.getvalue()


def save(prs, path: Path) -> None:
    """Save reproducibly (same bytes every run), so cached renders are reused."""
    buf = io.BytesIO()
    prs.save(buf)
    path.write_bytes(_fixed_zip(buf.getvalue()))


def slides_prs():
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    return prs


def titled(prs, title, hidden=False):
    s = blank(prs, hidden)
    text(s, 0.6, 0.4, 12, 1.2, [title], size=44)
    return s


def bullets(items):
    return [f"• {t}" for t in items]


# ---------- decks ----------

def make_slides(out: Path, tmp: Path) -> dict:
    prs, exp = slides_prs(), []

    def e(page, measure, key, level=None, max_level=None, note=""):
        d = {"measure": measure, "page": page, "key": key, "note": note}
        d.update({"level": level} if level is not None else {"max_level": max_level})
        exp.append(d)

    s = blank(prs)
    text(s, 0.8, 2.2, 11.5, 1.5, ["Generated test deck: text size and contrast"], size=54, bold=True)
    text(s, 0.8, 4.0, 11.5, 1.0, ["Each slide has one known flaw"], size=40)
    e(1, "font_size", "body", 4, note="54 pt title, 40 pt subtitle")
    e(1, "contrast", "body", 4)

    s = titled(prs, "Control: large black text")
    text(s, 0.8, 2.0, 11.5, 4.5, bullets(["Body text at 40 points", "Black on white"]), size=40)
    e(2, "font_size", "body", 4, note="40 pt")
    e(2, "contrast", "body", 4, note="21:1")

    for page, size, level in ((3, 32, 3), (4, 22, 2), (5, 14, 1)):
        s = titled(prs, f"Bullets at {size} points")
        text(s, 0.8, 2.0, 11.5, 4.5, bullets(["The first point on this slide",
                                              "A second point with more words in it",
                                              "A third and final point"]), size=size)
        e(page, "font_size", "body", level, note=f"{size} pt bullets")

    s = titled(prs, "Small citation")
    text(s, 0.8, 2.0, 11.5, 3.0, bullets(["Body text at 32 points", "Citation below is 10 points"]), size=32)
    text(s, 0.8, 6.6, 11.5, 0.5, ["Source: Smith et al. (2020), Journal of Examples 12(3)."], size=10)
    e(6, "font_size", "body", 3)
    e(6, "font_size", "supporting", 1, note="10 pt citation")

    for page, grey, level, ratio in ((7, "#999999", 1, "2.84"), (8, "#808080", 2, "3.94"),
                                     (9, "#6b6b6b", 3, "5.33")):
        s = titled(prs, f"Grey text {grey}")
        text(s, 0.8, 2.0, 11.5, 4.5, bullets([f"This text is {grey} on white",
                                              f"Contrast about {ratio}:1"]), size=32, color=grey)
        e(page, "contrast", "body", level, note=f"{grey} on white, {ratio}:1")

    s = titled(prs, "White text on orange")
    text(s, 0.8, 2.0, 11.5, 3.0, bullets(["White text on an orange box", "Contrast about 2.9:1"]),
         size=32, color="#ffffff", fill="#ed7d31")
    e(10, "contrast", "body", 1, note="white on #ed7d31")

    s = titled(prs, "Text over a gradient")
    s.shapes.add_picture(str(png_gradient(tmp / "gradient.png")), Inches(0.8), Inches(2.2),
                         Inches(11.5), Inches(2.9))
    text(s, 1.0, 3.0, 11, 1.2, ["Black text across a dark-to-light gradient"], size=32)
    e(11, "contrast", "body", 1, note="black over the dark end of a gradient")

    s = titled(prs, "Text inside a picture")
    s.shapes.add_picture(str(png_text(tmp / "picture-text.png",
                                      ["Small grey words inside a picture",
                                       "found only by text recognition"], 14)),
                         Inches(0.8), Inches(2.2), Inches(5.5))
    e(12, "font_size", "body", max_level=2, note="text in an image, about 13 pt on the slide (OCR)")
    e(12, "contrast", "body", max_level=3, note="grey text in an image (OCR)")

    s = titled(prs, "Hidden slide with tiny grey text", hidden=True)
    text(s, 0.8, 2.0, 11.5, 3.0, ["This slide is hidden and must not be scored"], size=10, color="#bbbbbb")

    save(prs, out / "flaws-slides.pptx")
    return {"deck": "flaws-slides.pptx", "kind": "slides", "hidden": [13], "expect": exp}


def make_poster(out: Path, tmp: Path) -> dict:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(48), Inches(36)
    s = blank(prs)
    exp = []

    def e(marker, measure, key, level=None, max_level=None, note=""):
        d = {"measure": measure, "page": 1, "marker": marker, "key": key, "note": note}
        d.update({"level": level} if level is not None else {"max_level": max_level})
        exp.append(d)

    text(s, 1, 0.8, 46, 3, ["Generated test poster: known flaws"], size=110, bold=True)
    e("Generated test poster", "font_size", "body", 4)
    para = ("This block of text describes one part of the poster in a few sentences so that "
            "it wraps over several lines.")
    col = [(1, 5), (17, 5), (33, 5), (1, 15), (17, 15), (33, 15)]
    blocks = [("Introduction at 40 points.", 40, "#000000", None, ("font_size", 4), ("contrast", 4)),
              ("Methods at 32 points.", 32, "#000000", None, ("font_size", 3), None),
              ("Results at 22 points.", 22, "#000000", None, ("font_size", 2), None),
              ("Details at 14 points.", 14, "#000000", None, ("font_size", 1), None),
              ("Discussion in light grey.", 32, "#aaaaaa", None, None, ("contrast", 1)),
              ("Conclusion in white on yellow.", 32, "#ffffff", "#ffc000", None, ("contrast", 1))]
    for (x, y), (marker, size, color, fill, fs_exp, ct_exp) in zip(col, blocks):
        text(s, x, y, 14, 9, [marker + " " + para], size=size, color=color, fill=fill)
        for ex in (fs_exp, ct_exp):
            if ex:
                e(marker, ex[0], "body", ex[1])
    text(s, 1, 31, 30, 3, ["References: Smith, J., et al. (2020). An example reference. "
                           "Journal of Examples, 12(3), 45-67."], size=14)
    e("References:", "font_size", "supporting", 1, note="14 pt citation")
    ch = chart(s, 33, 25, 14, 9, ["#c05040", "#609040"], label_size=14, legend=True)
    e(None, "color", "CO-1", 2, note="red/green chart series, deuteranopia")
    e("Group A", "font_size", "body", 1, note="14 pt chart labels")
    text(s, 1, 25, 30, 5, [[("Sentences with one ", {}), ("highlighted", {"color": "#c00000"}),
                            (" word in red show emphasis by color alone.", {})]], size=40)
    e(None, "color", "CO-2", 3, note="red word in black text, lightness ratio above 3:1")
    del ch
    save(prs, out / "flaws-poster.pptx")
    return {"deck": "flaws-poster.pptx", "kind": "poster", "hidden": [], "expect": exp}


def make_color(out: Path, tmp: Path) -> dict:
    prs, exp = slides_prs(), []

    def e(page, key, level, note=""):
        exp.append({"measure": "color", "page": page, "key": key, "level": level, "note": note})

    s = blank(prs)
    text(s, 0.8, 2.2, 11.5, 1.5, ["Generated test deck: use of color"], size=54, bold=True)
    e(1, "CO-1", 4)
    e(1, "CO-2", 4)

    s = titled(prs, "Control: blue and orange")
    chart(s, 0.8, 1.8, 11.5, 5.2, ["#0072b2", "#e69f00"], label_size=24, labels=True)
    e(2, "CO-1", 4, "Okabe-Ito blue/orange: safe")

    s = titled(prs, "Red and green chart")
    chart(s, 0.8, 1.8, 11.5, 5.2, ["#c05040", "#609040"], label_size=24)
    e(3, "CO-1", 2, "red/green series: deuteranopia")

    s = titled(prs, "Legend by color alone")
    for x, c in ((1.5, "#634c30"), (7.5, "#3c693c")):
        dot = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(2.0), Inches(3.5), Inches(3.5))
        dot.fill.solid()
        dot.fill.fore_color.rgb = rgb(c)
        dot.line.fill.background()
    text(s, 0.8, 6.0, 11.5, 1, ["Brown circles failed; green circles passed."], size=32)
    e(4, "CO-1", 1, "brown/green: confusable even with moderate deuteranomaly")

    s = titled(prs, "Blue and green boxes")
    for x, c in ((1.5, "#66aadd"), (7.5, "#77bb99")):
        b = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(2.0), Inches(4), Inches(3.5))
        b.fill.solid()
        b.fill.fore_color.rgb = rgb(c)
        b.line.fill.background()
    e(5, "CO-1", 3, "blue/green: tritanopia only")

    s = titled(prs, "Red word in black text")
    text(s, 0.8, 2.0, 11.5, 3, [[("The key result is that scores ", {}),
                                 ("improved", {"color": "#c00000"}), (" for every group.", {})]], size=36)
    e(6, "CO-2", 3, "#c00000 in black: lightness ratio about 3.2")

    s = titled(prs, "Green word in brown text")
    text(s, 0.8, 2.0, 11.5, 3, [[("The key result is that scores ", {}),
                                 ("improved", {"color": "#3c693c"}), (" for every group.", {})]],
         size=36, color="#634c30")
    e(7, "CO-2", 1, "#3c693c in #634c30: similar lightness; alike with deuteranopia")

    s = titled(prs, "Green word in grey text")
    text(s, 0.8, 2.0, 11.5, 3, [[("The key result is that scores ", {}),
                                 ("improved", {"color": "#2e8b57"}), (" for every group.", {})]],
         size=36, color="#7a5a5a")
    e(8, "CO-2", 2, "#2e8b57 in #7a5a5a: lightness ratio under 3:1, distinct in simulations")

    s = titled(prs, "Control: bold and colored")
    text(s, 0.8, 2.0, 11.5, 3, [[("The key result is that scores ", {}),
                                 ("improved", {"color": "#c00000", "bold": True}),
                                 (" for every group.", {})]], size=36)
    e(9, "CO-2", 4, "bold as well as color")

    s = titled(prs, "Colored link text, not underlined")
    text(s, 0.8, 2.0, 11.5, 3, [[("See the ", {}), ("course website", {"color": "#4472c4"}),
                                 (" for details.", {})]], size=36, color="#404040")
    e(10, "CO-2", 2, "blue words in dark grey: lightness ratio under 3:1")

    s = titled(prs, "Control: underlined link")
    text(s, 0.8, 2.0, 11.5, 3, [[("See the ", {}),
                                 ("course website", {"color": "#4472c4", "underline": True,
                                                     "link": "https://example.org/course"}),
                                 (" for details.", {})]], size=36, color="#404040")
    e(11, "CO-2", 4, "link is underlined")

    s = titled(prs, "Hidden slide with red and green", hidden=True)
    chart(s, 0.8, 1.8, 11.5, 5.2, ["#c05040", "#609040"], label_size=24)

    save(prs, out / "flaws-color.pptx")
    return {"deck": "flaws-color.pptx", "kind": "slides", "hidden": [12], "expect": exp}


def make_text(out: Path, tmp: Path) -> dict:
    prs, exp = slides_prs(), []

    def e(page, level, note=""):
        exp.append({"measure": "readability", "page": page, "key": "RD-2", "level": level, "note": note})

    s = blank(prs)
    text(s, 0.8, 2.2, 11.5, 1.5, ["Generated test deck: readability"], size=54, bold=True)
    e(1, 4)

    s = titled(prs, "Control: short plain bullets")
    text(s, 0.8, 2.0, 11.5, 4.5, bullets(["Read the page", "Talk with your team",
                                          "Write one new idea"]), size=36)
    e(2, 4, "three short bullets")

    for page, n, level in ((3, 18, 3), (4, 26, 2), (5, 36, 1)):
        words = ("Students in each small team read the short text together and then they write "
                 "down the main idea of the story in their own words before they share it with "
                 "the rest of the class at the end of the day").split()
        s = titled(prs, f"One sentence of {n} words")
        text(s, 0.8, 2.0, 11.5, 4.5, [" ".join(words[:n]) + "."], size=32)
        e(page, level, f"{n}-word sentence, wrapped over several lines")

    s = titled(prs, "Defined acronyms")
    text(s, 0.8, 2.0, 11.5, 4.5, bullets(["Think-Pair-Share (TPS) is a short activity",
                                          "PLTL (Peer-Led Team Learning) uses student leaders",
                                          "Use TPS and PLTL in class"]), size=32)
    e(6, 4)

    s = titled(prs, "Undefined acronyms")
    text(s, 0.8, 2.0, 11.5, 4.5, bullets(["Check the XQZ before class", "Send the BRV to your team"]),
         size=32)
    e(7, 4, "two acronyms that are never spelled out")

    s = titled(prs, "Rare words")
    text(s, 0.8, 2.0, 11.5, 4.5, bullets(["Ubiquitous heuristics obfuscate epistemological paradigms",
                                          "Recalcitrant ontologies engender pedagogical dissonance"]),
         size=32)
    e(8, 4, "off-list and C-level words")

    s = titled(prs, "Not problems")
    text(s, 0.8, 2.0, 11.5, 4.5, bullets(["Don't forget: search with AND, OR, and NOT",
                                          "Ask for help at help@example.org",
                                          "Maria and Kenji teachers' notes, 2nd edition"]), size=32)
    e(9, 4, "contractions, capitals, email, names, ordinals")

    s = titled(prs, "Hidden slide with a long sentence", hidden=True)
    text(s, 0.8, 2.0, 11.5, 4.5, ["This hidden slide has one very long sentence that goes on and on "
                                  "with many words about the ZZQ so that it would fail the sentence "
                                  "length check if hidden slides were scored by mistake."], size=24)

    save(prs, out / "flaws-text.pptx")
    return {"deck": "flaws-text.pptx", "kind": "slides", "hidden": [10], "expect": exp,
            "items": {"RD-1": 2, "RD-2": 1, "RD-3": 3}}


def _titled_layout(prs, title, body=None, title_size=None, body_size=28, hidden=False):
    """Slide from the 'Title and Content' (or 'Title Only') layout, with a real title placeholder."""
    s = prs.slides.add_slide(prs.slide_layouts[1 if body else 5])
    if hidden:
        s._element.set("show", "0")
    s.shapes.title.text = title
    for r in s.shapes.title.text_frame.paragraphs[0].runs:
        r.font.name = FONT
        if title_size:
            r.font.size = Pt(title_size)
    if body:
        ph = s.placeholders[1]
        for i, t in enumerate(body):
            para = ph.text_frame.paragraphs[0] if i == 0 else ph.text_frame.add_paragraph()
            run = para.add_run()
            run.text = t
            run.font.name = FONT
            run.font.size = Pt(body_size)
    return s


def _picture(slide, path, x, y, w, alt=None, decorative=False):
    pic = slide.shapes.add_picture(str(path), Inches(x), Inches(y), Inches(w))
    cnv = pic._element.nvPicPr.cNvPr
    cnv.set("descr", alt or "")
    if decorative:
        from lxml import etree
        ext_lst = etree.SubElement(cnv, "{http://schemas.openxmlformats.org/drawingml/2006/main}extLst")
        ext = etree.SubElement(ext_lst, "{http://schemas.openxmlformats.org/drawingml/2006/main}ext",
                               uri="{C183D7F6-B498-43B3-948B-1728B52AA6E4}")
        etree.SubElement(ext, "{http://schemas.microsoft.com/office/drawing/2017/decorative}decorative", val="1")
    return pic


def make_structure(out: Path, tmp: Path) -> dict:
    prs, exp = slides_prs(), []
    grad = png_gradient(tmp / "gradient.png")

    def e(page, key, level, note=""):
        exp.append({"measure": "layout", "page": page, "key": key, "level": level, "note": note})

    s = prs.slides.add_slide(prs.slide_layouts[0])
    s.shapes.title.text = "Generated test deck: layout and structure"
    s.placeholders[1].text = "Each slide has one known flaw"
    e(1, "LY-1", 4)

    s = _titled_layout(prs, "Control: title, bullets, described picture",
                       ["Short first point", "Short second point"])
    _picture(s, grad, 7.5, 4.8, 5, alt="A gradient from dark blue to white")
    e(2, "LY-1", 4)
    e(2, "LY-2", 4, "44 pt title over 28 pt body")

    s = _titled_layout(prs, "Picture without alt text", ["The picture below has no description"])
    _picture(s, grad, 1, 4.5, 6)

    s = _titled_layout(prs, "Decorative picture", ["The picture below is marked decorative"])
    _picture(s, grad, 1, 4.5, 6, decorative=True)

    s = blank(prs)
    text(s, 0.6, 0.4, 12, 1.2, ["A title in a text box, not a placeholder"], size=44)
    text(s, 0.8, 2.0, 11.5, 3, ["Screen readers find no title on this slide"], size=28)

    s = _titled_layout(prs, "Title read after a picture", ["The picture comes first in reading order"])
    pic = _picture(s, grad, 7.5, 4.8, 5, alt="A gradient")
    tree = s.shapes._spTree
    tree.remove(pic._element)
    tree.insert(2, pic._element)

    s = _titled_layout(prs, "Body text runs into the footer", ["Short first point"])
    text(s, 0.8, 6.6, 6, 0.6, ["Footer text at the bottom"], size=16, color="#444444")
    text(s, 0.8, 6.45, 11, 0.8, ["A note placed on top of the footer"], size=28, color="#000000")
    e(7, "LY-1", 1, "two text boxes overlap")

    s = _titled_layout(prs, "Text cut off at the bottom", ["Short first point"])
    text(s, 0.8, 6.95, 11.5, 1.2, ["This line is cut off by the bottom edge of the slide"], size=36)
    e(8, "LY-1", 1, "text box extends past the slide")

    s = _titled_layout(prs, "Small title", ["Body text larger than the title"], title_size=24, body_size=40)
    e(9, "LY-2", 1, "24 pt title over 40 pt body")

    s = _titled_layout(prs, "Words hidden under a label", ["Short first point"])
    text(s, 0.8, 4.5, 11, 1, ["These words are hidden under a white label"], size=28, color="#000000")
    text(s, 0.6, 4.4, 12, 1.2, ["A white label on top"], size=28, color="#000000", fill="#ffffff")
    e(10, "LY-1", 4, "covered text is not a visible collision")

    s = _titled_layout(prs, "Hidden slide with colliding text", ["Short first point"], hidden=True)
    text(s, 0.8, 4.5, 11, 1, ["Overlapping words one"], size=28)
    text(s, 0.8, 4.55, 11, 1, ["Overlapping words two"], size=28)

    save(prs, out / "flaws-structure.pptx")
    return {"deck": "flaws-structure.pptx", "kind": "slides", "hidden": [11], "expect": exp,
            "items": {"AC-1": 2, "AC-2": 3, "AC-3": 2}}


def make_4x3(out: Path, tmp: Path) -> dict:
    prs, exp = Presentation(), []  # python-pptx default: 10 x 7.5 in (4:3)
    assert (prs.slide_width, prs.slide_height) == (Inches(10), Inches(7.5))

    def e(page, measure, key, level, note=""):
        exp.append({"measure": measure, "page": page, "key": key, "level": level, "note": note})

    def footer(s, n):
        text(s, 0.5, 6.85, 6, 0.5, ["Generated test deck, 4:3 slides"], size=20)
        text(s, 8.8, 6.85, 0.8, 0.5, [str(n)], size=20)
        e(n, "font_size", "supporting", 2, "20 pt footer and slide number")

    def head(s, title):
        text(s, 0.5, 0.4, 9, 1.2, [title], size=44)

    s = blank(prs)
    text(s, 0.6, 2.2, 8.8, 1.5, ["Generated test deck: 4:3 slides"], size=54, bold=True)
    text(s, 0.6, 4.0, 8.8, 1.0, ["Footers on every slide"], size=40)
    footer(s, 1)
    e(1, "font_size", "body", 4)

    s = blank(prs)
    head(s, "Control: large black text")
    text(s, 0.6, 2.0, 8.8, 4.0, bullets(["Body text at 40 points", "Black on white"]), size=40)
    footer(s, 2)
    e(2, "font_size", "body", 4, "40 pt: the same level as on 16:9 slides of the same height")
    e(2, "contrast", "body", 4)
    e(2, "contrast", "supporting", 4, "black footer")
    e(2, "layout", "LY-1", 4, "the footer doesn't collide")

    for page, size, level in ((3, 32, 3), (4, 22, 2), (5, 14, 1)):
        s = blank(prs)
        head(s, f"Bullets at {size} points")
        text(s, 0.6, 2.0, 8.8, 4.0, bullets(["The first point on this slide",
                                             "A second point with more words",
                                             "A third and final point"]), size=size)
        footer(s, page)
        e(page, "font_size", "body", level, f"{size} pt bullets")

    s = blank(prs)
    head(s, "Bullets overflow into the footer")
    text(s, 0.6, 1.8, 8.8, 4.0, bullets([f"Point number {i} on a crowded slide" for i in range(1, 13)]),
         size=28)
    footer(s, 6)
    e(6, "layout", "LY-1", 1, "12 bullets overflow a 4 in box and run over the footer")

    long = ["A colored box with more text than fits in it, so the last lines spill out below "
            "the bottom of the box onto the white slide"]
    s = blank(prs)
    head(s, "Text spills out of a colored box")
    text(s, 0.6, 1.8, 8.8, 1.2, long, size=28, fill="#dde8f5")
    footer(s, 7)
    e(7, "layout", "LY-1", 1, "filled box 1.2 in high holding about 2 in of text")

    s = blank(prs)
    head(s, "Control: boxes that fit")
    text(s, 0.6, 1.8, 8.8, 1.4, ["A colored box whose text fits inside it"], size=28, fill="#dde8f5")
    text(s, 0.6, 3.8, 8.8, 0.6, long, size=28)  # no fill or outline: overflow isn't visible
    footer(s, 8)
    e(8, "layout", "LY-1", 4, "filled box fits; an unfilled text box overflows invisibly")

    s = blank(prs)
    head(s, "Control: text parked off the slide")
    text(s, 0.6, 2.0, 8.8, 1.0, ["Body text on the slide"], size=32)
    text(s, 10.5, 2.0, 4, 1.0, ["Speaker reminder parked off the slide"], size=24, fill="#ffff99")
    footer(s, 9)
    e(9, "layout", "LY-1", 4, "off-slide text is noted (LY-OFFPAGE), not scored")

    s = blank(prs, hidden=True)
    head(s, "Hidden slide with tiny text")
    text(s, 0.6, 2.0, 8.8, 3.0, ["This slide is hidden and must not be scored"], size=8, color="#bbbbbb")

    save(prs, out / "flaws-4x3.pptx")
    return {"deck": "flaws-4x3.pptx", "kind": "slides", "hidden": [10], "expect": exp}


def make_poster_half(out: Path, tmp: Path) -> dict:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(24), Inches(18)
    s = blank(prs)
    exp = []

    def e(marker, measure, key, level, note=""):
        exp.append({"measure": measure, "page": 1, "marker": marker, "key": key, "level": level,
                    "note": note})

    text(s, 0.5, 0.4, 23, 1.5, ["Half-size poster file, printed at 48x36 in"], size=55, bold=True)
    para = "This block wraps over a few lines so that it reads like part of a real poster."
    blocks = [((0.5, 2.5), "Introduction at 20 points,", 20, 4),
              ((8.5, 2.5), "Methods at 16 points,", 16, 3),
              ((16.5, 2.5), "Results at 11 points,", 11, 2),
              ((0.5, 9.5), "Details at 7 points,", 7, 1)]
    for (x, y), marker, size, level in blocks:
        text(s, x, y, 7, 6, [f"{marker} {2 * size} when printed. {para}"], size=size)
        e(marker, "font_size", "body", level, f"{size} pt in the file, {2 * size} pt printed")
    e("Introduction", "contrast", "body", 4)
    save(prs, out / "flaws-poster-half.pptx")
    return {"deck": "flaws-poster-half.pptx", "kind": "poster", "hidden": [], "print_size": "48x36in",
            "expect": exp}


# ---------- judged decks: the same short talk, done well and done badly ----------
# All three are judged with the course-presentation example rubric (FM-1 required slides,
# FM-2 citations on the slide, FM-3 slides per minute).

COURSE_RUBRIC = "rubrics/examples/course-presentation.md"

def _make_3d(ch) -> None:
    """Turn a 2-D clustered column chart into a 3-D one (python-pptx can't write 3-D charts)."""
    from lxml import etree
    C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
    cs = ch._chartSpace
    chart_el = cs.find(f"{{{C}}}chart")
    bar = chart_el.find(f"{{{C}}}plotArea/{{{C}}}barChart")
    bar.tag = f"{{{C}}}bar3DChart"
    for el in bar.findall(f"{{{C}}}overlap"):
        bar.remove(el)
    gap = bar.find(f"{{{C}}}gapWidth")
    shape = etree.Element(f"{{{C}}}shape", val="box")
    (gap.addnext(shape) if gap is not None else bar.find(f"{{{C}}}axId").addprevious(shape))
    view = etree.fromstring(f'<c:view3D xmlns:c="{C}"><c:rotX val="15"/><c:rotY val="20"/>'
                            '<c:rAngAx val="1"/></c:view3D>')
    chart_el.find(f"{{{C}}}plotArea").addprevious(view)
    for tag in ("floor", "sideWall", "backWall"):
        chart_el.find(f"{{{C}}}plotArea").addprevious(etree.Element(f"{{{C}}}{tag}"))


def _scores_chart(slide, colors, three_d=False, axis_min=0, labels=True, axis_titles=True):
    data = CategoryChartData()
    data.categories = ["Section 1", "Section 2", "Section 3"]
    data.add_series("Before", (61, 58, 64))
    data.add_series("After", (70, 67, 73))  # +9 in each section, as the title says
    ch = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.8), Inches(1.7), Inches(11.7),
                                Inches(5.5), data).chart
    ch.font.name, ch.font.size = FONT, Pt(20)
    ch.has_title = False
    ch.has_legend = True
    ch.legend.position = XL_LEGEND_POSITION.BOTTOM
    ch.legend.include_in_layout = False
    for sr, c in zip(ch.plots[0].series, colors):
        sr.format.fill.solid()
        sr.format.fill.fore_color.rgb = rgb(c)
    if labels:
        ch.plots[0].has_data_labels = True
        ch.plots[0].data_labels.font.size = Pt(20)
    ch.value_axis.minimum_scale = axis_min
    ch.value_axis.maximum_scale = 100 if axis_min == 0 else None
    if axis_titles:
        ch.value_axis.has_title = True
        ch.value_axis.axis_title.text_frame.text = "Mean quiz score (%)"
        ch.category_axis.has_title = True
        ch.category_axis.axis_title.text_frame.text = "Lecture section"
    if three_d:
        _make_3d(ch)  # last: python-pptx can't read 3-D plots back
    return ch


def make_judged_clear(out: Path, tmp: Path) -> dict:
    prs = slides_prs()
    s = prs.slides.add_slide(prs.slide_layouts[0])
    s.shapes.title.text = "Short pair discussions raise quiz scores in large classes"
    s.placeholders[1].text = "Ana Ruiz and Ben Okafor · Teaching seminar · 12 March 2026"
    _titled_layout(prs, "Outline", ["The problem", "What we tried", "What we found", "Summary"],
                   body_size=32)  # FM-1: every required slide; FM-2: sources cited on the slide
    _titled_layout(prs, "Many students in large lectures fall behind",
                   ["Few students ask questions (Lee & Park, 2019)", "Quiz scores vary a lot",
                    "We wanted a cheap fix"], body_size=32)
    _titled_layout(prs, "We added three 2-minute pair talks to each lecture",
                   ["The teacher asks a question (as in Mazur, 1997)", "Pairs talk for 2 minutes",
                    "A few pairs report back"], body_size=32)
    s = _titled_layout(prs, "Quiz scores rose by about 9 points in every section")
    _scores_chart(s, ["#0072b2", "#e69f00"])
    _titled_layout(prs, "Students who talked most gained most",
                   ["We counted turns in each pair", "More turns went with higher scores",
                    "Quiet students gained too"], body_size=32)
    _titled_layout(prs, "Summary: three things to remember",
                   ["Short pair talks raised quiz scores", "They cost about 6 minutes per lecture",
                    "Talking more went with learning more"], body_size=32)
    _titled_layout(prs, "References", [
        "Lee, J., & Park, S. (2019). Who asks questions in large lectures? Journal of College "
        "Teaching, 12(3), 45-58.",
        "Mazur, E. (1997). Peer Instruction: A User's Manual. Prentice Hall."], body_size=24)
    _titled_layout(prs, "Questions?", ["Ana Ruiz: aruiz@example.edu", "Ben Okafor: bokafor@example.edu"],
                   body_size=32)
    save(prs, out / "judged-clear.pptx")
    return {"deck": "judged-clear.pptx", "kind": "slides", "hidden": [], "expect": [],
            "intake": {"rubric": COURSE_RUBRIC, "time_limit_minutes": 10},  # FM-3: 6 content slides
            "judged": {k: [3, 4] for k in ("CN-1", "CL-1", "DG-1", "CO-3", "RD-4", "FM-1", "FM-2", "FM-3")},
            "key_ideas": [["score", "quiz"],
                          ["2-minute", "two-minute", "minutes", "cheap", "cost", "low-cost"],
                          ["talked most", "talked more", "gained more", "turns", "more talk", "talking more", "talk more"]]}


def make_judged_poor(out: Path, tmp: Path) -> dict:
    prs = slides_prs()
    s = prs.slides.add_slide(prs.slide_layouts[0])
    s.shapes.title.text = "TPS Study"
    s.placeholders[1].text = "Fall update"
    _titled_layout(prs, "Background", [
        "At the end of the day, leveraging peer-mediated metacognitive scaffolding affordances in "
        "high-enrollment STEM gateway course contexts moves the needle on student learning outcome "
        "assessment data, as the literature has long touched on, although the jury is still out on "
        "transfer, so we decided to take a stab at it and see whether it would pan out in our "
        "departmental ecosystem going forward, notwithstanding the usual institutional headwinds.",
        "\"Students learn more when they talk than when they listen\" (a well-known study)"],
        body_size=24)  # FM-2: literature and a quotation, never cited
    _titled_layout(prs, "Methods", [
        "Three sections (n = 412) in Room 101, Room 220 and the annex", "IRB protocol 2026-117, exempt",
        "TPS x3 per lecture, ~2 min, clicker Qs from the publisher bank",
        "Grading: 40% exams, 30% quizzes, 20% labs, 10% participation", "Late policy unchanged from spring",
        "TA training in week 2 (4 hours)", "Turn-taking coded from audio, kappa = .71",
        "Parking was a problem in week 5", "Pre/post quizzes, 20 items each",
        "Next year: maybe a second campus?"], body_size=20)
    s = _titled_layout(prs, "Results")
    _scores_chart(s, ["#c05040", "#609040"], three_d=True, axis_min=55, labels=False, axis_titles=False)
    s = _titled_layout(prs, "Results (cont.)")
    text(s, 0.8, 1.7, 11.7, 1.0, ["Red sections went up; green ones are the rest."], size=28)
    for i, c in enumerate(["#c05040", "#609040", "#c05040", "#609040", "#609040", "#c05040"]):
        b = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8 + 2 * i), Inches(3.2), Inches(1.7), Inches(1.7))
        b.fill.solid()
        b.fill.fore_color.rgb = rgb(c)
        b.line.fill.background()
    _titled_layout(prs, "Other", ["Low-hanging fruit: ballpark the ROI on TA FTEs",
                                  "Circle back re: LMS analytics", "Questions?"], body_size=28)
    # FM-1: no names or date, outline, conclusion, or references
    # FM-3: 4-5 content slides in 2 minutes (Level 1 or 2, however "Other" is counted)
    save(prs, out / "judged-poor.pptx")
    return {"deck": "judged-poor.pptx", "kind": "slides", "hidden": [], "expect": [],
            "intake": {"rubric": COURSE_RUBRIC, "time_limit_minutes": 2},
            "judged": {k: [1, 2] for k in ("CN-1", "CL-1", "DG-1", "CO-3", "RD-4", "FM-1", "FM-2", "FM-3")}}


def make_judged_middle(out: Path, tmp: Path) -> dict:
    """A different talk with every judged item in the middle (level 2 or 3): mixed signals."""
    prs = slides_prs()
    s = prs.slides.add_slide(prs.slide_layouts[0])
    s.shapes.title.text = "Weekly Quizzes Project"  # CN-1: topic titles throughout...
    s.placeholders[1].text = "Dana Cole and Lee Wu · Spring report · 14 April 2026"
    _titled_layout(prs, "Background", [  # RD-4: a few idioms, phrasal verbs, an undefined term
        "Many students cram the night before an exam",
        "Retrieval practice is known to help long-term memory",
        "We wanted to see if it pans out in intro biology"], body_size=32)
    _titled_layout(prs, "Method", [
        "Two sections of intro biology (n = 180)", "One section took a 5-question quiz each week",
        "The other section did the same homework, without quizzes", "Both took the same final exam"],
        body_size=28)
    s = _titled_layout(prs, "Results")
    data = CategoryChartData()  # DG-1 / CO-3: legend only, no axis titles, units, or labels
    data.categories = ["Unit 1", "Unit 2", "Unit 3", "Unit 4"]
    data.add_series("Weekly quizzes", (74, 71, 78, 76))
    data.add_series("No quizzes", (69, 64, 70, 67))
    ch = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.8), Inches(1.6), Inches(11.7),
                            Inches(4.6), data).chart
    ch.font.name, ch.font.size = FONT, Pt(20)
    ch.has_legend = True
    ch.legend.position = XL_LEGEND_POSITION.RIGHT
    ch.legend.include_in_layout = False
    for sr, c in zip(ch.plots[0].series, ["#0072b2", "#e69f00"]):
        sr.format.fill.solid()
        sr.format.fill.fore_color.rgb = rgb(c)
    ch.value_axis.minimum_scale, ch.value_axis.maximum_scale = 0, 100
    text(s, 0.8, 6.3, 11.7, 0.8, ["The quiz section scored higher on every unit exam."], size=28)
    _titled_layout(prs, "Details", [  # CL-1: one crowded slide among focused ones
        "Quizzes opened Monday and closed Friday at 5 pm",
        "LMS settings: one attempt, 15 minutes, answers shown after closing",
        "Quizzes counted for 5% of the course grade",
        "Attendance was about the same in both sections",
        "Most students finished each quiz in under 10 minutes",
        "A few students asked for extensions when they were sick, and we usually gave them one extra "
        "day, although this was not part of the original plan and may have affected the results",
        "The final exam had 60 multiple-choice items",
        "The same teacher taught both sections"], body_size=20)
    _titled_layout(prs, "Student comments", [
        "\"The quizzes made me keep up with the reading\"",
        "\"At first I didn't like them, but they grew on me\"",
        "\"I wish other courses did this\""], body_size=32)
    _titled_layout(prs, "Summary", [  # ...but a summary that states the findings
        "Weekly quizzes went with higher unit exam scores",
        "The quizzes took students about 10 minutes a week",
        "Next: try weekly quizzes in other courses"], body_size=32)
    _titled_layout(prs, "References", [  # FM-2: listed here, but not cited on the Background slide
        "Roediger, H. L., & Karpicke, J. D. (2006). Test-enhanced learning: Taking memory tests "
        "improves long-term retention. Psychological Science, 17(3), 249-255."], body_size=24)
    # FM-1: no outline and no questions slide (two missing: Level 2); FM-3: no time limit given
    save(prs, out / "judged-middle.pptx")
    return {"deck": "judged-middle.pptx", "kind": "slides", "hidden": [], "expect": [],
            "intake": {"rubric": COURSE_RUBRIC},
            "judged": {k: [2, 3] for k in ("CN-1", "CL-1", "DG-1", "CO-3", "RD-4", "FM-1", "FM-2")},
            "omit": ["FM-3"],
            "key_ideas": [["higher", "scored", "scores", "better"],
                          ["10 minutes", "ten minutes", "little time", "cheap", "low cost", "low-cost"]]}


def make_judged_low(out: Path, tmp: Path) -> dict:
    """A third talk aimed at Level 2 on every judged item, to test the 2/3 boundary from below."""
    prs = slides_prs()
    s = prs.slides.add_slide(prs.slide_layouts[0])
    s.shapes.title.text = "Online Homework Pilot"  # CN-1: topic titles, no summary
    s.placeholders[1].text = "Chris Patel · Math department meeting · 3 February 2026"
    _titled_layout(prs, "Background", [  # CL-1 / RD-4 / FM-2: dense, idioms, uncited data
        "Our paper homework system has been on its last legs for years",
        "DFW rates in Calc I hover around 30%, about the national average",
        "The vendor says students who use the platform score 20% higher",
        "TA grading load is through the roof in the fall term",
        "Students often hand in homework late or not at all",
        "Other departments have already moved to online homework",
        "The dean asked us to look into it last spring",
        "We wanted to try it before the budget cycle"], body_size=24)
    _titled_layout(prs, "Platform", [
        "LTI 1.3 integration with the LMS; SSO through the campus IdP",
        "Algorithmic item banks with randomized parameters",
        "Auto-graded, with partial credit for multi-part items",
        "Gradebook sync runs nightly", "ADA/VPAT documentation requested, not yet received",
        "Per-seat licensing; no site license"], body_size=24)
    _titled_layout(prs, "Pilot design", [
        "Six sections of Calc I in the fall term", "Sections 01-03 used online homework",
        "Sections 04-06 kept paper homework", "Same textbook, exams, and homework problems",
        "Homework counted for 10% of the grade", "Instructors were not randomly assigned",
        "Students could not switch sections after week 2"], body_size=24)
    s = _titled_layout(prs, "Completion")  # DG-1 / CO-3: 6 series, no axis titles, colors alone
    data = CategoryChartData()
    data.categories = [f"W{w}" for w in range(1, 13)]
    for name, base in (("Sec 01", 90), ("Sec 02", 87), ("Sec 03", 85), ("Sec 04", 74), ("Sec 05", 70),
                       ("Sec 06", 68)):
        data.add_series(name, [base - (w % 3) - w // 2 for w in range(12)])
    ch = s.shapes.add_chart(XL_CHART_TYPE.LINE, Inches(0.8), Inches(1.6), Inches(11.7), Inches(5.6),
                            data).chart
    ch.font.name, ch.font.size = FONT, Pt(18)
    ch.has_legend = True
    ch.legend.position = XL_LEGEND_POSITION.RIGHT
    ch.legend.include_in_layout = False
    for sr, c in zip(ch.plots[0].series, ["#2ca02c", "#d62728", "#8c8c3c", "#b5651d", "#6b8e23", "#cd5c5c"]):
        sr.smooth = False
        sr.format.line.color.rgb = rgb(c)
        sr.format.line.width = Pt(3)
    ch.value_axis.minimum_scale, ch.value_axis.maximum_scale = 0, 100
    s = _titled_layout(prs, "Scores")
    _bar_chart(s, 0.8, 1.6, 11.7, 5.6, ["Exam 1", "Exam 2", "Exam 3", "Final"],
               {"Online": (72, 70, 74, 71), "Paper": (70, 69, 71, 70)}, ["#0072b2", "#e69f00"], 18,
               legend=True, labels=False, axis_max=100)
    _titled_layout(prs, "Student survey", [  # CL-1: one finding buried among unrelated points
        "Response rate was 58% (n = 141)", "Most students (72%) preferred online homework",
        "Some said the instant feedback helped", "Some said typing math answers was a pain",
        "Wi-Fi in the dorms was spotty in October", "A few asked for a printed copy of each problem set",
        "Several mentioned the parking situation", "Two asked for more office hours"], body_size=22)
    _titled_layout(prs, "Cost", [
        "$35 per student per term", "Paper grading: about 10 TA hours per week",
        "Online: about 2 TA hours per week", "Similar savings at other campuses (Lee, 2024)"], body_size=28)
    _titled_layout(prs, "Issues", [
        "SSO outage in week 3 locked students out for a day", "Some items had answer-format gotchas",
        "Gradebook sync double-counted one assignment", "Students on the waitlist had no access at first",
        "The vendor's support line is hit or miss", "Accessibility review still pending"], body_size=24)
    _titled_layout(prs, "Next steps", [
        "Decide by March", "Talk to the dean about funding", "Ask the bookstore about bundles",
        "Finish the accessibility review"], body_size=28)
    # FM-1: no outline, references, or questions slide (three missing); FM-3: 9 content slides in 5 minutes
    save(prs, out / "judged-low.pptx")
    return {"deck": "judged-low.pptx", "kind": "slides", "hidden": [], "expect": [],
            "intake": {"rubric": COURSE_RUBRIC, "time_limit_minutes": 5},
            "judged": {k: [2, 2] for k in ("CN-1", "CL-1", "DG-1", "CO-3", "RD-4", "FM-1", "FM-2", "FM-3")},
            "key_ideas": [["completion", "completed", "turned in", "hand in", "more homework"],
                          ["TA", "grading", "hours"],
                          ["preferred", "72%"]]}


# ---------- judged posters: conference-poster example rubric ----------

POSTER_RUBRIC = "rubrics/examples/conference-poster.md"
POSTER_CALL = "landscape posters only, up to 48x36 in"
POSTER_ITEMS = ("CN-1", "CL-1", "DG-1", "CO-3", "RD-4", "FM-1", "FM-2", "FM-3")


def _bar_chart(slide, x, y, w, h, categories, series, colors, size, legend=False, labels=True,
               value_title=None, axis_min=0, axis_max=None, three_d=False):
    data = CategoryChartData()
    data.categories = categories
    for name, values in series.items():
        data.add_series(name, values)
    ch = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(x), Inches(y), Inches(w), Inches(h),
                                data).chart
    ch.font.name, ch.font.size = FONT, Pt(size)
    ch.has_title = False
    ch.has_legend = legend
    if legend:
        ch.legend.position = XL_LEGEND_POSITION.RIGHT
        ch.legend.include_in_layout = False
    for sr, c in zip(ch.plots[0].series, colors):
        sr.format.fill.solid()
        sr.format.fill.fore_color.rgb = rgb(c)
    if labels:
        ch.plots[0].has_data_labels = True
        ch.plots[0].data_labels.font.size = Pt(size)
    ch.value_axis.minimum_scale = axis_min
    if axis_max is not None:
        ch.value_axis.maximum_scale = axis_max
    if value_title:
        ch.value_axis.has_title = True
        ch.value_axis.axis_title.text_frame.text = value_title
        for r in ch.value_axis.axis_title.text_frame.paragraphs[0].runs:
            r.font.size, r.font.name = Pt(size), FONT
    if three_d:
        _make_3d(ch)  # last: python-pptx can't read 3-D plots back
    return ch


def _poster_intake(print_size: str) -> dict:
    return {"what": "a research poster for a conference", "rubric": POSTER_RUBRIC,
            "print_size": print_size, "call": POSTER_CALL}


def make_judged_poster_clear(out: Path, tmp: Path) -> dict:
    """48x36 in, as the call allows: finding in the title, every part, numbered columns."""
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(48), Inches(36)
    s = blank(prs)
    text(s, 1, 0.7, 46, 2.6, ["Studying a worked example first halved errors on new problems"],
         size=96, bold=True)
    text(s, 1, 3.4, 46, 1.2, ["Maya Chen (Riverside College, Chemistry) and Omar Haddad "
                              "(Riverside College, Education)"], size=44)

    def head(x, y, t):
        text(s, x, y, 14.5, 1.3, [t], size=60, bold=True, color="#1f3864")

    head(1, 5.5, "1. Question")
    text(s, 1, 6.9, 14.5, 5, ["Does studying a worked example before each practice problem help "
                              "students solve new problems?"], size=40)
    head(1, 12.5, "2. Methods")
    text(s, 1, 13.9, 14.5, 12, bullets(["120 students in general chemistry",
                                        "Half studied a worked example before each problem",
                                        "Half solved the same problems with no example",
                                        "All took the same test of new problems"]), size=40)
    head(16.75, 5.5, "3. Results")
    _bar_chart(s, 16.75, 7.0, 14.5, 17, ["Worked example first", "Problems only"],
               {"Errors": (2.1, 4.3)}, ["#0072b2"], 36, value_title="Errors per test (mean)", axis_max=5)
    text(s, 16.75, 24.5, 14.5, 4, ["Students who studied an example first made 2.1 errors per test; "
                                   "the others made 4.3."], size=44, bold=True)
    head(32.5, 5.5, "4. Conclusions")
    text(s, 32.5, 6.9, 14.5, 14, bullets(["A worked example first halved errors on new problems",
                                          "It took no extra class time",
                                          "Weaker and stronger students both gained"]), size=40)
    head(32.5, 22, "5. References")
    text(s, 32.5, 23.4, 14.5, 4, ["Sweller, J., & Cooper, G. A. (1985). The use of worked examples as a "
                                  "substitute for problem solving in learning algebra. Cognition and "
                                  "Instruction, 2(1), 59-89."], size=32)
    text(s, 32.5, 29, 14.5, 2, ["Contact: mchen@example.edu"], size=40)
    save(prs, out / "judged-poster-clear.pptx")
    return {"deck": "judged-poster-clear.pptx", "kind": "poster", "hidden": [], "expect": [],
            "print_size": "48x36in", "intake": _poster_intake("48x36 in"),
            "judged": {k: [3, 4] for k in POSTER_ITEMS},
            "key_ideas": [["halved", "half", "fewer errors", "errors", "4.3", "2.1"]]}


def make_judged_poster_middle(out: Path, tmp: Path) -> dict:
    """24x18 in file printed at 48x36 (FM-3 Level 3); sizes are half the printed size."""
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(24), Inches(18)
    s = blank(prs)
    text(s, 0.5, 0.35, 23, 1.2, ["Peer Tutoring in First-Year Math"], size=48, bold=True)  # CN-1: a topic
    text(s, 0.5, 1.6, 23, 0.6, ["Rosa Diaz and Tom Becker, Lakeside University, Department of Mathematics"],
         size=22)

    def head(x, y, w, t):
        text(s, x, y, w, 0.7, [t], size=30, bold=True, color="#1f3864")

    head(0.5, 2.6, 7.2, "Background")
    text(s, 0.5, 3.3, 7.2, 3.6, ["Many first-year students fall behind in calculus. Peer tutoring is "
                                 "cheap, but the jury is still out on whether it pays off for grades."],
         size=20)
    head(0.5, 7.4, 7.2, "Methods")  # CL-1: two crowded blocks (this and Discussion)
    text(s, 0.5, 8.1, 7.2, 9.5, bullets([
        "Two calculus sections (n = 210) in the fall term, taught by different instructors using the "
        "same syllabus, homework sets and exams",
        "One section offered weekly peer tutoring; the other had the usual office hours only",
        "Tutors were second-year students who had earned an A, trained for 6 hours on questioning",
        "Sessions: 50 minutes, groups of 4, held in the library on Tuesday and Thursday evenings",
        "Attendance was optional and logged by the tutors on a paper sign-in sheet",
        "Outcome: the common final exam (100 points), graded by a shared rubric",
        "We also surveyed students at the end of term about study habits and confidence"]), size=16)
    head(8.3, 2.6, 15.2, "Results")  # FM-2: one wide box over two columns; what comes next is unclear
    _bar_chart(s, 8.3, 3.3, 15.2, 6.6, ["Exam 1", "Exam 2", "Final"],
               {"Tutoring offered": (68, 71, 74), "No tutoring": (66, 66, 68)}, ["#0072b2", "#e69f00"], 16,
               legend=True, labels=False, axis_max=100)  # DG-1 / CO-3: legend only, no axis title
    head(8.3, 10.4, 7.2, "Student comments")
    text(s, 8.3, 11.1, 7.2, 5, ['"The tutors explained it in a way I could follow"',
                                '"I went every week before the exams"'], size=20)
    head(8.3, 13.0, 7.2, "Discussion")  # FM-2: after Results, comments, Discussion or Conclusions?
    text(s, 8.3, 13.7, 7.2, 4.2, [
        "The sections had different instructors, so some of the difference may come from teaching style. "
        "Students chose whether to attend, and stronger students may have come more often. The survey "
        "suggested that tutored students studied more regularly, but response rates were low (41%). "
        "Tutors also reported gains in their own understanding, which we did not measure. Funding for "
        "tutor pay came from a small internal grant that ends next year, and we are now planning a "
        "version for statistics."], size=14)
    head(16.3, 10.4, 7.2, "Conclusions")
    text(s, 16.3, 11.1, 7.2, 4.5, bullets(["The tutoring section scored about 6 points higher on the final",
                                           "Students who came more often gained more"]), size=16)  # CN-1: small
    text(s, 16.3, 16.3, 7.2, 0.8, ["Contact: rdiaz@example.edu"], size=18)
    # FM-1: no references (one part missing)
    save(prs, out / "judged-poster-middle.pptx")
    return {"deck": "judged-poster-middle.pptx", "kind": "poster", "hidden": [], "expect": [],
            "print_size": "48x36in", "intake": _poster_intake("48x36 in"),
            "judged": {k: [2, 3] for k in POSTER_ITEMS},
            "key_ideas": [["higher", "6 points", "six points", "scored", "better"],
                          ["more often", "came more", "attend", "gained more"]]}


def make_judged_poster_poor(out: Path, tmp: Path) -> dict:
    """Portrait, though the call allows landscape only; scattered unlabeled blocks; most parts missing."""
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(36), Inches(48)
    s = blank(prs)
    text(s, 1, 0.8, 34, 2.5, ["WE-PS Project"], size=88, bold=True)  # no authors, affiliations, or contact
    text(s, 15, 4.5, 20, 12, [  # no headings anywhere; blocks at odd positions
        "Leveraging schema-acquisition affordances via example-based instructional sequencing in "
        "high-enrollment gateway chemistry contexts is low-hanging fruit for moving the needle on "
        "transfer-relevant problem-solving outcome metrics, though the literature is all over the map "
        "and at the end of the day the proof of the pudding is in the eating."], size=32)
    text(s, 1, 5, 12, 14, ["N=120, GC1, F26, IRB exempt, 2 cond., counterbal., Qualtrics, 14 items, "
                           "WE vs PS, LMS export, TA-coded, alpha .81, 3 dropped, 2 late, room swap wk 6"],
         size=30)
    _bar_chart(s, 4, 20, 26, 14, ["WE", "PS"], {"Pre": (5.1, 5.0), "Post": (2.1, 4.3)},
               ["#c05040", "#609040"], 28, legend=True, labels=False, axis_min=1.5, three_d=True)
    text(s, 22, 36, 13, 3, ["Red = good"], size=36)
    text(s, 1, 38, 18, 8, ["Future: more sections? other courses? online version? grant?"], size=32)
    save(prs, out / "judged-poster-poor.pptx")
    return {"deck": "judged-poster-poor.pptx", "kind": "poster", "hidden": [], "expect": [],
            "print_size": "36x48in", "intake": _poster_intake("36x48 in (portrait)"),
            "judged": {k: [1, 2] for k in POSTER_ITEMS}}


def make_all(out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    tmp = ROOT / ".cache" / "deck-assets"  # pictures placed in the decks; not committed
    tmp.mkdir(parents=True, exist_ok=True)
    paths = []
    for maker in (make_slides, make_poster, make_color, make_text, make_structure, make_4x3,
                  make_poster_half, make_judged_clear, make_judged_poor, make_judged_middle, make_judged_low,
                  make_judged_poster_clear, make_judged_poster_middle, make_judged_poster_poor):
        exp = maker(out, tmp)
        (out / exp["deck"]).with_suffix(".expected.json").write_text(
            json.dumps(exp, indent=2), encoding="utf-8")
        paths.append(out / exp["deck"])
    return paths


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    out = Path(argv[0]) if argv else ROOT / "tests" / "decks"
    for p in make_all(out):
        print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
