"""Pipeline tests on the local files in test-inputs/ (not in git; tests skip if missing)."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skill" / "slide-poster-review"
sys.path.insert(0, str(SKILL / "scripts"))
import color  # noqa: E402
import contrast  # noqa: E402
import extract_text  # noqa: E402
import font_size  # noqa: E402
import ocr  # noqa: E402
import scorecard  # noqa: E402
import render  # noqa: E402

sys.path.insert(0, str(ROOT / "tools"))
import make_test_decks  # noqa: E402

INPUTS = ROOT / "test-inputs"
# Renders persist here between test runs (render.py reuses them when inputs are unchanged).
CACHE = ROOT / ".cache" / "test-renders"
POSTERS = INPUTS / "PNM 2026 posters.pptx"
HANDOUT = INPUTS / "2026-11 Active & Engaged Learning - slide handout.pdf"

needs = lambda p: pytest.mark.skipif(not p.exists(), reason=f"missing {p.name}")  # noqa: E731
needs_pptx_backend = pytest.mark.skipif(
    not (render._powerpoint_available() or render._find_soffice()), reason="no PPTX renderer")


@pytest.fixture(scope="module")
def posters_out(tmp_path_factory):
    if not POSTERS.exists():
        pytest.skip("missing posters pptx")
    if not (render._powerpoint_available() or render._find_soffice()):
        pytest.skip("no PPTX renderer")
    out = render.render(POSTERS, CACHE, dpi=150, max_px=8000)
    extract_text.extract(out)
    return out


def load(out, name):
    return json.loads((out / name).read_text(encoding="utf-8"))


@needs(POSTERS)
@needs_pptx_backend
def test_pptx_manifest(posters_out):
    m = load(posters_out, "manifest.json")
    assert m["source_type"] == "pptx" and m["page_count"] == 3
    assert m["kind_guess"] == "poster"
    assert m["pptx_slide_size_in"] == [48.0, 36.0]
    for p in m["pages"]:
        assert (p["width_pt"], p["height_pt"]) == (3456.0, 2592.0)
        assert (p["width_px"], p["height_px"]) == (7200, 5400)
        assert p["hidden"] is False
        assert (posters_out / p["image"]).exists()
    assert m["source_app"]["app"] == "powerpoint"
    assert m["notices"] == []


@needs(POSTERS)
@needs_pptx_backend
def test_text_runs(posters_out):
    t = load(posters_out, "text.json")
    title = t["pages"][0]["spans"][0]
    assert title["text"].startswith("Process Oriented Guided Inquiry Learning")
    assert title["size_pt"] == pytest.approx(115, abs=0.1) and title["bold"]
    assert title["color"] == "#000000"
    assert t["fonts"]["SegoeUI"]["cap_height_em"] == pytest.approx(0.700, abs=0.001)
    assert t["fonts"]["Calibri"]["cap_height_em"] == pytest.approx(0.632, abs=0.001)
    # Chart text (horizontal) is extracted as text.
    texts = {s["text"].strip() for s in t["pages"][0]["spans"]}
    assert {"Lecture", "POGIL", "60%"} <= texts


@needs(POSTERS)
@needs_pptx_backend
def test_pptx_structure(posters_out):
    fonts = load(posters_out, "manifest.json")["fonts"]
    assert fonts["not_in_pdf"] == ["Calibri Light"]  # theme heading font, unused
    assert fonts["not_installed"] == []  # ...but installed, so not a substitution
    x = load(posters_out, "text.json")["pptx"]
    s2 = {sh["name"]: sh for sh in x["slides"][1]["shapes"]}
    assert s2["Picture 2"]["alt_text"].startswith("CS-POGIL logo")
    assert s2["Picture 13"]["alt_text"] is None
    chart = next(sh for sh in x["slides"][0]["shapes"] if sh["type"] == "CHART")
    assert chart["bbox"] == pytest.approx([1764.0, 468.54, 2520.0, 1032.0], abs=0.1)


@needs(POSTERS)
@needs_pptx_backend
def test_pdf_passthrough_and_px_cap(posters_out, tmp_path):
    m = load(render.render(posters_out / "source.pdf", tmp_path, dpi=150, max_px=1200), "manifest.json")
    assert m["renderer"] == "pdf" and m["page_count"] == 3 and m["kind_guess"] == "poster"
    assert max(m["pages"][0]["width_px"], m["pages"][0]["height_px"]) <= 1200


@needs(HANDOUT)
def test_handout_rejected(tmp_path):
    with pytest.raises(render.RenderError) as e:
        render.render(HANDOUT, tmp_path)
    assert e.value.code == 2 and "handout" in str(e.value)


def test_docx_out_of_scope(tmp_path):
    f = tmp_path / "notes.docx"
    f.write_bytes(b"")
    with pytest.raises(render.RenderError) as e:
        render.render(f, tmp_path / "out")
    assert e.value.code == 2


# ---------- Google Slides exports (same deck as .pptx, .pdf, .odp) ----------

GENAI = INPUTS / "2026 Fall - Education & GenAI"
AEL = INPUTS / "2026-11 Active & Engaged Learning (3h)"


@pytest.fixture(scope="module")
def genai_pair(tmp_path_factory):
    pptx, pdf = GENAI.with_suffix(".pptx"), GENAI.with_suffix(".pdf")
    if not (pptx.exists() and pdf.exists()):
        pytest.skip("missing GenAI exports")
    if not render._powerpoint_available():
        pytest.skip("needs PowerPoint")
    root = CACHE
    out = {}
    for src in (pptx, pdf):
        d = render.render(src, root)
        extract_text.extract(d)
        out[src.suffix[1:]] = d
    return out


def test_output_dirs_do_not_collide(genai_pair):
    assert genai_pair["pptx"] != genai_pair["pdf"]


def test_hidden_slides_kept_and_flagged(genai_pair):
    mx, mp = load(genai_pair["pptx"], "manifest.json"), load(genai_pair["pdf"], "manifest.json")
    assert mx["page_count"] == mp["page_count"] == 66  # Google's PDF includes skipped slides
    assert [p["index"] for p in mx["pages"] if p["hidden"]] == [1, 13, 19, 23, 24, 25, 30, 36, 37, 38]
    assert mx["hidden_flags_known"] and not mp["hidden_flags_known"]


def test_font_substitution_warned(genai_pair):
    mx = load(genai_pair["pptx"], "manifest.json")
    assert mx["fonts"]["substituted"] == ["Gill Sans"]
    sub = next(n for n in mx["notices"] if n["code"] == "FONT-SUB")
    assert sub["level"] == "warning" and "Gill Sans" in sub["message"]
    assert "Google Slides as PDF" in sub["advice"]


def test_source_app_notices(genai_pair):
    mx, mp = load(genai_pair["pptx"], "manifest.json"), load(genai_pair["pdf"], "manifest.json")
    assert mx["source_app"]["app"] == mp["source_app"]["app"] == "google_slides"
    assert mx["source_app"]["confidence"] == "likely" and mp["source_app"]["confidence"] == "high"
    assert {n["code"] for n in mx["notices"]} == {"SRC-GSLIDES-PPTX", "FONT-SUB"}
    pdf_notice = next(n for n in mp["notices"] if n["code"] == "SRC-PDF")
    assert "Skipped" in pdf_notice["message"] and ".pptx" in pdf_notice["advice"]


def test_cap_height_from_subset_fonts_without_cmap(genai_pair):
    fonts = load(genai_pair["pdf"], "text.json")["fonts"]
    assert fonts["ArialMT"]["cap_height_source"] == "glyph-gid"
    assert fonts["ArialMT"]["cap_height_em"] == pytest.approx(0.716, abs=0.002)
    assert fonts["Calibri"]["cap_height_source"] == "family"


def test_font_sizes_agree_across_exports(genai_pair):
    tx, tp = load(genai_pair["pptx"], "text.json"), load(genai_pair["pdf"], "text.json")
    diffs = []
    for a, b in zip(tp["pages"], tx["pages"]):
        sizes = {s["text"].strip(): s["size_pt"] for s in a["spans"]}
        diffs += [abs(s["size_pt"] - sizes[k]) for s in b["spans"]
                  if len(k := s["text"].strip()) > 3 and k in sizes]
    assert len(diffs) > 500 and sorted(diffs)[int(len(diffs) * 0.95)] < 0.5


@needs(AEL.with_suffix(".odp"))
def test_odp_without_libreoffice_is_clear(tmp_path):
    if render._find_soffice():
        pytest.skip("LibreOffice installed")
    with pytest.raises(render.RenderError, match="odp"):
        render.render(AEL.with_suffix(".odp"), tmp_path)


# ---------- packaging ----------

def test_skill_validates():
    skills_ref = pytest.importorskip("skills_ref")
    assert skills_ref.validate(SKILL) == []


def test_skill_folder_has_no_dev_files():
    shipped = {p.name for p in SKILL.iterdir()}
    assert not shipped & {"tests", "test-inputs", "output", ".venv", "DESIGN.md", "QUEUE.md"}


# ---------- font size ----------

def test_presets_and_levels():
    presets = font_size.load_presets()
    assert {n for n, p in presets.items() if p["default"]} == {"slides-8H", "poster-1.5m"}
    b = presets["slides-8H"]["bounds"]
    assert b == [10, 16, 22]
    # At 8H, the bounds correspond to about 18 / 29 / 40 pt at 0.7 em on a 540 pt slide.
    for pt, bound in zip((18, 28.7, 39.5), b):
        assert font_size.cap_angle_arcmin(pt * 0.7 / 540, 8) == pytest.approx(bound, abs=0.05)
    assert font_size.level_for(b[1] * 0.995, b) == 3  # 1% tolerance (39.96 pt counts as 40)
    assert font_size.level_for(b[1] * 0.98, b) == 2


def test_print_size_parsing():
    assert font_size.parse_print_size("48x36in") == pytest.approx((1.2192, 0.9144))
    assert font_size.parse_print_size("120 x 90 cm") == pytest.approx((1.2, 0.9))
    with pytest.raises(ValueError):
        font_size.parse_print_size("A0")


def _without_ocr(src, tmp_path):
    """Copy of a cached output folder without OCR results (tests of PDF-text-only behaviour)."""
    import shutil
    d = tmp_path / src.name
    shutil.copytree(src, d)
    for f in ("ocr.json", "font_size.json", "contrast.json", "scorecard.md", "scorecard.json"):
        (d / f).unlink(missing_ok=True)
    return d


def test_poster_font_size(posters_out, tmp_path):
    posters_out = _without_ocr(posters_out, tmp_path)
    full = load(font_size.measure(posters_out).parent, "font_size.json")
    assert full["items"]["FS-1"]["level"] == 3 and full["findings"] == []
    assert any(n["code"] == "FS-PRINT-SIZE" for n in full["notices"])
    # Printing at 3/4 size makes text smaller: some blocks drop below L3.
    small = load(font_size.measure(posters_out, print_size="36x27in").parent, "font_size.json")
    assert small["m_per_pt"] == pytest.approx(full["m_per_pt"] * 0.75)
    assert small["findings"] and small["findings"][0]["summary"].startswith("FS-1: 9 text blocks")


@pytest.fixture(scope="module")
def ael_pptx(tmp_path_factory):
    src = AEL.with_suffix(".pptx")
    if not src.exists() or not render._powerpoint_available():
        pytest.skip("needs AEL pptx and PowerPoint")
    d = render.render(src, CACHE)
    extract_text.extract(d)
    font_size.measure(d)
    return d


def test_footers_are_supporting_and_hidden_not_scored(ael_pptx):
    r = load(ael_pptx, "font_size.json")
    assert r["items"]["FS-2"]["units"] == 81  # 98 slides - 17 hidden, all with the footer
    fs2 = next(f for f in r["findings"] if f["id"] == "FS-2")
    assert "footers (81 slides)" in fs2["details"]
    body_smallest = [u["body"]["smallest"]["text"] for u in r["units"] if "body" in u]
    assert "Clif Kussmaul" not in body_smallest


def test_invisible_text_is_not_scored(genai_pair):
    r = load(font_size.measure(genai_pair["pptx"]).parent, "font_size.json")
    tiny = next(n for n in r["notices"] if n["code"] == "FS-TINY")
    assert "Countdown timer" in tiny["message"]
    assert all(u["body"]["smallest"]["arcmin"] >= 1 for u in r["units"] if "body" in u)


def test_text_kinds_named_in_findings(ael_pptx):
    r = load(ael_pptx, "font_size.json")
    fs1 = next(f for f in r["findings"] if f["id"] == "FS-1")
    assert "bullets" in fs1["summary"] and "short labels" in fs1["summary"]
    assert "comfortable reading size (about 22 pt in this deck)" in fs1["headline"]
    kinds = {u["page"]: u["body"]["smallest"]["kind"] for u in r["units"] if "body" in u}
    assert kinds[13] == "bullet"  # "●interest in math"
    assert kinds[20] == "label"   # "Partner  Worksheet Highlight  Read"


def test_substitute_font_named(genai_pair):
    r = load(font_size.measure(genai_pair["pptx"]).parent, "font_size.json")
    assert any("substitute for Gill Sans" in f["summary"] for f in r["findings"])


# ---------- render cache ----------

def test_render_cache_reuse_and_force(tmp_path):
    pdf = GENAI.with_suffix(".pdf")
    if not pdf.exists():
        pytest.skip("missing GenAI pdf")
    d = render.render(pdf, tmp_path, max_px=600)
    first = load(d, "manifest.json")
    (d / "text.json").write_text("{}", encoding="utf-8")
    assert render.render(pdf, tmp_path, max_px=600) == d
    assert load(d, "manifest.json")["rendered_at"] == first["rendered_at"]  # reused
    assert (d / "text.json").exists()  # downstream results kept on reuse
    render.render(pdf, tmp_path, max_px=500)  # different settings: re-rendered
    assert load(d, "manifest.json")["cache_key"] != first["cache_key"]
    assert not (d / "text.json").exists()  # stale downstream results removed
    k = load(d, "manifest.json")["cache_key"]
    render.render(pdf, tmp_path, max_px=500, force=True)
    assert load(d, "manifest.json")["cache_key"] == k


# ---------- rubric and scorecard ----------

def test_default_rubric_parses():
    sections, items = scorecard.load_rubric()
    assert sections["Text size"]["weight"] == 3 and sections["Format"]["weight"] == 1
    assert items["FS-1"]["type"] == "measured" and items["CN-1"]["type"] == "judged"
    assert items["FS-1"]["name"] == "Body text size" and items["FS-1"]["weight"] == 3
    assert set(items["CN-1"]["levels"]) == {1, 2, 3, 4}


def test_context_rubric_overrides(tmp_path):
    ctx = tmp_path / "course.md"
    ctx.write_text("## Sections\n\n| section | weight |\n|---|---|\n| Content | 5 |\n\n"
                   "## Judged items\n\n### CN-1 Key ideas are identifiable\n- weight: 4\n"
                   "- Level 4: Course version.\n\n### FM-9 Has an objectives slide\n"
                   "- section: Format\n- weight: 1\n", encoding="utf-8")
    sections, items = scorecard.load_rubric([ctx])
    assert sections["Content"]["weight"] == 5
    assert items["CN-1"]["weight"] == 4 and items["CN-1"]["levels"][4] == "Course version."
    assert items["CN-1"]["levels"][1].startswith("No clear key ideas")  # untouched fields kept
    assert items["FM-9"]["type"] == "judged" and items["FM-9"]["section"] == "Format"


def test_scoring_math():
    sections = {"A": {"weight": 3}, "B": {"weight": 1}, "C": {"weight": 2}}
    items = {"a1": {"id": "a1", "name": "A one", "section": "A", "weight": 3, "type": "measured"},
             "a2": {"id": "a2", "name": "A two", "section": "A", "weight": 1, "type": "measured"},
             "b1": {"id": "b1", "name": "B one", "section": "B", "weight": 1, "type": "judged"},
             "c1": {"id": "c1", "name": "C one", "section": "C", "weight": 1, "type": "measured"}}
    res = {"a1": {"level": 2, "confidence": "high", "headline": "x", "count": 5},
           "a2": {"level": 1, "confidence": "high", "headline": "y", "count": 9},
           "b1": {"level": 4, "confidence": "low", "headline": None, "count": 0}}
    sc = scorecard.score(sections, items, res)
    assert sc["sections"][0]["score"] == 1.8           # (3*2 + 1*1) / 4 = 1.75
    assert sc["overall"] == pytest.approx((3 * 1.75 + 1 * 4) / 4, abs=0.05)
    assert sc["not_assessed_sections"] == ["C"]
    assert [i["id"] for i in sc["issues"]] == ["a1", "a2"]  # 3*3/4*2=4.5 > 3*1/4*3=2.25


def test_scorecard_with_judgment(ael_pptx, tmp_path):
    d = _without_ocr(ael_pptx, tmp_path)  # this test covers size (PDF text) + judged items
    font_size.measure(d)
    (d / "judgments.json").write_text(json.dumps({
        "key_ideas": ["Active learning beats lecture", "Use structured activities"],
        "items": [{"id": "CN-1", "level": 3, "confidence": "medium",
                   "headline": "Two key ideas are signaled only in the closing slides.",
                   "pages": [90, 95]},
                  {"id": "FS-1", "level": 1}]}), encoding="utf-8")
    md = scorecard.build(d).read_text(encoding="utf-8")
    assert "| **Text size** | **1.8** |" in md
    assert "| &emsp;Body text size | 2 |" in md
    assert "| **Content** (judged) | **3.0** |" in md
    assert "1. **Body text size** (2 of 4, high confidence):" in md  # names, not just IDs
    assert "For example: slides 90, 95." in md
    assert "'FS-1' is not a judged item" in md  # agent can't override measured items
    assert "Active learning beats lecture" in md
    sc = load(d, "scorecard.json")
    assert sc["items_assessed"] == 3 and "Contrast" in sc["not_assessed_sections"]


# ---------- contrast ----------

def _ratio(a, b):
    return float(contrast.contrast_ratio(contrast.rel_luminance(contrast.hex_rgb(a)),
                                         contrast.rel_luminance(contrast.hex_rgb(b))))


def test_contrast_math():
    assert _ratio("#000000", "#ffffff") == pytest.approx(21.0)
    assert _ratio("#767676", "#ffffff") == pytest.approx(4.54, abs=0.01)  # classic AA grey
    assert contrast.show_ratio(4.4999) == "4.49:1"  # truncated, never rounded up
    assert contrast.level_for(4.49, large=False) == 2 and contrast.level_for(4.5, large=False) == 3
    assert contrast.level_for(3.0, large=True) == 3 and contrast.level_for(2.99, large=True) == 1
    assert contrast.level_for(7.0, large=False) == 4


def _synthetic(fg, bg, noisy=False):
    import numpy as np
    img = np.zeros((40, 200, 3), dtype=np.int16)
    img[:] = contrast.hex_rgb(bg)
    if noisy:  # left half much lighter: a "photo" background, worse for white text
        img[:, :100] = contrast.hex_rgb("#e0e0e0")
    for x in range(20, 180, 12):  # glyph strokes
        img[8:32, x:x + 4] = contrast.hex_rgb(fg)
    return img


def test_sample_span_uniform_and_complex():
    import numpy as np
    r = contrast.sample_span(_synthetic("#0097a7", "#ffffff"), (0, 0, 200, 40),
                             contrast.hex_rgb("#0097a7"), 1.0)
    assert r["ratio"] == pytest.approx(_ratio("#0097a7", "#ffffff"), abs=0.01)
    assert r["visible"] and not r["complex_bg"]
    r2 = contrast.sample_span(_synthetic("#ffffff", "#808080", noisy=True), (0, 0, 200, 40),
                              contrast.hex_rgb("#ffffff"), 1.0)
    assert r2["complex_bg"]
    assert r2["ratio"] < _ratio("#ffffff", "#808080")  # near-worst case, not the light half
    blank = np.full((40, 200, 3), 255, dtype=np.int16)  # text color absent: covered or effects
    r3 = contrast.sample_span(blank, (0, 0, 200, 40), contrast.hex_rgb("#202020"), 1.0)
    assert not r3["visible"]


def test_poster_low_contrast_found(posters_out):
    r = load(contrast.measure(posters_out).parent, "contrast.json")
    f = next(f for f in r["findings"] if f["id"] == "CT-1")
    assert "1.64:1, #ffc000 on #ffffff" in f["details"]
    assert "image, gradient" not in f["details"]  # neighbouring lines aren't "background"


def test_link_contrast_exact(ael_pptx):
    r = load(contrast.measure(ael_pptx).parent, "contrast.json")
    links = [u["supporting"]["worst"] for u in r["units"]
             if "supporting" in u and u["supporting"]["worst"]["fg"] == "#0097a7"]
    assert links and all(w["ratio"] == pytest.approx(3.509, abs=0.01) for w in links)
    assert all(w["reason"] == "citation" and w["level"] == 2 for w in links)
    # Slide 19: body text overflows into the footer, so the footer is "over other text".
    s19 = next(u for u in r["units"] if u["page"] == 19)["supporting"]["worst"]
    assert s19["complex_bg"] and s19["level"] == 1
    md = scorecard.build(ael_pptx).read_text(encoding="utf-8")
    assert "| **Contrast** |" in md and "| &emsp;Body text contrast | 3 |" in md


# ---------- OCR (text in images and shapes) ----------

needs_ocr = pytest.mark.skipif(not ocr.ocr_available(), reason="Windows OCR not available")


def test_ocr_helpers():
    assert ocr.cap_px("Hello", 100) == pytest.approx(95)     # cap/ascender, no descender
    assert ocr.cap_px("Happy", 100) == pytest.approx(70)     # ascender to descender
    assert ocr.cap_px("one", 100) == pytest.approx(140)      # x-height only
    assert ocr.real_line([{"text": "Analytical"}, {"text": "xQz"}])
    assert ocr.real_line([{"text": "91-100"}])
    assert not ocr.real_line([{"text": "rwentOry"}, {"text": "x1Q"}])


def test_infer_text_color():
    img = _synthetic("#ffffff", "#2050a0")  # white strokes on blue
    fg = contrast.infer_text_color(img, (0, 0, 200, 40))
    assert contrast.rgb_hex(fg) == "#ffffff"


def test_glyph_clusters_find_rotated_labels(posters_out):
    import pymupdf
    doc = pymupdf.open(posters_out / "source.pdf")
    assert len(ocr.glyph_clusters(doc[0])) == 1  # the chart's rotated axis labels
    assert ocr.glyph_clusters(doc[1]) == []


@needs_ocr
def test_ocr_reads_rotated_axis_labels(posters_out):
    r = load(ocr.run(posters_out).parent, "ocr.json")
    rotated = sorted(w["text"] for w in r["words"] if w["rotation"])
    assert rotated == sorted(["0-50", "51-60", "61-70", "71-80", "81-90", "91-100"])
    # 36 pt Segoe UI: cap height 0.70 em = 25.2 pt
    assert all(w["cap_pt"] == pytest.approx(25.2, rel=0.05) for w in r["words"] if w["rotation"])
    assert r["unread"] == []


@needs_ocr
def test_image_text_measured(ael_pptx):
    ocr.run(ael_pptx)
    r = load(font_size.measure(ael_pptx).parent, "font_size.json")
    s79 = next(u for u in r["units"] if u["page"] == 79)["body"]["smallest"]
    assert s79.get("ocr") and s79["level"] == 1  # tiny Bloom's verbs infographic
    assert any(n["code"] == "OCR-FOUND" for n in r["notices"])
    fs1 = next(f for f in r["findings"] if f["id"] == "FS-1")
    assert fs1["confidence"] == "medium" and "text in images or shapes" in fs1["details"]
    c = load(contrast.measure(ael_pptx).parent, "contrast.json")
    c79 = next(u for u in c["units"] if u["page"] == 79)["body"]["worst"]
    assert c79.get("ocr") and c79["level"] == 1  # white heading on bright cyan


# ---------- color ----------

def test_color_math():
    assert float(color.delta_e([0, 0, 0], [255, 255, 255])) == pytest.approx(100, abs=0.1)
    assert color.confusions([0xc0, 0x50, 0x40], [0x60, 0x90, 0x40]) == ["deutan"]
    assert color.confusions([0x00, 0x72, 0xb2], [0xe6, 0x9f, 0x00]) == []  # Okabe-Ito
    assert color.confusions([0x66, 0xaa, 0xdd], [0x77, 0xbb, 0x99]) == ["tritan"]
    assert color.level_for([]) == 4 and color.level_for(["tritan"]) == 3
    assert color.level_for(["deutan", "tritan"]) == 2 and color.level_for(["deutan-moderate"]) == 1


def test_photo_vs_graphic():
    rng = np.random.default_rng(0)
    photo = rng.integers(0, 256, (200, 200, 3))
    graphic = np.full((200, 200, 3), 255)
    graphic[50:150, 20:80] = (0xc0, 0x50, 0x40)
    graphic[50:150, 120:180] = (0x60, 0x90, 0x40)
    assert color.is_photo(photo) and not color.is_photo(graphic)
    pal = color.palette(graphic)
    assert len(pal) == 2 and color.confusable_pairs(pal)[0]["types"] == ["deutan"]
    assert color.palette(graphic, skip=[(0, 0, 200, 200)]) == []


def _span(t, c, x0, bold=False, block=0, line=0):
    return {"text": t, "color": c, "font": "ArialMT", "size_pt": 32, "bold": bold, "italic": False,
            "bbox": [x0, 100, x0 + 20 * len(t), 132], "origin": [x0, 125], "dir": [1.0, 0.0],
            "block": block, "line": line}


def test_emphasis_spans():
    line = [_span("The result ", "#000000", 0), _span("improved", "#c00000", 220),
            _span(" for every group.", "#000000", 380)]
    [e] = color.emphasis_spans(line, [], [])
    assert e["text"] == "improved" and e["level"] == 3 and not e["link"]
    assert color.emphasis_spans(line, [(220, 128, 380, 130)], []) == []          # underlined
    assert color.emphasis_spans(line, [], [(200, 90, 400, 140)])[0]["link"]      # link
    line[1]["bold"] = True
    assert color.emphasis_spans(line, [], []) == []                              # bold too
    grey = [_span("The result ", "#000000", 0), _span("improved", "#555555", 220)]
    assert color.emphasis_spans(grey, [], []) == []                              # not a color cue
    brown = [_span("The result ", "#634c30", 0), _span("improved", "#3c693c", 220),
             _span(" for every group.", "#634c30", 380)]
    assert color.emphasis_spans(brown, [], [])[0]["level"] == 1


# ---------- generated decks with known flaws ----------

DECKS = ["flaws-slides.pptx", "flaws-poster.pptx", "flaws-color.pptx"]


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    if not (render._powerpoint_available() or render._find_soffice()):
        pytest.skip("no PPTX renderer")
    src = ROOT / ".cache" / "test-decks"
    make_test_decks.make_all(src)  # reproducible bytes, so renders below are cached
    out = {}
    for name in DECKS:
        d = render.render(src / name, CACHE)
        extract_text.extract(d)
        ocr.run(d)
        font_size.measure(d)
        contrast.measure(d)
        color.measure(d)
        out[name] = (d, json.loads((src / name).with_suffix(".expected.json").read_text(encoding="utf-8")))
    return out


@pytest.mark.parametrize("name", DECKS)
def test_generated_deck_levels(generated, name):
    d, exp = generated[name]
    text = load(d, "text.json")
    res = {m: load(d, f"{m}.json") for m in ("font_size", "contrast", "color")}
    wrong = []
    for e in exp["expect"]:
        units = [u for u in res[e["measure"]]["units"] if u["page"] == e["page"]]
        if e.get("marker"):
            blocks = {s["block"] for s in text["pages"][e["page"] - 1]["spans"] if e["marker"] in s["text"]}
            units = [u for u in units if u.get("block") in blocks]
        levels = [u[e["key"]]["level"] for u in units if e["key"] in u]
        got = min(levels) if levels else None
        if "level" in e:
            ok = got == e["level"]
        else:  # OCR-dependent: just found, at or below max_level (skipped without OCR)
            ok = got is not None and got <= e["max_level"] or not ocr.ocr_available()
        if not ok:
            wrong.append(f"page {e['page']} {e.get('marker') or ''} {e['measure']} {e['key']}: "
                         f"want {e.get('level', e.get('max_level'))}, got {got} ({e['note']})")
    assert not wrong, "\n".join(wrong)
    for m in res.values():  # hidden slides are never in findings
        for f in m["findings"]:
            assert not set(exp["hidden"]) & {u if isinstance(u, int) else u[0] for u in f["units"]}


def test_color_views_and_scorecard(generated):
    d, _ = generated["flaws-color.pptx"]
    c = load(d, "color.json")
    views = sorted(p.name for p in (d / "color").glob("*.png"))
    assert views == ["p003-deutan.png", "p004-deutan.png", "p005-tritan.png"]  # not hidden p012
    co1 = next(f for f in c["findings"] if f["id"] == "CO-1")
    assert "red-green or blue-yellow color blindness" in co1["headline"] and "color/p004-deutan.png" in co1["details"]
    sc = json.loads(Path(scorecard.build(d)).with_suffix(".json").read_text(encoding="utf-8"))
    names = {i["name"] for i in sc["issues"]}
    assert {"Colors distinguishable with color-vision deficiency", "Emphasis not by color alone"} <= names
    assert "Meaning doesn't depend on color alone" in {i["name"] for i in sc["not_assessed_items"]}
