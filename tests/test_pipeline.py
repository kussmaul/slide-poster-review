"""Pipeline tests on the local files in test-inputs/ (not in git; tests skip if missing)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
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
    assert m["warnings"] == []


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
    x = load(posters_out, "text.json")["pptx"]
    assert x["fonts_not_in_pdf"] == ["Calibri Light"]  # theme heading font, unused
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
