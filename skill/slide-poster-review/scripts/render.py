"""Render a slide deck or poster to a PDF plus one PNG per page, and write manifest.json.

Usage:
    python scripts/render.py INPUT [--out OUTPUT_ROOT] [--dpi 150] [--max-px 8000]
                             [--backend auto|powerpoint|libreoffice]

INPUT is a .pdf or a PowerPoint file (.pptx/.ppt/.pptm/.odp). Google Slides: export to .pptx or .pdf.
Output goes to OUTPUT_ROOT/<stem>-<ext>/, e.g. output/deck-pptx/ (default OUTPUT_ROOT = ./output):
    source.pdf          the PDF that was rendered (a copy, for PDF inputs)
    pages/page-NNN.png  one image per page
    manifest.json       page sizes, scale, hidden flags, renderer, source app, fonts, notices

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
        raise RenderError(r.stderr.strip() or r.stdout.strip() or "PowerPoint export failed")


def _convert_libreoffice(src: Path, dst: Path, soffice: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        # Separate profile dir so a running LibreOffice instance doesn't block headless use.
        profile = Path(tmp, "profile").as_uri()
        # Include hidden slides (LibreOffice 7.4+ JSON filter options); render.py marks them.
        fmt = 'pdf:impress_pdf_Export:{"ExportHiddenSlides":{"type":"boolean","value":"true"}}'
        cmd = [soffice, f"-env:UserInstallation={profile}", "--headless",
               "--convert-to", fmt, "--outdir", tmp, str(src)]
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
        # PowerPoint (16.0) reports Google Slides .odp exports as corrupted, so .odp needs LibreOffice.
        if b == "powerpoint" and src.suffix.lower() == ".odp":
            tried.append("powerpoint (can't read .odp)")
            continue
        if b == "powerpoint" and _powerpoint_available():
            _convert_powerpoint(src, dst)
            return "powerpoint"
        if b == "libreoffice" and (soffice := _find_soffice()):
            _convert_libreoffice(src, dst, soffice)
            return "libreoffice"
        tried.append(b)
    raise RenderError(
        f"No renderer available for {src.suffix} (tried: {', '.join(tried)}). "
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
    theme = pptx_theme_fonts(prs)
    requested = set(theme.values())
    for part in [prs.slide_master.part] + [s.slide_layout.part for s in prs.slides] + [s.part for s in prs.slides]:
        for typeface in part._element.xpath(".//a:latin/@typeface"):
            requested.add(theme.get(typeface, typeface))
    return {
        "hidden": [s._element.get("show") in ("0", "false") for s in prs.slides],
        "width_in": prs.slide_width / 914400,
        "height_in": prs.slide_height / 914400,
        "theme_fonts": theme,
        "requested_fonts": sorted(f for f in requested if f and not f.startswith("+")),
        "embedded_fonts": prs.part._element.xpath(".//p:embeddedFont/p:font/@typeface"),
    }


def pptx_theme_fonts(prs) -> dict[str, str]:
    """Theme major/minor latin fonts, keyed by the '+mj-lt' / '+mn-lt' aliases runs use."""
    from pptx.opc.constants import RELATIONSHIP_TYPE as RT
    fonts = {}
    try:
        xml = prs.slide_master.part.part_related_by(RT.THEME).blob.decode("utf-8", "replace")
        for key, tag in (("+mj-lt", "majorFont"), ("+mn-lt", "minorFont")):
            if m := re.search(rf"<a:{tag}>\s*<a:latin typeface=\"([^\"]+)\"", xml):
                fonts[key] = m.group(1)
    except Exception:
        pass
    return fonts


# ---------- fonts ----------

STYLE_WORDS = re.compile(r"(regular|bold|italic|oblique|bolditalic)+$")


def norm_font(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def installed_font_families() -> set[str] | None:
    """Normalized names of installed font families, or None if they can't be listed."""
    names: list[str] = []
    if os.name == "nt":
        import winreg
        key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hive, key_path) as k:
                    for i in range(winreg.QueryInfoKey(k)[1]):
                        label = winreg.EnumValue(k, i)[0]
                        label = re.sub(r"\s*\((TrueType|OpenType|All res)\)$", "", label)
                        names += label.split(" & ")
            except OSError:
                continue
    elif shutil.which("fc-list"):
        r = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True)
        for line in r.stdout.splitlines():
            names += line.split(",")
    else:
        return None
    out = set()
    for n in names:
        n = norm_font(n)
        out.add(n)
        out.add(STYLE_WORDS.sub("", n))
    return out


