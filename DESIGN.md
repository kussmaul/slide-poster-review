# slide-poster-review — design brief

Agent Skill that reviews slide decks and posters against rubrics and produces a scorecard.
Separate from the POGIL claude-skills project (review / simulate / split).

## Inputs
- .pptx (python-pptx for structure) and PDF; Google Slides via exported .pptx/PDF for now.
- Everything is also rendered to page images (→ PDF → PNG via PyMuPDF) for pixel-based checks.
  PPTX → PDF backends, in order: PowerPoint (Windows COM), LibreOffice if already installed,
  else ask the user to export a PDF. Full LibreOffice is not a required dependency.
- Text runs (text, size, font, color, position) are read from the rendered PDF, so autofit and
  master/placeholder inheritance are already applied. python-pptx adds what the PDF loses:
  hidden slides, titles, alt text, requested fonts (to detect substitution).
- Font substitution matters: a missing font (e.g. Gill Sans) changes line breaks and can push
  text off the slide. Flag it as "substituted" when the font is requested, not installed, and absent
  from the PDF, and warn that results may not match what the audience sees.
- PDFs exported by the authoring app (e.g. Google Slides) keep the true fonts and layout, but they
  include hidden/skipped slides without marking them, and they carry no alt text.
- Users normally provide one format, and results from different formats are never merged.
  Instead, the pipeline detects which app made the file (PDF creator; `docProps/app.xml`, which is
  missing in Google Slides PPTX exports) and reports notices `{code, level, message, advice}`:
  what this format can't show, and which format or export method to use instead.
- Inputs are one slide or poster per page; handout PDFs (several slides per page) are rejected for now.
  DOCX / Google Docs are out of scope for now.
- Intake asks for: viewing preset, audience (students vs. experts; L1 vs. L2 English), print size (posters).
- Key ideas / learning objectives: inferred from content or an abstract; flag when unclear.

## Rubrics
- Markdown files. Built-in defaults plus context rubrics (org, conference, course, lab) that override items by ID.
- Each item: ID, measured vs. judged, weight, source (e.g. WCAG 1.4.3), 4 level descriptors, link to more info.
- Measured and judged items live in separate rubric sections. Every finding gets a confidence level.
- Default weights per section, with measured accessibility items weighted higher; context rubrics can override.

## Measures (initial)
- **Font size:** visual angle of cap height (0.7 em unless font metrics are available).
  Level boundaries 10 / 16 / 22′ (display standards and reading research; see references/legibility-thresholds.md).
  Default presets: slides back row at 8H (≈ 18 / 29 / 40 pt), posters at 1.5 m; optional 12H and 2 m presets.
  Each slide is rated by its smallest body text; an item's level is the level that 90% of slides reach.
  Same distance for all text roles.
  Thresholds are universal (universal design): they never vary by audience; intake audience affects
  readability only. Scale by real slide height or poster print factor.
  Includes text inside images (OCR text height); "check manually" only when measurement fails,
  and counted as evidence of a potential problem.
  OCR: Windows OCR (RapidOCR later). Pass 1 = whole page minus PDF text; pass 2 = glyph-like shape
  clusters retried at ±45°/±90°. Cap height from word boxes (letter shapes; median per line, ≈ ±10%).
  Posters group OCR text by picture. Contrast for OCR text uses the median background (boxes include
  nearby graphics); colors not reported.
- **Contrast:** WCAG 2.x (1.4.3 text, 1.4.11 non-text), sampled from rendered pixels; ratios never rounded.
  Text: CT-1 body / CT-2 supporting; levels 7 / 4.5 / 3:1 (large: 4.5 / 3:1). "Large" = WCAG 18 pt (14 pt bold)
  as a visual angle: cap 21.5′ (16.7′ bold). Background excludes glyphs + 2 px; over images/gradients
  the 10th-percentile contrast is used (medium confidence).
- **Color:** WCAG 1.4.1 (color not the only cue); color-vision simulation (DaltonLens) as supporting evidence.
  CO-1 (measured, medium confidence): page palette of saturated colors (≥0.4% of page; photos excluded:
  <80% of pixels in their top 8 colors); pairs with ΔE76 > 25 normally but < 10 simulated. Viénot 1999
  protan/deutan, Brettel 1997 tritan, Machado 2009 severity 0.6. Levels: tritan only 3, red-green 2,
  moderate red-green 1. CO-2 (measured): spans differing from their block's main color (ΔE > 20) with
  same weight/style/size, no drawn underline; neutral-vs-neutral ignored; 3:1 lightness → 3, else 2,
  alike in simulation → 1. CO-3 (judged): is meaning lost without color; agent uses simulated views.
  Limitation: JPEG infographics count as photos.
- **Readability:** CEFR vocabulary profile (free list such as CEFR-J or Oxford 3000/5000) and patterns
  (idioms, phrasal verbs, undefined acronyms, noun stacks, words per bullet), plus judgment.
  Flesch / Flesch-Kincaid and language adaptations are secondary signals only.
- **Extras:** cognitive load, data graphics, accessibility metadata, consistency.

## Judgments (initial)
- Format: required/forbidden headings per context rubric.
- Content: sections to expand vs. shorten/omit, relative to inferred key ideas.

## Output
- Section score = weighted average of its items' levels (shown as "1.8 of 4"); items show "Level 1–4" by name.
  Overall = weighted average of assessed sections; unassessed items are listed, not counted.
  Issues ranked by section weight × item share × (4 − level), then by slides affected.
- Judged items: the agent writes `judgments.json` (level, confidence, headline, details, pages); it can't
  override measured items.
- Summary scorecard: section scores (4 levels, weighted), overall score, then a ranked issue list.
- Issues: ≤1 line, confidence, sample slides/sections ("FS-1: 14 slides below L3, e.g. 4, 9, 12").
- No rewrites or specific suggested edits (users may accept them blindly).

## Structure
The skill follows the Agent Skills format (agentskills.io) and lives in its own subfolder, so dev
files don't ship with it. `tests/test_pipeline.py` runs `skills-ref` to validate it.
```
skill/slide-poster-review/     ← the shipped skill (folder name = `name` in SKILL.md)
  SKILL.md          intake → render → measure → judge → scorecard
  requirements.txt  runtime Python deps
  rubrics/          default.md, presets.md
  references/       WCAG, 8H, ADA, CEFR notes + links
  scripts/          render, extract_text, font_size, contrast, cvd_sim, readability
tests/  test-inputs/ (local, gitignored)  DESIGN.md  QUEUE.md  requirements-dev.txt
```

## Open / verify
- Check the angle thresholds against vision/legibility literature (calibrated to rules of thumb so far).
- Verify which formulas and languages `textstat` supports.
