# slide-poster-review

An [Agent Skill](https://agentskills.io) that reviews slide decks and posters against rubrics and
produces a scorecard. It measures text size, contrast, color use, and readability, and adds judged
items such as format and content. It reports issues but never rewrites your content.

**Status:** work in progress. The rendering pipeline and the text-size measure work. Contrast,
color, readability, the rubrics, and the scorecard are still to come (see [QUEUE.md](QUEUE.md)).

## What you can give it

- **PowerPoint (.pptx)** gives the most complete review: it includes hidden slides, titles, and alt text.
  Rendering needs PowerPoint (Windows) or LibreOffice.
- **Google Slides:** download it as .pptx (File > Download > Microsoft PowerPoint) or as PDF.
- **PDF**, with one slide or poster per page. Handouts with several slides per page are not supported yet.

Each format shows something different, so the review tells you what your file can't show and which
format would be better. Some examples:
- A PDF from Google Slides includes skipped slides but doesn't mark them.
- A .pptx that uses fonts not installed on the reviewing computer may lay out differently from what
  your audience will see.

## How text size is rated

What matters is how big text *looks* from where people sit or stand, not its point size. So the
review measures the **visual angle** of each letter's cap height (the height of a capital letter),
in arcminutes (′; 60′ = 1°).

**Viewing distance.**
- **Slides** are measured relative to the projected image. "8H" means a viewer 8 times the image
  height away. With a 2 m tall image, that is 16 m. 8H is the usual planning distance for the back
  row (AVIXA). "12H" is a large room with an undersized screen.
- **Posters** are measured at the printed size from the reader's eyes. The default is 1.5 m for
  reading; headlines are checked at 2 m. Give the actual print size (e.g. `--print-size 36x48in`)
  if it differs from the file's page size.

**Levels.** These come from display standards and reading research (ISO 9241-303, ANSI/HFES 100,
MIL-STD-1472, Legge). See
[references/legibility-thresholds.md](skill/slide-poster-review/references/legibility-thresholds.md).

| Level | Cap-height angle | Meaning | Slide at 8H, about | Poster at 1.5 m, about |
|---|---|---|---|---|
| L1 | under 10′ | Below the absolute floor; hard to read | under 18 pt | under 18 pt |
| L2 | 10–16′ | Readable with effort; fine for footnotes | 18 pt | 18 pt |
| L3 | 16–22′ | Comfortable reading | 29 pt | 28 pt |
| L4 | 22′ and up | Preferred | 40 pt | 39 pt |

The point sizes assume a typical sans-serif font on a 7.5-inch-high slide. Fonts differ: Calibri's
capitals are about 10% shorter than Arial's at the same point size. The review uses each font's real
cap height when it can read it from the file.

The same thresholds apply to every audience. This follows universal design: text that works for
viewers with weaker eyesight works for everyone.

**Scoring.**
- Each slide is rated by its **smallest** body text, because that is what someone still has to read.
- The deck's score for an item is the level that **at least 90% of slides** reach. One bad slide
  doesn't sink it, but small text on many slides does.
- Hidden slides are measured but not scored.
- For posters, each text block is rated in the same way.

**Body vs. supporting text.**
- **Supporting text** is rated separately, so it doesn't drag down the body score. This means
  footers and slide numbers, citations and URLs, and superscripts.
- **Body text** is everything else.

**Findings** say what kind of text is small and where, for example:

> FS-1: 26 slides have body text (bullets 11, labels 6, sub-bullets 4, chart/table text 3, …) below L3, e.g. 20, 21, 96; smallest 12 pt Georgia (8.8′)

**What isn't measured yet:**
- Text inside images.
- Text that the file draws as shapes, such as rotated chart labels. That needs OCR, which is planned.
- Text too small to see at all (under 1′), which is usually hidden metadata, e.g. from embedded
  videos. It is listed but not scored.

## Repository layout

```
skill/slide-poster-review/   the skill itself (this folder is what gets installed)
  SKILL.md                   instructions for the agent
  scripts/                   render.py, extract_text.py, font_size.py, ...
  rubrics/                   rubric items and viewing presets
  references/                evidence and standards notes
tests/                       pytest suite (uses local files in test-inputs/, not in git)
DESIGN.md                    design brief
QUEUE.md                     task queue
```

## Development

```
py -3.14 -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest -q tests
.venv/Scripts/agentskills validate skill/slide-poster-review
```

To run the pipeline by hand:

```
python skill/slide-poster-review/scripts/render.py deck.pptx --out output
python skill/slide-poster-review/scripts/extract_text.py output/deck-pptx
python skill/slide-poster-review/scripts/font_size.py output/deck-pptx
```
