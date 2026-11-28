"""Dev tool: package the skill as a zip that users download, unzip, and use.

Usage:
    python tools/build_skill_zip.py [OUT_DIR]        # default: dist/

Writes OUT_DIR/slide-poster-review.zip containing one top-level folder, slide-poster-review/,
with SKILL.md inside: unzipped into a skills folder it is ready to use, and the Claude apps take
the zip itself as an uploaded skill. Caches and placeholder files are left out.
.github/workflows/release.yml runs this for every pushed version tag (v*) and attaches the zip
to a GitHub release.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skill" / "slide-poster-review"
SKIP_DIRS = {"__pycache__", ".pytest_cache"}
SKIP_FILES = {".gitkeep", ".DS_Store"}


def build(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "slide-poster-review.zip"
    files = sorted(p for p in SKILL.rglob("*") if p.is_file() and p.name not in SKIP_FILES
                   and p.suffix != ".pyc" and not SKIP_DIRS & set(p.relative_to(SKILL).parts))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, f"{SKILL.name}/{p.relative_to(SKILL).as_posix()}")
    return path


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    print(build(Path(argv[0]) if argv else ROOT / "dist"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
