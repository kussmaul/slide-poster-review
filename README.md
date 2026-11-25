# slide-poster-review

An [Agent Skill](https://agentskills.io) that reviews slide decks and posters against rubrics and
produces a scorecard. It measures text size, contrast, color use, and readability, and adds judged
items such as format and content. It reports issues but never rewrites your content.

**Status:** early version. It rates text size, text contrast (including text inside images), use
of color, and readability (measured), plus whether key ideas are identifiable, whether meaning
depends on color alone, and whether the language suits the audience (judged by the agent), and
produces a scorecard. Next steps are in [QUEUE.md](QUEUE.md).

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

**Text in images and shapes** (screenshots, infographics, chart images, rotated chart labels) is
found with OCR. Windows' built-in OCR is used; on other systems it is skipped with a note.
- It is measured like other body text and labeled "text in images or shapes".
- Its size is estimated from the OCR word boxes. On test slides the estimate was within about ±10%
  of the true size. Findings that depend on it are marked medium confidence.
- Its contrast is compared against the typical background in each word's box. The colors are
  estimates, so issues give an approximate ratio without naming colors.
- Rotated text (e.g. 45° axis labels) is read by rotating those areas and trying OCR again.
  Areas that look like text but still can't be read are listed for checking by eye.
- Text too small to see at all (under 1′), which is usually hidden metadata, e.g. from embedded
  videos, is listed but not scored.

## How contrast is rated

Contrast is the WCAG 2.x ratio between the text color and the background actually behind it,
sampled from the rendered page. It ranges from 1:1 (invisible) to 21:1 (black on white).

| Level | Normal text | Large text |
|---|---|---|
| Level 4 | 7:1 or more (WCAG AAA) | 4.5:1 or more |
| Level 3 | 4.5:1 or more (WCAG AA) | 3:1 or more |
| Level 2 | 3:1 or more | — |
| Level 1 | below 3:1 | below 3:1 |

- **"Large" text.** WCAG defines it as 18 pt, or 14 pt bold, for a page read at arm's length.
  Here that is converted to the same visual angle at the viewing distance: a cap height of 21.5′,
  or 16.7′ for bold. At 8H that is about 39 pt, so mostly titles.
- **Ratios aren't rounded.** 4.49:1 fails 4.5:1. They are shown truncated, e.g. 4.49:1.
- **Text over a photo, gradient, or other text** is rated by a near-worst case: the 10th percentile
  of contrast across its background. It is marked medium confidence. Text that overflows into a
  footer shows up this way too.
- **Scoring.** As for text size, each slide is rated by its worst text, and the deck gets the level
  that 90% of slides reach. Body and supporting text are separate items.

## How color is rated

About 8% of men and 0.5% of women have some color-vision deficiency, mostly red-green. WCAG 1.4.1
asks that color never be the *only* way to convey information. Two items are measured and one is
judged:

- **Colors distinguishable with color-vision deficiency** (measured). On each slide, the main
  saturated colors (each covering at least 0.4% of the page) are compared in pairs. A pair that is
  clearly different with normal vision but nearly the same in a simulation of color blindness is
  flagged. Photos are left out: a red shirt on green grass rarely carries meaning.

  | Level | Colors that look alike… |
  |---|---|
  | Level 4 | none |
  | Level 3 | only with blue-yellow color blindness (tritanopia, about 1 in 10,000) |
  | Level 2 | with red-green color blindness (protanopia, deuteranopia: about 2% of men) |
  | Level 1 | even with moderate red-green deficiency (most of the other 6% of affected men) |

  This finds where color *could* be the only cue, so it is medium confidence. For each flagged
  slide, a simulated view is saved (e.g. `color/p003-deutan.png`).
- **Emphasis not by color alone** (measured). Words whose color differs from the rest of their text
  block, with no other cue: same weight, style, and size, not underlined. Links count too. Black vs.
  grey is a lightness difference, not a color cue, and isn't counted. Level 3 if the words still
  differ in lightness by 3:1 or more (WCAG technique G183), Level 2 if less, Level 1 if they look
  the same as the surrounding text with color blindness.
- **Meaning doesn't depend on color alone** (judged). The agent looks at the flagged slides, their
  simulated views, and any charts or legends, and rates whether anything is lost without color,
  e.g. chart series told apart only by a color key.

Simulation uses [DaltonLens](https://github.com/DaltonLens/DaltonLens-Python) (MIT): Viénot 1999 for
protanopia and deuteranopia, Brettel 1997 for tritanopia, and Machado 2009 at severity 0.6 for
moderate deficiency. Color differences are CIELAB ΔE: "clearly different" is more than 25, "nearly
the same" less than 10.

## How readability is rated

Readability depends on the audience, so intake asks who it is: a **general** audience, readers of
English as a **second language**, or **experts** in the field. This is the only place the audience
changes a rating. Three items are measured and one is judged:

- **Vocabulary level** (measured). Each word is looked up in two free CEFR word lists: the
  CEFR-J Wordlist (A1–B2) and the Octanove C1/C2 profile. Inflections are removed first
  (*studies* → *study*). Names, numbers, and acronyms are left out. The item is the share of words
  at or below the audience's level: B2 for a general audience, B1 for second-language readers,
  C2 for experts.

  | Level | Words at or below the audience's level |
  |---|---|
  | Level 4 | 98% or more: most readers understand without help |
  | Level 3 | 95% or more: readers get the gist, with some support |
  | Level 2 | 90% or more |
  | Level 1 | under 90% |

  The bounds come from research on how many words a reader must know to understand a text
  (Laufer; Hu & Nation; Schmitt et al.). The lists hold about 10,000 words, so some common
  academic words (*framework*, *variable*) count as rare, and so do technical terms. Findings
  name the words, so you can see which are terms your audience knows.
- **Sentence length** (measured). Each slide is rated by its longest sentence; a bullet without
  end punctuation counts as one sentence. Level 4 is 15 words or fewer, Level 3 is 20, Level 2
  is 30. The deck gets the level that 90% of slides reach.
- **Acronyms spelled out** (measured). Acronyms that are never spelled out anywhere in the deck,
  e.g. as "Think-Pair-Share (TPS)". Level 4 is none, Level 3 one or two, Level 2 three to five.
- **Language suits the audience** (judged). The agent reads the text for idioms, phrasal verbs,
  jargon, stacked nouns, and culture-specific references, using hints from the measured items.

Flesch Reading Ease and Flesch-Kincaid grade are reported, but not scored: they are built for
prose, and slide fragments make text look easier than it is. Text found by OCR is left out of
readability, because misread words would count as rare. Sources are in
[references/readability.md](skill/slide-poster-review/references/readability.md).

## The scorecard

- The scorecard has a summary row for each **section** (e.g. "Text size: 1.8 of 4"), the weighted
  average of its items. Below it, each **item** is listed by name with its level (e.g. "Body text
  size: Level 2").
- The **overall** score is the weighted average of the sections. Measured accessibility sections
  (text size, contrast) weigh more.
- Items that haven't been assessed are listed, not counted.
- **Issues** are ranked by how much they cost: section weight × the item's share of its section ×
  how far it is below Level 4. Each issue gives the item name, level, and confidence, then a second
  line of details.
- The rubric is [rubrics/default.md](skill/slide-poster-review/rubrics/default.md). An organization,
  conference, course, or lab can supply a context rubric that changes weights or level
  descriptions, or adds items, by repeating item IDs.

## Repository layout

```
skill/slide-poster-review/   the skill itself (this folder is what gets installed)
  SKILL.md                   instructions for the agent
  scripts/                   render.py, extract_text.py, font_size.py, ...
  rubrics/                   rubric items and viewing presets
  references/                evidence and standards notes
tests/                       pytest suite (uses local files in test-inputs/, not in git)
tools/                       dev tools, e.g. review_test_inputs.py (not shipped)
DESIGN.md                    design brief
QUEUE.md                     task queue
```

## Development

```
py -3.14 -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest -q tests   # renders are cached in .cache/; a repeat run takes seconds
.venv/Scripts/agentskills validate skill/slide-poster-review
```

To review everything in `test-inputs/` and read the results as rendered Markdown:

```
.venv/Scripts/python tools/review_test_inputs.py   # scorecards -> test-outputs/*.md, index.md
```

Intermediate files (PDF, page images, JSON) go to `.cache/work/`.

Decks with known flaws come from a generator; each has an `.expected.json` with the level every
flaw should get, which the tests check:

```
.venv/Scripts/python tools/make_test_decks.py     # -> test-inputs/generated/flaws-{slides,poster,color,text}.pptx
```

`review_test_inputs.py` includes `test-inputs/generated/` if it exists. Open a scorecard in VS Code's
Markdown preview (Ctrl+Shift+V) to see the tables.

To run the pipeline by hand:

```
python skill/slide-poster-review/scripts/render.py deck.pptx --out output
python skill/slide-poster-review/scripts/extract_text.py output/deck-pptx
python skill/slide-poster-review/scripts/font_size.py output/deck-pptx
python skill/slide-poster-review/scripts/contrast.py output/deck-pptx
python skill/slide-poster-review/scripts/color.py output/deck-pptx
python skill/slide-poster-review/scripts/readability.py output/deck-pptx --audience general
# the agent writes output/deck-pptx/judgments.json (see SKILL.md), then:
python skill/slide-poster-review/scripts/scorecard.py output/deck-pptx
```

`render.py` reuses an earlier render when the input file, settings, and installed fonts are unchanged.
Use `--force` to render again.
