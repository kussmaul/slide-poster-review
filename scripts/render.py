"""Render a slide deck or poster to a PDF plus one PNG per page, and write manifest.json.

Usage:
    python scripts/render.py INPUT [--out OUTPUT_ROOT] [--dpi 150] [--max-px 8000]
                             [--backend auto|powerpoint|libreoffice]

INPUT is a .pdf or a PowerPoint file (.pptx/.ppt/.pptm/.odp). Google Slides: export to .pptx or .pdf.
Output goes to OUTPUT_ROOT/<input stem>/ (default OUTPUT_ROOT = ./output):
    source.pdf          the PDF that was rendered (a copy, for PDF inputs)
    pages/page-NNN.png  one image per page
    manifest.json       page sizes, scale, hidden flags, renderer, fonts, warnings

PPTX -> PDF backends (auto order): PowerPoint via COM (Windows), then LibreOffice if already
installed. If neither is available, export a PDF and pass that instead.
Exit codes: 0 ok, 2 bad input / unsupported, 3 no backend or conversion failed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pymupdf

SCRIPTS = Path(__file__).resolve().parent
PPT_EXTS = {".pptx", ".ppt", ".pptm", ".odp"}
OUT_OF_SCOPE = {".docx", ".doc", ".odt", ".key"}
POSTER_MIN_INCHES = 20  # longest side at or above this => guess "poster"
MANIFEST_VERSION = 1


class RenderError(Exception):
    def __init__(self, msg: str, code: int = 3):
        super().__init__(msg)
        self.code = code


# ---------- PPTX -> PDF backends ----------

def _powerpoint_available() -> bool:
    if os.name != "nt" or not shutil.which("powershell"):
        return False
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "PowerPoint.Application"))
        return True
    except OSError:
        return False


def _find_soffice() -> str | None:
    for name in ("soffice", "libreoffice"):
        if p := shutil.which(name):
            return p
    candidates = [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ]
    return next((c for c in candidates if Path(c).exists()), None)


def _convert_powerpoint(src: Path, dst: Path) -> None:
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
           "-File", str(SCRIPTS / "pptx_to_pdf.ps1"), str(src), str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not dst.exists():
        raise RenderError(f"PowerPoint export failed: {r.stderr.strip() or r.stdout.strip()}")


def _convert_libreoffice(src: Path, dst: Path, soffice: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        # Separate profile dir so a running LibreOffice instance doesn't block headless use.
        profile = Path(tmp, "profile").as_uri()
        cmd = [soffice, f"-env:UserInstallation={profile}", "--headless",
               "--convert-to", "pdf", "--outdir", tmp, str(src)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        out = Path(tmp, src.stem + ".pdf")
        if r.returncode != 0 or not out.exists():
            raise RenderError(f"LibreOffice export failed: {r.stderr.strip() or r.stdout.strip()}")
        shutil.move(out, dst)


def convert_to_pdf(src: Path, dst: Path, backend: str = "auto") -> str:
    """Convert a PowerPoint file to PDF. Returns the backend name used."""
    order = ["powerpoint", "libreoffice"] if backend == "auto" else [backend]
    tried = []
    for b in order:
        if b == "powerpoint" and _powerpoint_available():
            _convert_powerpoint(src, dst)
            return "powerpoint"
        if b == "libreoffice" and (soffice := _find_soffice()):
            _convert_libreoffice(src, dst, soffice)
            return "libreoffice"
        tried.append(b)
    raise RenderError(
        f"No PPTX renderer available (tried: {', '.join(tried)}). "
        "Export the file to PDF (one slide per page) and pass the PDF instead.")


# ---------- PPTX facts the PDF loses ----------

def pptx_slide_facts(src: Path) -> dict | None:
    """Hidden flags and slide size from the PPTX, or None if it can't be read."""
    if src.suffix.lower() not in {".pptx", ".pptm"}:
        return None
    try:
        from pptx import Presentation
        prs = Presentation(str(src))
    except Exception:
        return None
    return {
        "hidden": [s._element.get("show") in ("0", "false") for s in prs.slides],
        "width_in": prs.slide_width / 914400,
        "height_in": prs.slide_height / 914400,
    }


# ---------- PDF checks ----------

def detect_handout(doc: pymupdf.Document, sample: int = 6) -> bool:
    """True if most sampled pages hold several same-size slide-shaped frames (an N-up handout)."""
    pages = list(doc)[:sample]
    hits = sum(1 for page in pages if _looks_like_handout_page(page))
    return bool(pages) and hits > len(pages) / 2


