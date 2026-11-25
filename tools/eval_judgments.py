"""Dev tool: evaluate the agent's judged items on decks with known judged levels.

Usage:
    python tools/eval_judgments.py prepare [EVAL_DIR] [--runs N] [--seed S] [--only GLOB]
    python tools/eval_judgments.py check   [EVAL_DIR]

EVAL_DIR defaults to .cache/evals/. `prepare` regenerates the decks (tools/make_test_decks.py),
runs the measuring scripts on every deck with "judged" levels in its .expected.json, then copies
the results into EVAL_DIR/run1 .. runN, renamed talk-A, poster-B, ... in a shuffled order so that
neither folder names nor paths reveal which deck is which. The mapping goes to EVAL_DIR/key.json,
outside the run folders. Expected levels are never copied there. Each talk folder also gets
intake.md: the user's answers at intake ("intake" in .expected.json: audience, context rubric,
time limit, print size, what the call allows), standing in for step 1 of SKILL.md. --only limits
the decks (comma-separated globs), e.g. --only "judged-poster-*,judged-low".

Then, for each run folder, have an agent do step 3 ("Judge") of SKILL.md on each talk-X-pptx
(or poster-X-pptx) folder blind: a fresh session or subagent told to read only the skill folder and that run folder,
and to take intake.md as the user's answers. It writes judgments.json in each folder.

`check` scores every run against the expected ranges, and checks that items in "omit" (a needed
intake fact is missing) were left out. Then it summarizes each item across runs (levels seen,
share in range) and writes EVAL_DIR/eval-report.md. Exit code 1 if any judgment is missing, out
of range, or given when it should have been left out.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import random
import re
import shutil
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "slide-poster-review" / "scripts"))
sys.path.insert(0, str(ROOT / "tools"))

DECKS = ROOT / ".cache" / "test-decks"
NAMED = ("manifest.json", "outline.md", "text.json")  # files that mention the source file name


def judged_decks(only: str | None = None) -> dict[str, tuple[Path, dict]]:
    import make_test_decks
    make_test_decks.make_all(DECKS)
    out = {}
    for exp_path in sorted(DECKS.glob("*.expected.json")):
        exp = json.loads(exp_path.read_text(encoding="utf-8"))
        stem = Path(exp["deck"]).stem
        if exp.get("judged") and (only is None or any(fnmatch.fnmatch(stem, g.strip().removesuffix(".pptx"))
                                                      for g in only.split(","))):
            out[Path(exp["deck"]).stem] = (DECKS / exp["deck"], exp)
    return out


def _anonymize(d: Path, stem: str, alias: str) -> None:
    for name in NAMED:
        p = d / name
        if p.exists():
            s = p.read_text(encoding="utf-8")
            s = re.sub(r'"source": "[^"]*"', f'"source": "talks/{alias}.pptx"', s)
            p.write_text(s.replace(stem, alias), encoding="utf-8")


def _intake_md(intake: dict) -> str:
    lines = ["# Intake", "", "The user's answers to the intake questions (step 1 of SKILL.md). They can't be",
             "asked anything more; anything not listed here was not given.", "",
             f"- Audience: {intake.get('audience', 'general')}"]
    if intake.get("what"):
        lines.insert(5, f"- What it is: {intake['what']}")
    if intake.get("rubric"):
        lines.append(f"- Context rubric: `{intake['rubric']}` (in the skill folder)")
    if intake.get("print_size"):
        lines.append(f"- Print size: {intake['print_size']}")
    if intake.get("call"):
        lines.append(f"- What the conference allows: {intake['call']}")
    if intake.get("time_limit_minutes"):
        lines.append(f"- Time limit: {intake['time_limit_minutes']} minutes")
    return "\n".join(lines) + "\n"


def prepare(eval_dir: Path, runs: int, seed: int | None, only: str | None = None) -> list[Path]:
    import accessibility, color, contrast, extract_text, font_size, layout, ocr, readability, render  # noqa: E401
    decks = judged_decks(only)
    measured = {}
    for stem, (src, exp) in decks.items():
        d = render.render(src, eval_dir / "_measured")
        extract_text.extract(d)
        ocr.run(d)
        font_size.measure(d, print_size=exp.get("print_size"))
        contrast.measure(d, print_size=exp.get("print_size"))
        color.measure(d)
        readability.measure(d)
        layout.measure(d)
        accessibility.measure(d)
        measured[stem] = d
    stems = list(decks)
    random.Random(seed).shuffle(stems)
    key = {f"{'poster' if decks[stem][1]['kind'] == 'poster' else 'talk'}-{letter}": stem
           for letter, stem in zip(string.ascii_uppercase, stems)}
    (eval_dir / "key.json").write_text(json.dumps(key, indent=2), encoding="utf-8")
    dirs = []
    for r in range(1, runs + 1):
        run = eval_dir / f"run{r}"
        if run.exists():
            shutil.rmtree(run)
        for alias, stem in key.items():
            d = run / f"{alias}-pptx"
            shutil.copytree(measured[stem], d)
            _anonymize(d, stem, alias)
            (d / "intake.md").write_text(_intake_md(decks[stem][1].get("intake", {})), encoding="utf-8")
            dirs.append(d)
    return dirs


def check(eval_dir: Path) -> int:
    decks = judged_decks()
    key = json.loads((eval_dir / "key.json").read_text(encoding="utf-8"))
    runs = sorted((p for p in eval_dir.glob("run*") if p.is_dir()), key=lambda p: int(p.name[3:]))
    lines, per_run = [], []
    across: dict[tuple[str, str], list] = {}
    total = passed = 0
    for run in runs:
        lines += [f"## {run.name}", "", "| Deck | Item | Judged | Expected | Confidence | Result |",
                  "|---|---|---|---|---|---|"]
        ideas = []
        for alias, stem in key.items():
            _, exp = decks[stem]
            jp = run / f"{alias}-pptx" / "judgments.json"
            j = json.loads(jp.read_text(encoding="utf-8")) if jp.exists() else {}
            got = {it["id"]: it for it in j.get("items", [])}
            for iid, (lo, hi) in sorted(exp["judged"].items()):
                it = got.get(iid, {})
                lvl = it.get("level")
                ok = lvl is not None and lo <= lvl <= hi
                total, passed = total + 1, passed + ok
                across.setdefault((stem, iid), []).append(lvl)
                lines.append(f"| {stem} | {iid} | {lvl if lvl is not None else '(missing)'} | {lo}-{hi} | "
                             f"{it.get('confidence', '')} | {'pass' if ok else 'FAIL'} |")
            for iid in exp.get("omit", []):
                lvl = got.get(iid, {}).get("level")
                ok = iid not in got
                total, passed = total + 1, passed + ok
                across.setdefault((stem, iid), []).append(lvl)
                lines.append(f"| {stem} | {iid} | {'(left out)' if ok else lvl} | left out | "
                             f"{got.get(iid, {}).get('confidence', '')} | {'pass' if ok else 'FAIL'} |")
            if exp.get("key_ideas"):
                stated = [k.lower() for k in j.get("key_ideas", [])]
                hits = sum(any(w.lower() in k for k in stated for w in words) for words in exp["key_ideas"])
                ideas.append(f"{stem}: key ideas matched {hits} of {len(exp['key_ideas'])} "
                             f"({'; '.join(j.get('key_ideas', [])) or 'none stated'})")
        lines += ["", *ideas, ""]
        per_run.append(run.name)
    summary = ["# Judged-item eval", "",
               f"**{passed} of {total} judgments within the expected range** "
               f"({len(runs)} runs, decks anonymized as {', '.join(f'{a} = {s}' for a, s in key.items())}).", "",
               "| Deck | Item | Expected | Levels by run | In range |", "|---|---|---|---|---|"]
    for (stem, iid), lvls in sorted(across.items()):
        if iid in decks[stem][1].get("judged", {}):
            lo, hi = decks[stem][1]["judged"][iid]
            ok, want = sum(v is not None and lo <= v <= hi for v in lvls), f"{lo}-{hi}"
        else:  # "omit": a level means the item was judged without the needed fact
            ok, want = sum(v is None for v in lvls), "left out"
        summary.append(f"| {stem} | {iid} | {want} | {', '.join('-' if v is None else str(v) for v in lvls)} "
                       f"| {ok} of {len(lvls)} |")
    report = "\n".join(summary + [""] + lines) + "\n"
    (eval_dir / "eval-report.md").write_text(report, encoding="utf-8")
    print(report)
    return 0 if passed == total else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("action", choices=["prepare", "check"])
    ap.add_argument("eval_dir", nargs="?", type=Path, default=ROOT / ".cache" / "evals")
    ap.add_argument("--runs", type=int, default=3, help="copies to judge independently (prepare)")
    ap.add_argument("--seed", type=int, default=None, help="fix the deck-to-letter shuffle (prepare)")
    ap.add_argument("--only", default=None, help='deck name globs, comma-separated, e.g. "judged-poster-*,judged-low" (prepare)')
    a = ap.parse_args()
    a.eval_dir.mkdir(parents=True, exist_ok=True)
    if a.action == "prepare":
        for d in prepare(a.eval_dir, a.runs, a.seed, a.only):
            print(d)
        return 0
    return check(a.eval_dir)


if __name__ == "__main__":
    sys.exit(main())
