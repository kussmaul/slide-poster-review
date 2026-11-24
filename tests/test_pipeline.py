"""Pipeline tests on the local files in test-inputs/ (not in git; tests skip if missing)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skill" / "slide-poster-review"
sys.path.insert(0, str(SKILL / "scripts"))
import extract_text  # noqa: E402
import render  # noqa: E402

INPUTS = ROOT / "test-inputs"
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
    out = render.render(POSTERS, tmp_path_factory.mktemp("out"), dpi=150, max_px=8000)
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
    root = tmp_path_factory.mktemp("genai")
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
