"""Combine measured and judged results into a scorecard.

Usage:
    python scripts/scorecard.py OUTPUT_DIR [--rubric CONTEXT.md ...]

Reads from OUTPUT_DIR:
    manifest.json      (render.py)      notices, page counts, hidden slides
    font_size.json     (font_size.py)   measured items FS-*
    contrast.json      (contrast.py)    measured items CT-*
    judgments.json     (the agent)      judged items, see below
Rubric: rubrics/default.md, then each --rubric file in order. A later file overrides fields of an
item with the same ID, adds new items, and overrides section weights by name.

judgments.json:
    {"key_ideas": ["...", ...],                      # inferred; [] if unclear
     "items": [{"id": "CN-1", "level": 3, "confidence": "high|medium|low",
                "headline": "one sentence", "details": "optional second line",
                "pages": [4, 9, 12]}]}

Writes OUTPUT_DIR/scorecard.md (for people) and scorecard.json.
Scores: an item has a level 1-4. A section's score is the weighted average of its assessed items'
levels; the overall score is the weighted average of assessed sections. Issues are ranked by
section weight x item's share of its section x (4 - level), then by how many slides are affected.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
LEVEL_RE = re.compile(r"^Level ([1-4])$")
MEASURE_FILES = ("font_size.json", "contrast.json")  # written by the measure scripts


# ---------- rubric ----------

def parse_rubric(text: str) -> tuple[dict, dict]:
    """(sections {name: {weight, notes}}, items {id: {...}}) from a rubric markdown file."""
    sections, items = {}, {}
    part, item = None, None
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("## "):
            part, item = line[3:].strip().lower(), None
            if part == "sections":
                rows = []
                i += 1
                while i < len(lines) and (lines[i].startswith("|") or not lines[i].strip()):
                    if lines[i].startswith("|"):
                        rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                    i += 1
                header = rows[0]
                for r in rows[2:]:
                    row = dict(zip(header, r))
                    sections[row["section"]] = {"weight": float(row["weight"]), "notes": row.get("notes", "")}
                continue
        elif line.startswith("### "):
            m = re.match(r"###\s+(\S+)\s+(.*)", line)
            item = items.setdefault(m.group(1), {"id": m.group(1)})
            item["name"] = m.group(2).strip()
            if part and "measured" in part:
                item.setdefault("type", "measured")
            elif part and "judged" in part:
                item.setdefault("type", "judged")
            item.setdefault("levels", {})
        elif item is not None and (m := re.match(r"^- ([^:]+):\s*(.*)$", line)):
            key, value = m.group(1).strip(), m.group(2).strip()
            if lm := LEVEL_RE.match(key):
                item["levels"][int(lm.group(1))] = value
            elif key == "weight":
                item["weight"] = float(value)
            else:
                item[key] = value
        i += 1
    return sections, items


def load_rubric(extra: list[Path] = ()) -> tuple[dict, dict]:
    sections, items = parse_rubric((SKILL / "rubrics" / "default.md").read_text(encoding="utf-8"))
    for path in extra:
        s2, i2 = parse_rubric(Path(path).read_text(encoding="utf-8"))
        for name, sec in s2.items():
            sections.setdefault(name, {}).update(sec)
        for iid, it in i2.items():
            base = items.setdefault(iid, {"id": iid, "levels": {}})
            levels = {**base.get("levels", {}), **it.pop("levels", {})}
            base.update(it)
            base["levels"] = levels
    return sections, items


# ---------- results ----------

def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def collect_results(out_dir: Path, items: dict) -> tuple[dict, list, dict | None]:
    """{item id: result}, notes about inputs, judgments (or None)."""
    results, problems = {}, []
    for measure_file in MEASURE_FILES:
        fs = _read(out_dir / measure_file)
        if not fs:
            continue
        for iid, it in fs["items"].items():
            if it.get("level") is None:
                continue
            finding = next((f for f in fs["findings"] if f["id"] == iid), None)
            results[iid] = {
                "level": it["level"], "confidence": it.get("confidence", "medium"),
                "headline": finding["headline"] if finding else None,
                "details": finding["details"] if finding else None,
                "count": finding["count"] if finding else 0,
            }
    judgments = _read(out_dir / "judgments.json")
    for j in (judgments or {}).get("items", []):
        iid = j.get("id")
        if iid not in items or items[iid].get("type") != "judged":
            problems.append(f"judgments.json: {iid!r} is not a judged item in the rubric; ignored.")
            continue
        if j.get("level") not in (1, 2, 3, 4):
            problems.append(f"judgments.json: {iid} has no level 1-4; ignored.")
            continue
        pages = j.get("pages") or []
        details = j.get("details") or ""
        if pages:
            details = (details + " " if details else "") + "For example: slides " + \
                ", ".join(map(str, pages[:5])) + "."
        results[iid] = {"level": j["level"], "confidence": j.get("confidence", "medium"),
                        "headline": j.get("headline"), "details": details or None,
                        "count": len(pages)}
    return results, problems, judgments


# ---------- scoring ----------

def score(sections: dict, items: dict, results: dict) -> dict:
    by_section: dict = {}
    for it in items.values():
        by_section.setdefault(it.get("section", "Other"), []).append(it)
    rows, issues, not_assessed_sections, not_assessed_items = [], [], [], []
    total_w = total = 0.0
    for name, sec in sections.items():
        its = by_section.get(name, [])
        done = [it for it in its if it["id"] in results]
        if not done:
            if its:
                not_assessed_items += [it for it in its]
            not_assessed_sections.append(name)
            continue
        w_sum = sum(it.get("weight", 1) for it in done)
        sec_score = sum(it.get("weight", 1) * results[it["id"]]["level"] for it in done) / w_sum
        kinds = {it.get("type") for it in done}
        rows.append({"section": name, "score": round(sec_score, 1), "weight": sec["weight"],
                     "type": "judged" if kinds == {"judged"} else "measured" if kinds == {"measured"} else "mixed",
                     "items": [{"id": it["id"], "name": it["name"], "type": it.get("type"),
                                "level": results[it["id"]]["level"],
                                "confidence": results[it["id"]]["confidence"]} for it in done]})
        not_assessed_items += [it for it in its if it["id"] not in results]
        total += sec["weight"] * sec_score
        total_w += sec["weight"]
        for it in done:
            r = results[it["id"]]
            if r["level"] < 4 and r.get("headline"):
                importance = sec["weight"] * it.get("weight", 1) / w_sum * (4 - r["level"])
                issues.append({"id": it["id"], "name": it["name"], "level": r["level"],
                               "confidence": r["confidence"], "headline": r["headline"],
                               "details": r.get("details"), "importance": round(importance, 3),
                               "count": r.get("count", 0)})
    issues.sort(key=lambda x: (-x["importance"], -x["count"]))
    assessed = sum(len(r["items"]) for r in rows)
    return {"overall": round(total / total_w, 1) if total_w else None,
            "items_assessed": assessed, "items_total": len(items),
            "sections": rows, "issues": issues,
            "not_assessed_sections": not_assessed_sections,
            "not_assessed_items": [{"id": it["id"], "name": it["name"]} for it in not_assessed_items]}


# ---------- report ----------

def _context_line(manifest: dict, fs: dict | None) -> str:
    kind = (fs or {}).get("kind") or manifest.get("kind_guess", "slides")
    pages = manifest["pages"]
    hidden = sum(p["hidden"] for p in pages)
    if kind == "slides":
        what = f"{len(pages)} slides"
        if hidden:
            what += f" ({hidden} hidden, not scored)"
    else:
        what = f"{len(pages)} poster{'s' if len(pages) != 1 else ''}"
    parts = [what]
    if fs:
        p = fs["preset"]
        if p["distance_unit"] == "H":
            parts.append(f"viewing distance {p['distance']:g}× image height")
        else:
            parts.append(f"reading distance {p['distance']:g} m")
        if kind == "poster":
            if fs.get("print_size"):
                parts.append(f"printed at {fs['print_size']}")
            else:
                w, h = pages[0]["width_pt"] / 72, pages[0]["height_pt"] / 72
                parts.append(f"printed at {w:g} × {h:g} in (assumed)")
    return " · ".join(parts)


def render_markdown(src_name: str, context: str, sc: dict, notices: list, judgments: dict | None,
                    problems: list) -> str:
    L = [f"# Scorecard: {src_name}", "", context, ""]
    L += ["| Section and item | Score (1–4) |", "|---|---|"]
    overall = "—" if sc["overall"] is None else f"{sc['overall']:.1f}"
    L.append(f"| **Overall** | **{overall}** |")
    for row in sc["sections"]:
        tag = " (judged)" if row["type"] == "judged" else ""
        L.append(f"| **{row['section']}**{tag} | **{row['score']:.1f}** |")
        for it in row["items"]:
            L.append(f"| &emsp;{it['name']} | {it['level']} |")
    L.append("")
    L.append(f"4 is best. Section and overall scores are weighted averages; "
             f"{sc['items_assessed']} of {sc['items_total']} rubric items assessed.")
    if sc["not_assessed_sections"] or sc["not_assessed_items"]:
        names = [i["name"] for i in sc["not_assessed_items"]]
        L += ["", "**Not assessed yet:** " + "; ".join(
            [", ".join(sc["not_assessed_sections"])] + ([f"items: {', '.join(names)}"] if names else []))]
    if judgments and judgments.get("key_ideas") is not None:
        ki = judgments["key_ideas"]
        L += ["", "**Key ideas (as inferred from the content):**"]
        L += [f"- {k}" for k in ki] if ki else ["- Unclear: no key ideas could be identified."]
    L += ["", "## Issues, most important first", ""]
    if not sc["issues"]:
        L.append("No issues found in the assessed items.")
    for n, iss in enumerate(sc["issues"], 1):
        L.append(f"{n}. **{iss['name']}** ({iss['level']} of 4, {iss['confidence']} confidence): "
                 f"{iss['headline']}")
        if iss.get("details"):
            L.append(f"   {iss['details']}")
    shown = [x for x in notices if x["level"] == "warning"] + [x for x in notices if x["level"] != "warning"]
    if shown or problems:
        L += ["", "## Notes about this review", ""]
        for x in shown:
            label = "Warning" if x["level"] == "warning" else "Note"
            advice = f" {x['advice']}" if x.get("advice") else ""
            L.append(f"- **{label}:** {x['message']}{advice}")
        L += [f"- **Note:** {p}" for p in problems]
    L += ["", "_This review reports issues only; it does not suggest rewrites._", ""]
    return "\n".join(L)


def build(out_dir: Path, extra_rubrics: list[Path] = ()) -> Path:
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    sections, items = load_rubric(extra_rubrics)
    results, problems, judgments = collect_results(out_dir, items)
    sc = score(sections, items, results)
    fs = _read(out_dir / "font_size.json")
    notices = list(manifest.get("notices", []))
    for measure_file in MEASURE_FILES:
        notices += (_read(out_dir / measure_file) or {}).get("notices", [])
    src_name = Path(manifest["source"]).name
    md = render_markdown(src_name, _context_line(manifest, fs), sc, notices, judgments, problems)
    (out_dir / "scorecard.md").write_text(md, encoding="utf-8")
    (out_dir / "scorecard.json").write_text(json.dumps(
        {"source": manifest["source"], **sc, "notices": notices, "problems": problems,
         "key_ideas": (judgments or {}).get("key_ideas")}, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_dir / "scorecard.md"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--rubric", type=Path, action="append", default=[],
                    help="context rubric that overrides the default (repeatable)")
    a = ap.parse_args(argv)
    if not (a.out_dir / "manifest.json").exists():
        print(f"error: no manifest.json in {a.out_dir}; run render.py first", file=sys.stderr)
        return 2
    print(build(a.out_dir, a.rubric).read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
