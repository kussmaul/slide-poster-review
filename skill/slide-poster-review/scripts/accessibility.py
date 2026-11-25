"""Check accessibility metadata in a .pptx (rubric items AC-1 to AC-3).

Usage:
    python scripts/accessibility.py OUTPUT_DIR [--kind slides|poster]

Needs manifest.json and text.json (render.py, extract_text.py). Only a .pptx source has this
metadata; for other sources the items are not assessed and a notice says why. Writes
OUTPUT_DIR/accessibility.json (same layout as font_size.json).

These matter when the file itself is shared, e.g. posted for students who use a screen reader.
They follow Microsoft's Accessibility Checker and WCAG 2.x.

AC-1  Alt text (WCAG 1.1.1 Non-text Content). Pictures, charts, SmartArt, media, and embedded
      objects need alt text unless marked decorative. A picture inside a group with alt text is
      covered. Alt text that is only a file or default name ("image1.png", "Picture 3") counts
      as missing; text Office generated automatically ("Description automatically generated")
      counts as present but unchecked.
        Level 4  all have alt text, none auto-generated
        Level 3  90% or more have alt text (or all, some auto-generated)
        Level 2  50% or more             Level 1  under 50%
AC-2  Slide titles (WCAG 2.4.2 Page Titled, 2.4.6 Headings and Labels). Screen-reader users
      navigate by slide title. Text that looks like a title but isn't in the title placeholder
      doesn't count. Share of shown slides without a title:
        Level 4  none (Level 3 if titles repeat on non-consecutive slides)
        Level 3  up to 10%   Level 2  up to 25%   Level 1  more than 25%
AC-3  Reading order (WCAG 1.3.2 Meaningful Sequence). Screen readers read shapes in the order
      they were added. Titled slides where another shape is read before the title:
        Level 4  none   Level 3  up to 10%   Level 2  up to 25%   Level 1  more than 25%
Posters: AC-1 only. Hidden slides are not scored.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT_NAME = re.compile(r"^(picture|image|graphic|chart|diagram|content placeholder|object|"
                          r"grafik|bild|imagen|immagine)\s*\d*$|\.(png|jpe?g|gif|svg|emf|wmf|bmp|tiff?|webp)$",
                          re.IGNORECASE)
AUTO_ALT = re.compile(r"description automatically generated|ai-generated content may be incorrect",
                      re.IGNORECASE)


def alt_status(shape: dict) -> str:
    """'ok', 'auto', or 'missing' for one shape that needs alt text."""
    alt = (shape.get("alt_text") or "").strip()
    if not alt or DEFAULT_NAME.search(alt) or alt == shape.get("name"):
        return "missing"
    return "auto" if AUTO_ALT.search(alt) else "ok"


def _share_level(n: int, total: int) -> int:
    if n == 0:
        return 4
    share = n / total
    return 3 if share <= 0.10 else 2 if share <= 0.25 else 1


def _where(pages: list[int], word: str) -> str:
    pages = sorted(set(pages))
    return f"{word}{'s' if len(pages) != 1 else ''} " + ", ".join(map(str, pages[:3]))


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip().lower()


def measure(out_dir: Path, kind: str | None = None) -> Path:
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    text = json.loads((out_dir / "text.json").read_text(encoding="utf-8"))
    kind = kind or manifest["kind_guess"]
    pptx = text.get("pptx")
    word = "slide" if kind == "slides" else "page"
    items, findings, notices, units = {}, [], [], []
    if not pptx:
        for iid in ("AC-1", "AC-2", "AC-3"):
            items[iid] = {"level": None, "units": 0}
        notices.append({"code": "AC-NO-PPTX", "level": "info",
                        "message": "Alt text, slide titles, and reading order weren't checked: they are "
                                   "only available in a .pptx file.",
                        "advice": "Review the .pptx to check these, if the file will be shared."})
        return _write(out_dir, kind, items, findings, notices, units)

    shown = [s for s in pptx["slides"] if not s["hidden"]]

    # AC-1
    images = []
    for s in shown:
        group_alt = {sh["name"]: alt_status(sh) for sh in s["shapes"] if sh["type"] == "GROUP"}
        for sh in s["shapes"]:
            if sh.get("media") != "image" or sh.get("decorative"):
                continue
            status = alt_status(sh)
            if status == "missing" and group_alt.get(sh.get("group")) in ("ok", "auto"):
                status = group_alt[sh["group"]]
            images.append({"page": s["index"], "name": sh["name"], "type": sh["type"], "status": status})
    if images:
        missing = [x for x in images if x["status"] == "missing"]
        auto = [x for x in images if x["status"] == "auto"]
        have = 1 - len(missing) / len(images)
        level = (4 if not missing and not auto else 3 if have >= 0.9 else 2 if have >= 0.5 else 1)
        items["AC-1"] = {"level": level, "units": len(images), "confidence": "high",
                         "missing": len(missing), "auto": len(auto)}
        if level < 4:
            parts = []
            if missing:
                parts.append(f"{len(missing)} of {len(images)} pictures, charts, or other graphics have no alt text")
            if auto:
                parts.append(f"{len(auto)} have auto-generated alt text that may not describe their purpose")
            pages = [x["page"] for x in (missing or auto)]
            findings.append({"id": "AC-1", "level": level, "count": len(missing) + len(auto), "confidence": "high",
                             "headline": "; ".join(parts).capitalize() + ".",
                             "details": f"For example: {_where(pages, word)}. Graphics that add nothing can be "
                                        "marked decorative instead.",
                             "units": sorted(set(pages))})
    else:
        items["AC-1"] = {"level": None, "units": 0}

    # AC-2, AC-3 (slides only)
    if kind == "slides" and shown:
        untitled = [s["index"] for s in shown if not (s.get("title") or "").strip()]
        by_title = defaultdict(list)
        for s in shown:
            if (s.get("title") or "").strip():
                by_title[_norm(s["title"])].append(s["index"])
        repeats = {t: p for t, p in by_title.items()
                   if len(p) > 1 and any(b - a > 1 for a, b in zip(p, p[1:]))}
        level = _share_level(len(untitled), len(shown))
        if level == 4 and repeats:
            level = 3
        items["AC-2"] = {"level": level, "units": len(shown), "confidence": "high",
                         "untitled": len(untitled), "repeated_titles": len(repeats)}
        if untitled or repeats:
            parts, details = [], []
            if untitled:
                parts.append(f"{len(untitled)} {word}{'s' if len(untitled) != 1 else ''} "
                             f"{'have' if len(untitled) != 1 else 'has'} no title that a screen reader can find")
                details.append(f"For example: {_where(untitled, word)}. Text that looks like a title but is in a "
                               "text box doesn't count.")
            if repeats:
                t, p = max(repeats.items(), key=lambda kv: len(kv[1]))
                parts.append(f"{len(repeats)} title{'s are' if len(repeats) != 1 else ' is'} repeated on "
                             "separate slides")
                details.append(f"E.g. \"{t[:40]}\" on {_where(p, word)}.")
            findings.append({"id": "AC-2", "level": level, "count": len(untitled) + len(repeats),
                             "confidence": "high", "headline": "; ".join(parts).capitalize() + ".",
                             "details": " ".join(details), "units": untitled or sorted({x for p in repeats.values() for x in p})})

        titled = [s for s in shown if s.get("title_order") is not None]
        late = [s["index"] for s in titled if s["title_order"] > 0]
        if titled:
            level = _share_level(len(late), len(titled))
            items["AC-3"] = {"level": level, "units": len(titled), "confidence": "high", "title_not_first": len(late)}
            if late:
                findings.append({"id": "AC-3", "level": level, "count": len(late), "confidence": "high",
                                 "headline": f"On {len(late)} {word}{'s' if len(late) != 1 else ''}, a screen reader "
                                             "reads something else before the title.",
                                 "details": f"For example: {_where(late, word)}. Check the reading order "
                                            "(PowerPoint: Home > Arrange > Selection Pane).",
                                 "units": late})
        else:
            items["AC-3"] = {"level": None, "units": 0}
    else:
        items["AC-2"] = {"level": None, "units": 0}
        items["AC-3"] = {"level": None, "units": 0}

    for f in findings:
        f["summary"] = f"{f['id']}: {f['headline']} {f['details']}"
    for s in pptx["slides"]:
        units.append({"page": s["index"], "hidden": s["hidden"], "title": s.get("title"),
                      "title_order": s.get("title_order"),
                      "images": [x for x in images if x["page"] == s["index"]]})
    findings.sort(key=lambda f: (f["level"], -f["count"]))
    return _write(out_dir, kind, items, findings, notices, units)


def _write(out_dir, kind, items, findings, notices, units) -> Path:
    path = out_dir / "accessibility.json"
    path.write_text(json.dumps({"measure": "accessibility", "kind": kind, "items": items, "findings": findings,
                                "notices": notices, "units": units}, indent=2, ensure_ascii=False),
                    encoding="utf-8")
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
        print(f"{iid}: level {it['level']}")
    for f in res["findings"]:
        print(f["summary"])
    for n in res["notices"]:
        print(f"note: {n['message']}")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # Windows consoles and pipes default to cp1252
        stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