def _looks_like_handout_page(page: pymupdf.Page) -> bool:
    """Some slide-shaped frame size (aspect 1.2-1.85, 3-60% of the page) appears at >= 2 positions."""
    area = page.rect.width * page.rect.height
    rects = [g["rect"] for g in page.get_drawings()]
    rects += [pymupdf.Rect(i["bbox"]) for i in page.get_image_info()]
    positions: dict[tuple, set] = {}
    for r in rects:
        a = r.width * r.height
        if r.height <= 0 or not (0.03 * area <= a <= 0.6 * area) or not (1.2 <= r.width / r.height <= 1.85):
            continue
        positions.setdefault((round(r.width), round(r.height)), set()).add((round(r.x0), round(r.y0)))
    return any(len(p) >= 2 for p in positions.values())


def base_font_name(name: str) -> str:
    """Strip a PDF subset prefix like 'ABCDEF+'."""
    return re.sub(r"^[A-Z]{6}\+", "", name)


# ---------- main pipeline ----------

def render(src: Path, out_root: Path, dpi: int = 150, max_px: int = 8000,
           backend: str = "auto") -> Path:
    src = src.resolve()
    if not src.exists():
        raise RenderError(f"Input not found: {src}", 2)
    ext = src.suffix.lower()
    if ext in OUT_OF_SCOPE:
        raise RenderError(f"{ext} files are not supported yet (slides and posters only).", 2)
    if ext != ".pdf" and ext not in PPT_EXTS:
        raise RenderError(f"Unsupported input type: {ext}", 2)

    out_dir = out_root / src.stem
    pages_dir = out_dir / "pages"
    out_dir.mkdir(parents=True, exist_ok=True)
    if pages_dir.exists():
        shutil.rmtree(pages_dir)
    pages_dir.mkdir()
    pdf_path = out_dir / "source.pdf"
    warnings: list[str] = []

    if ext == ".pdf":
        shutil.copyfile(src, pdf_path)
        used = "pdf"
    else:
        used = convert_to_pdf(src, pdf_path, backend)

    doc = pymupdf.open(pdf_path)
    if doc.page_count == 0:
        raise RenderError("PDF has no pages.", 2)
    if ext == ".pdf" and detect_handout(doc):
        raise RenderError(
            "This PDF looks like a handout (several slides per page). "
            "Export one slide per page and try again.", 2)

    facts = pptx_slide_facts(src)
    hidden = facts["hidden"] if facts else []
    if facts and len(hidden) != doc.page_count:
        warnings.append(f"PPTX has {len(hidden)} slides but PDF has {doc.page_count} pages; "
                        "hidden flags not applied.")
        hidden = []

    pages = []
    for i, page in enumerate(doc):
        w_in, h_in = page.rect.width / 72, page.rect.height / 72
        page_dpi = min(dpi, max_px / max(w_in, h_in))
        pix = page.get_pixmap(dpi=round(page_dpi) or 1, alpha=False)
        name = f"page-{i + 1:03d}.png"
        pix.save(pages_dir / name)
        pages.append({
            "index": i + 1,
            "image": f"pages/{name}",
            "width_pt": round(page.rect.width, 3),
            "height_pt": round(page.rect.height, 3),
            "width_px": pix.width,
            "height_px": pix.height,
            # Use these (not dpi) for conversions; pixmap sizes are rounded to whole pixels.
            "px_per_pt_x": pix.width / page.rect.width,
            "px_per_pt_y": pix.height / page.rect.height,
            "rotation": page.rotation,
            "hidden": hidden[i] if hidden else False,
        })

    sizes = {(p["width_pt"], p["height_pt"]) for p in pages}
    if len(sizes) > 1:
        warnings.append(f"Pages have {len(sizes)} different sizes.")
    longest_in = max(max(w, h) for w, h in sizes) / 72
    pdf_fonts = sorted({base_font_name(f[3]) for p in doc for f in p.get_fonts()})

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "source": str(src),
        "source_type": "pdf" if ext == ".pdf" else "pptx",
        "renderer": used,
        "rendered_at": dt.datetime.now().isoformat(timespec="seconds"),
        "pdf": "source.pdf",
        "page_count": doc.page_count,
        "kind_guess": "poster" if longest_in >= POSTER_MIN_INCHES else "slides",
        "requested_dpi": dpi,
        "max_px": max_px,
        "pptx_slide_size_in": [facts["width_in"], facts["height_in"]] if facts else None,
        "pdf_metadata": {k: v for k, v in doc.metadata.items() if v},
        "pdf_fonts": pdf_fonts,
        "pages": pages,
        "warnings": warnings,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out_dir


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("input", type=Path)
    ap.add_argument("--out", type=Path, default=Path("output"), help="output root (default ./output)")
    ap.add_argument("--dpi", type=int, default=150)
    ap.add_argument("--max-px", type=int, default=8000, help="cap on the longest image side")
    ap.add_argument("--backend", choices=["auto", "powerpoint", "libreoffice"], default="auto")
    a = ap.parse_args(argv)
    try:
        out = render(a.input, a.out, a.dpi, a.max_px, a.backend)
    except RenderError as e:
        print(f"error: {e}", file=sys.stderr)
        return e.code
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