def font_report(requested: list[str], pdf_fonts: list[str], embedded: list[str]) -> dict:
    """Which requested fonts made it into the PDF, and which were substituted.

    A font is 'substituted' when it is requested, not installed, and absent from the PDF.
    Absent but installed = simply unused (e.g. a theme font no text uses). Not installed but
    present = the renderer used the copy embedded in the file. Embedded fonts can still be
    ignored (PowerPoint skipped an embedded Gill Sans, probably due to its license flags).
    """
    pdf_norm = [norm_font(f) for f in pdf_fonts]
    not_in_pdf = [f for f in requested if not any(p.startswith(norm_font(f)) for p in pdf_norm)]
    installed = installed_font_families()
    not_installed = None if installed is None else [f for f in requested if norm_font(f) not in installed]
    return {
        "requested": requested,
        "embedded_in_source": embedded,
        "in_pdf": pdf_fonts,
        "not_in_pdf": not_in_pdf,
        "not_installed": not_installed,  # None = couldn't list installed fonts
        "substituted": None if not_installed is None else [f for f in not_installed if f in not_in_pdf],
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


# ---------- source app and notices ----------

APP_LABELS = {"google_slides": "Google Slides", "powerpoint": "PowerPoint", "libreoffice": "LibreOffice",
              "keynote": "Keynote", "canva": "Canva", "unknown": "an unknown app"}


def detect_source_app(src: Path, doc: pymupdf.Document) -> dict:
    """Best guess at the app that produced the input: {app, confidence, evidence}."""
    if src.suffix.lower() == ".pdf":
        md = doc.metadata or {}
        tag = f"{md.get('creator') or ''} {md.get('producer') or ''}".strip()
        for needle, app in (("Google", "google_slides"), ("PowerPoint", "powerpoint"),
                            ("LibreOffice", "libreoffice"), ("OpenOffice", "libreoffice"),
                            ("Keynote", "keynote"), ("Canva", "canva")):
            if needle.lower() in tag.lower():
                return {"app": app, "confidence": "high", "evidence": f"PDF creator/producer: {tag}"}
        return {"app": "unknown", "confidence": "low", "evidence": f"PDF creator/producer: {tag or '(none)'}"}
    if src.suffix.lower() in {".pptx", ".pptm"}:
        import zipfile
        try:
            with zipfile.ZipFile(src) as z:
                names = set(z.namelist())
                app_xml = z.read("docProps/app.xml").decode("utf-8", "replace") \
                    if "docProps/app.xml" in names else None
        except (OSError, zipfile.BadZipFile):
            return {"app": "unknown", "confidence": "low", "evidence": "unreadable package"}
        if app_xml is None:
            fntdata = any(n.endswith(".fntdata") for n in names)
            return {"app": "google_slides", "confidence": "likely",
                    "evidence": "no docProps/app.xml" + (" and .fntdata fonts" if fntdata else "")
                                + " (typical of Google Slides exports)"}
        m = re.search(r"<Application>([^<]*)</Application>", app_xml)
        name = m.group(1) if m else ""
        for needle, app in (("PowerPoint", "powerpoint"), ("LibreOffice", "libreoffice"),
                            ("OpenOffice", "libreoffice"), ("Keynote", "keynote")):
            if needle.lower() in name.lower():
                return {"app": app, "confidence": "high", "evidence": f"docProps/app.xml Application: {name}"}
        return {"app": "unknown", "confidence": "low",
                "evidence": f"docProps/app.xml Application: {name or '(none)'}"}
    return {"app": "unknown", "confidence": "low", "evidence": f"{src.suffix} file"}


def notice(code: str, level: str, message: str, advice: str | None = None) -> dict:
    """For the user: 'warning' = may change results; 'info' = limits what can be checked."""
    return {"code": code, "level": level, "message": message, "advice": advice}


def source_notices(src: Path, source: dict, ext: str) -> list[dict]:
    app, name = source["app"], src.name
    label = APP_LABELS.get(app, app)
    seems = "was" if source["confidence"] == "high" else "appears to be"
    out = []
    if ext == ".pdf":
        if app == "google_slides":
            skipped = "Skipped slides are included but can't be identified"
            native = "In Google Slides, use File > Download > Microsoft PowerPoint (.pptx)."
        elif app == "powerpoint":
            skipped = ("Hidden slides can't be identified (PowerPoint usually leaves them out, so "
                       "page numbers may not match slide numbers)")
            native = "Provide the original .pptx file."
        else:
            skipped = "Hidden slides can't be identified"
            native = "Provide the original .pptx file, if there is one."
        out.append(notice(
            "SRC-PDF", "info",
            f"{name} {seems} exported from {label} as a PDF. {skipped}, and alt text isn't "
            "available, so those checks are skipped.",
            f"For those checks: {native}"))
    elif app == "google_slides":
        out.append(notice(
            "SRC-GSLIDES-PPTX", "info",
            f"{name} {seems} exported from Google Slides. It is rendered here with another app, so "
            "small layout differences from Google Slides are possible (e.g. list numbering, spacing).",
            "If a slide looks different from Google Slides, check it there."))
    return out


def font_notice(src: Path, source: dict, fonts: dict) -> dict | None:
    if fonts.get("substituted"):
        if source["app"] == "google_slides":
            export = ("download it from Google Slides as PDF (File > Download > PDF), though that PDF "
                      "won't allow alt-text or skipped-slide checks")
        else:
            export = "export a PDF on a computer that has the fonts"
        return notice(
            "FONT-SUB", "warning",
            f"{src.name} uses fonts that aren't installed here ({', '.join(fonts['substituted'])}), "
            "so other fonts were used. Line breaks, text size, and overflow may differ from what "
            "the audience sees.",
            f"Install the fonts, or {export}.")
    if fonts.get("substituted") is None and fonts.get("not_in_pdf"):
        return notice(
            "FONT-UNKNOWN", "warning",
            f"{src.name} requests fonts that aren't in the rendered PDF "
            f"({', '.join(fonts['not_in_pdf'])}); they may be unused or substituted "
            "(installed fonts could not be checked).",
            "If these fonts are used, make sure they are installed, or provide a PDF export.")
    return None


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

    out_dir = out_root / f"{src.stem}-{ext[1:]}"  # same deck in several formats must not collide
    pages_dir = out_dir / "pages"
    out_dir.mkdir(parents=True, exist_ok=True)
    if pages_dir.exists():
        shutil.rmtree(pages_dir)
    pages_dir.mkdir()
    pdf_path = out_dir / "source.pdf"
    notices: list[dict] = []

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

    source = detect_source_app(src, doc)
    notices += source_notices(src, source, ext)
    facts = pptx_slide_facts(src)
    hidden = facts["hidden"] if facts else []
    if facts and len(hidden) != doc.page_count:
        notices.append(notice(
            "PAGE-COUNT", "warning",
            f"{src.name} has {len(hidden)} slides but the rendered PDF has {doc.page_count} pages, "
            "so hidden slides can't be identified."))
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
        notices.append(notice("PAGE-SIZES", "warning",
                              f"{src.name} has pages in {len(sizes)} different sizes."))
    longest_in = max(max(w, h) for w, h in sizes) / 72
    pdf_fonts = sorted({base_font_name(f[3]) for p in doc for f in p.get_fonts()})
    if facts:
        fonts = font_report(facts["requested_fonts"], pdf_fonts, facts["embedded_fonts"])
        fonts["theme"] = facts["theme_fonts"]
        if n := font_notice(src, source, fonts):
            notices.append(n)
    else:
        fonts = {"in_pdf": pdf_fonts}  # PDF inputs carry their own (embedded) fonts

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "source": str(src),
        "source_type": ext[1:],
        "source_app": source,
        "renderer": used,
        "rendered_at": dt.datetime.now().isoformat(timespec="seconds"),
        "pdf": "source.pdf",
        "page_count": doc.page_count,
        "kind_guess": "poster" if longest_in >= POSTER_MIN_INCHES else "slides",
        "requested_dpi": dpi,
        "max_px": max_px,
        "pptx_slide_size_in": [facts["width_in"], facts["height_in"]] if facts else None,
        # PDF exports (e.g. Google Slides) may include skipped slides without marking them.
        "hidden_flags_known": bool(hidden),
        "pdf_metadata": {k: v for k, v in doc.metadata.items() if v},
        "fonts": fonts,
        "pages": pages,
        # Shown to the user: {code, level: warning|info, message, advice}
        "notices": notices,
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
    for n in json.loads((out / "manifest.json").read_text(encoding="utf-8"))["notices"]:
        advice = f" {n['advice']}" if n["advice"] else ""
        print(f"[{n['level']}] {n['code']}: {n['message']}{advice}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
