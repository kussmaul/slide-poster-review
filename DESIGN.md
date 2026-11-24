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
  Default preset = back row at 12H / poster at 2 m; level boundaries 18 / 30 / 50 pt (≈ 7′ / 12′ / 20′).
  Same distance for all text roles. Scale by real slide height or poster print factor.
  Includes text inside images (OCR text height); "check manually" only when measurement fails,
  and counted as evidence of a potential problem.
- **Contrast:** WCAG 2.x (1.4.3 text, 1.4.11 non-text), sampled from rendered pixels; ratios never rounded.
- **Color:** WCAG 1.4.1 (color not the only cue); color-vision simulation (DaltonLens) as supporting evidence.
- **Readability:** CEFR vocabulary profile (free list such as CEFR-J or Oxford 3000/5000) and patterns
  (idioms, phrasal verbs, undefined acronyms, noun stacks, words per bullet), plus judgment.
  Flesch / Flesch-Kincaid and language adaptations are secondary signals only.
- **Extras:** cognitive load, data graphics, accessibility metadata, consistency.

## Judgments (initial)
- Format: required/forbidden headings per context rubric.
- Content: sections to expand vs. shorten/omit, relative to inferred key ideas.

## Output
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
