# slide-poster-review

An [Agent Skill](https://agentskills.io) that reviews slide decks and posters against rubrics and
produces a scorecard. It measures text size, contrast, color use, and readability, and adds judged
items such as format and content. It reports issues but never rewrites your content.

**Status:** early version. It rates text size, text contrast (including text inside images), use
of color, readability, layout, and accessibility metadata (measured), plus key ideas, meaning that
depends on color, language for the audience, cognitive load, and data graphics (judged by the
agent), and produces a scorecard. Next steps are in [QUEUE.md](QUEUE.md).

## Contents

- [How to start](#how-to-start): install, run a review, what you can give it
- [The scorecard](#the-scorecard)
- [How ratings work](#how-ratings-work): [text size](#text-size), [contrast](#contrast),
  [color](#color), [readability](#readability), [layout](#layout),
  [accessibility metadata](#accessibility-metadata), [content and format](#content-and-format)
- [For developers](#for-developers): [repository layout](#repository-layout),
  [development](#development), [releases](#releases)

## How to start

### Install

1. **Download [slide-poster-review.zip](https://github.com/kussmaul/slide-poster-review/releases/latest/download/slide-poster-review.zip)**
   (the latest release; earlier versions are on the
   [releases page](https://github.com/kussmaul/slide-poster-review/releases)).
2. **Put it where your agent finds skills.** The zip holds one folder, `slide-poster-review`.
   Unzip it into the skills folder in the table, so that you get
   `…/skills/slide-poster-review/SKILL.md`. (Windows' "Extract All" suggests a folder named after
   the zip; remove that last part of the path, or you get `slide-poster-review` twice.)

   | Agent | For all your projects | For one project |
   |---|---|---|
   | Claude Code | `~/.claude/skills/` | `.claude/skills/` in the project |
   | Claude apps (claude.ai, desktop) | Don't unzip: upload the zip as a skill in Settings. Code execution must be on. | |
   | Other agents, e.g. GitHub Copilot in VS Code | `~/.agents/skills/` | `.agents/skills/` in the project |

   `~` is your home folder (`C:\Users\you` on Windows). Many agents look in `.agents/skills/`,
   the shared convention described at [agentskills.io](https://agentskills.io); if yours doesn't,
   its documentation names its skills folder. Agents that support skills are listed in the
   [Client Showcase](https://agentskills.io/clients).
3. **Install the Python packages** once, with the Python the agent uses, e.g. for Claude Code:

   ```
   pip install -r ~/.claude/skills/slide-poster-review/requirements.txt
   ```

   If you skip this, the agent installs them the first time a script needs them.
4. **Start a new session** of your agent, so it finds the new skill.

What the computer running the scripts needs:
- **Python 3.10 or later.**
- **PowerPoint (Windows) or LibreOffice** to review .pptx files. Without either, export a PDF and
  review that.
- **Windows** for reading text inside images (OCR). Elsewhere that step is skipped with a note.

In a cloud sandbox, such as the Claude apps, this may mean PDF input and no OCR.

### Run a review

Ask in plain words and name the file, e.g. "Review the slides in talk.pptx" or "Check my poster,
poster.pdf, for accessibility". In Claude Code you can also type `/slide-poster-review talk.pptx`.

The agent asks only what it doesn't already know: the print size (posters), whether the room is
large (slides), the audience (general, second-language readers, or experts), any rubric from your
organization, conference, course, or lab, and an abstract or learning objectives if you have one.
Then it renders the file, measures it, judges the remaining items, and shows the scorecard. Working
files go to `./slide-review/` in the current folder.

It reports issues; it never rewrites your content.

### What you can give it

- **PowerPoint (.pptx)** gives the most complete review: it includes hidden slides, titles, and alt text.
  Rendering needs PowerPoint (Windows) or LibreOffice.
- **Google Slides:** download it as .pptx (File > Download > Microsoft PowerPoint) or as PDF.
- **PDF**, with one slide or poster per page. Handouts with several slides per page are not supported yet.

Each format shows something different, so the review tells you what your file can't show and which
format would be better. Some examples:
- A PDF from Google Slides includes skipped slides but doesn't mark them.
- A .pptx that uses fonts not installed on the reviewing computer may lay out differently from what
  your audience will see.

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
  descriptions, or adds items, by repeating item IDs. Weight 0 leaves an item or section out.
  Three examples, with Format items, are in
  [rubrics/examples/](skill/slide-poster-review/rubrics/examples/): a POGIL-style class session,
  a conference poster, and a course presentation.

## How ratings work

Every item is rated from **Level 4** (best) to **Level 1**.
- **Measured** items come from the scripts, each with a confidence (high or medium).
- **Judged** items are rated by the agent against the level descriptions in the rubric. Each
  gives its confidence and the slides it is based on.
- Items rated slide by slide give the deck the level that at least 90% of slides reach. One bad
  slide doesn't sink a deck, but the same problem on many slides does.

Each item's levels and sources are in
[rubrics/default.md](skill/slide-poster-review/rubrics/default.md).

### Text size

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

**Colored text** (red, blue, green; not black, white, or grey) is rated as if it were about 30%
smaller, because colored characters need to be larger to be read as easily (MIL-STD-1472F: 21′
instead of 16′). Findings say when the smallest text is colored.

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

### Contrast

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

### Color

About 8% of men and 0.5% of women have some color-vision deficiency, mostly red-green. WCAG 1.4.1
asks that color never be the *only* way to convey information. Two items are measured and one is
judged:

- **Colors distinguishable with color-vision deficiency** (measured). On each slide, the main
  saturated colors (each covering at least 0.4% of the page) are compared in pairs. A pair that is
  clearly different with normal vision but nearly the same in a simulation of color blindness is
  flagged. Photos are left out: a red shirt on green grass rarely carries meaning. In a .pptx,
  the series colors of each chart are also read from the file and compared, so thin chart lines
  and small legend keys count too.

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

### Readability

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

### Layout

- **Text doesn't collide.** Text that overlaps other text (e.g. a line running into the footer) or
  is cut off at the edge of the slide. Text deliberately hidden under an opaque shape isn't a visible
  collision. It is listed separately, because a screen reader still reads it.
- **Titles stand out.** Each slide's title compared with its largest body text: Level 4 is 1.2
  times larger or more, Level 3 is 1.1 times, Level 2 about the same, Level 1 smaller.
- **Few fonts.** Font families in body text (each with at least 2% of the characters): one or two
  is Level 4, three is Level 3, four is Level 2, more is Level 1.
- **Titles in a consistent place.** Titles whose position or size differs from other slides with
  the same layout, e.g. a title shrunk to fit.

Two items are judged by the agent, using counts from the layout check as pointers:
**cognitive load** (one point per slide, text the audience can glance at rather than read) and
**data graphics** (labeled axes, direct labels, no 3-D or other distortion).

### Accessibility metadata

These matter when the file itself is shared, e.g. posted for students who use a screen reader.
They follow WCAG and PowerPoint's Accessibility Checker, and need the .pptx:

- **Alt text** on pictures, charts, and diagrams, unless they are marked decorative. Alt text that
  is just a file name counts as missing; alt text Office generated automatically counts as present
  but unchecked.
- **Slide titles** in the title placeholder, because screen-reader users navigate by them. A title
  typed into a text box doesn't count.
- **Reading order:** the title is read first.

Sources are in [references/standards.md](skill/slide-poster-review/references/standards.md).

### Content and format

Judged by the agent from the slide text and page images:
- **Key ideas are identifiable.** Could a viewer state the 2-5 key ideas from the slides alone? Titles
  that state messages, emphasis, and a summary help; titles that only name topics don't. An abstract
  or learning objectives, if given, tell the agent what the key ideas should be.
- **Format items** come from a context rubric, e.g. required slides or parts, citations, and length
  for the time limit. See [The scorecard](#the-scorecard) for how a context rubric is applied.

## For developers

### Repository layout

```
skill/slide-poster-review/   the skill itself (this folder is what gets installed)
  SKILL.md                   instructions for the agent
  scripts/                   render.py, extract_text.py, font_size.py, ...
  rubrics/                   rubric items and viewing presets
  references/                evidence and standards notes
tests/                       pytest suite; also uses real decks in test-inputs/ (not in git)
  decks/                     generated decks with known levels (tools/make_test_decks.py)
tools/                       dev tools, e.g. build_skill_zip.py, eval_judgments.py (not shipped)
.github/workflows/           release.yml: builds the skill zip for each version tag
evals/                       reports from blind evals of the judged items
DESIGN.md                    design brief
QUEUE.md                     task queue
```

### Development

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
flaw should get, which the tests check. The decks are committed in `tests/decks/`; a test fails
if they differ from what the generator makes, so rerun it after changing the generator:

```
.venv/Scripts/python tools/make_test_decks.py     # -> tests/decks/{flaws,judged}-*.pptx and .expected.json
```

`review_test_inputs.py` includes `tests/decks/`. Open a scorecard in VS Code's
Markdown preview (Ctrl+Shift+V) to see the tables.

To run the pipeline by hand:

```
python skill/slide-poster-review/scripts/render.py        deck.pptx --out output
python skill/slide-poster-review/scripts/extract_text.py  output/deck-pptx
python skill/slide-poster-review/scripts/font_size.py     output/deck-pptx
python skill/slide-poster-review/scripts/contrast.py      output/deck-pptx
python skill/slide-poster-review/scripts/color.py         output/deck-pptx
python skill/slide-poster-review/scripts/readability.py   output/deck-pptx --audience general
python skill/slide-poster-review/scripts/layout.py        output/deck-pptx
python skill/slide-poster-review/scripts/accessibility.py output/deck-pptx
# the agent writes output/deck-pptx/judgments.json (see SKILL.md), then:
python skill/slide-poster-review/scripts/scorecard.py     output/deck-pptx
```

`render.py` reuses an earlier render when the input file, settings, and installed fonts are unchanged.
Use `--force` to render again.

To try changes to the skill without a release, link the skill folder of your clone into a skills
folder (Windows: `mklink /J %USERPROFILE%\.claude\skills\slide-poster-review skill\slide-poster-review`
in cmd; elsewhere `ln -s "$PWD/skill/slide-poster-review" ~/.claude/skills/`).

### Releases

The download link in [Install](#install) points to the zip attached to the latest GitHub release.
To publish one, push a version tag; `.github/workflows/release.yml` builds the zip with
`tools/build_skill_zip.py` and creates the release:

```
git tag v0.1.0
git push origin v0.1.0
.venv/Scripts/python tools/build_skill_zip.py     # to build dist/slide-poster-review.zip locally
```
