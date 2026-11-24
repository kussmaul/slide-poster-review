# slide-poster-review — design brief

Agent Skill that reviews slide decks and posters against rubrics and produces a scorecard.
Separate from the POGIL claude-skills project (review / simulate / split).

## Inputs
- .pptx (python-pptx for structure) and PDF; Google Slides via exported .pptx/PDF for now.
- Everything is also rendered to page images (LibreOffice → PDF → PNG) for pixel-based checks.
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
```
slide-poster-review/
  SKILL.md          intake → render → measure → judge → scorecard
  rubrics/          default.md, presets.md
  references/       WCAG, 8H, ADA, CEFR notes + links
  scripts/          render, extract_text, font_size, contrast, cvd_sim, readability
```

## Open / verify
- Check the angle thresholds against vision/legibility literature (calibrated to rules of thumb so far).
- Verify which formulas and languages `textstat` supports.
