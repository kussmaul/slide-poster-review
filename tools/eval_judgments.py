"""Dev tool: evaluate the agent's judged items on decks with known judged levels.

Usage:
    python tools/eval_judgments.py prepare [EVAL_DIR]   # render + measure the judged-* decks
    python tools/eval_judgments.py check   [EVAL_DIR]   # compare each judgments.json with expected

EVAL_DIR defaults to .cache/evals/. `prepare` regenerates the decks (tools/make_test_decks.py),
runs the measuring scripts on every deck that has "judged" levels in its .expected.json, and
lists the OUTPUT_DIRs. Expected levels are NOT copied there, so an agent can do step 3 ("Judge")
of SKILL.md on each OUTPUT_DIR blind, e.g. a fresh session or subagent given only the skill and
the folder. It writes OUTPUT_DIR/judgments.json.

`check` reports, per deck and item, the judged level against the acceptable range, then the key
ideas found, and writes EVAL_DIR/eval-report.md. Exit code 1 if any item is missing or out of range.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "slide-poster-review" / "scripts"))
sys.path.insert(0, str(ROOT / "tools"))

DECKS = ROOT / ".cache" / "test-decks"


def judged_decks() -> list[tuple[Path, dict]]:
    import make_test_decks
    make_test_decks.make_all(DECKS)
    out = []
    for exp_path in sorted(DECKS.glob("*.expected.json")):
        exp = json.loads(exp_path.read_text(encoding="utf-8"))
        if exp.get("judged"):
            out.append((DECKS / exp["deck"], exp))
    return out


def prepare(eval_dir: Path) -> list[Path]:
    import accessibility, color, contrast, extract_text, font_size, layout, ocr, readability, render  # noqa: E401
    dirs = []
    for src, exp in judged_decks():
        d = render.render(src, eval_dir)
        extract_text.extract(d)
        ocr.run(d)
        font_size.measure(d, print_size=exp.get("print_size"))
        contrast.measure(d, print_size=exp.get("print_size"))
        color.measure(d)
        readability.measure(d)
        layout.measure(d)
        accessibility.measure(d)
        dirs.append(d)
    return dirs


def check_one(d: Path, exp: dict) -> tuple[list[str], int, int]:
    """(report lines, items passed, items expected)."""
    lines = [f"## {exp['deck']}", ""]
    jpath = d / "judgments.json"
    if not jpath.exists():
        return lines + [f"No judgments.json in {d}.", ""], 0, len(exp["judged"])
    j = json.loads(jpath.read_text(encoding="utf-8"))
    got = {it["id"]: it for it in j.get("items", [])}
    lines += ["| Item | Judged | Expected | Confidence | Result |", "|---|---|---|---|---|"]
    passed = 0
    for iid, (lo, hi) in sorted(exp["judged"].items()):
        it = got.get(iid)
        lvl = it.get("level") if it else None
        ok = lvl is not None and lo <= lvl <= hi
        passed += ok
        lines.append(f"| {iid} | {lvl if lvl is not None else '(missing)'} | {lo}-{hi} | "
                     f"{it.get('confidence', '') if it else ''} | {'pass' if ok else 'FAIL'} |")
    lines.append("")
    if exp.get("key_ideas"):
        stated = [k.lower() for k in j.get("key_ideas", [])]
        hits = [any(w.lower() in k for k in stated for w in words) for words in exp["key_ideas"]]
        lines.append(f"Key ideas matched: {sum(hits)} of {len(hits)}. Stated: "
                     + ("; ".join(j.get("key_ideas", [])) or "(none)"))
        lines.append("")
    for iid in sorted(set(got) - set(exp["judged"])):
        lines.append(f"Also judged (not scored here): {iid} = {got[iid].get('level')}")
    return lines, passed, len(exp["judged"])


def check(eval_dir: Path) -> int:
    lines, total_pass, total = ["# Judged-item eval", ""], 0, 0
    for src, exp in judged_decks():
        d = eval_dir / f"{src.stem}-{src.suffix[1:]}"
        part, p, n = check_one(d, exp)
        lines += part
        total_pass, total = total_pass + p, total + n
    lines[1:1] = ["", f"**{total_pass} of {total} judged items within the expected range.**"]
    report = "\n".join(lines) + "\n"
    (eval_dir / "eval-report.md").write_text(report, encoding="utf-8")
    print(report)
    return 0 if total_pass == total else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("action", choices=["prepare", "check"])
    ap.add_argument("eval_dir", nargs="?", type=Path, default=ROOT / ".cache" / "evals")
    a = ap.parse_args()
    a.eval_dir.mkdir(parents=True, exist_ok=True)
    if a.action == "prepare":
        for d in prepare(a.eval_dir):
            print(d)
        return 0
    return check(a.eval_dir)


if __name__ == "__main__":
    sys.exit(main())
