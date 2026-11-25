---
name: slide-poster-review
description: Reviews slide decks and posters (PPTX, Google Slides exports, PDF) against accessibility and presentation rubrics and produces a scorecard with a ranked issue list. Measures text size by viewing distance and text contrast (WCAG), including text inside images (OCR), and colors that look alike with color blindness or carry meaning alone; rates readability for the audience (CEFR vocabulary level, sentence length, acronyms), layout (colliding text, title hierarchy, fonts, consistency), accessibility metadata (alt text, slide titles, reading order), cognitive load, data graphics, and whether key ideas are identifiable. Use when the user asks to review, check, critique, or score slides, a presentation, a deck, or a poster.
compatibility: Requires Python 3.10+ with pymupdf, python-pptx, fonttools, numpy, and daltonlens (requirements.txt); readability uses the bundled CEFR word lists, no extra packages. Rendering .pptx needs PowerPoint (Windows) or LibreOffice; without either, accepts PDF exports only. OCR uses Windows' built-in engine; elsewhere it is skipped with a notice.
metadata:
  status: "early version: text size, contrast, color, readability, layout, accessibility, content"
---

# Slide & poster review

Produce a scorecard for a slide deck or poster: section scores, then a ranked list of issues.
**Report issues only. Never rewrite content or suggest specific replacement wording.** Users
tend to accept suggested edits without thinking, and the author knows their content best.

Paths below are relative to this skill's folder. Write all output to a working folder outside
the skill, e.g. `./slide-review/` in the user's current directory (called `OUT` below).
If a script fails because a module is missing, run `pip install -r requirements.txt` once.

## 1. Intake

Ask only for what you don't already know, in one short message:
- **The file.** PPTX gives the most complete review. Google Slides can be downloaded as .pptx or PDF.
  PDFs need one slide or poster per page.
- **Posters: the print size**, e.g. 48x36in or 120x90cm. Without it, the file's page size is assumed.
- **Slides: the room**, only if it's large (big room, small screen). Then use `--preset slides-large-room`.
- **The audience:** a general audience, readers of English as a second language (`--audience l2`),
  or experts in the field (`--audience experts`). This sets the vocabulary level only; text size,
  contrast, and the other measures are the same for every audience. Also ask for the language if
  the text isn't English (`--lang de`).
- **A context rubric** from an organization, conference, course, or lab, if they have one.
- **An abstract or learning objectives**, if available; they help judge key ideas.

## 2. Render and measure

Run these in order. Each prints the next folder or a summary.

```
python scripts/render.py INPUT --out OUT            # prints OUTPUT_DIR; notices go to stderr
python scripts/extract_text.py OUTPUT_DIR           # text.json, outline.md
python scripts/ocr.py OUTPUT_DIR                    # text in images/shapes (Windows; skipped elsewhere)
python scripts/font_size.py OUTPUT_DIR [--print-size 48x36in] [--preset NAME]
python scripts/contrast.py OUTPUT_DIR  [--print-size 48x36in] [--preset NAME]   # same options
python scripts/color.py OUTPUT_DIR                  # color blindness, color-only emphasis
python scripts/readability.py OUTPUT_DIR [--audience general|l2|experts] [--lang en]
python scripts/layout.py OUTPUT_DIR                 # colliding text, title hierarchy, fonts, consistency
python scripts/accessibility.py OUTPUT_DIR          # alt text, slide titles, reading order (.pptx only)
```

- If `render.py` fails (exit code 2 or 3), tell the user its message. It explains what to do,
  e.g. export a PDF, or export one slide per page instead of a handout.
- Pass every notice from `render.py` on to the user. These say what this file format can't show,
  e.g. a Google Slides PDF that includes skipped slides. The scorecard repeats them.
- Viewing presets are in [rubrics/presets.md](rubrics/presets.md). The evidence behind them is in
  [references/legibility-thresholds.md](references/legibility-thresholds.md). Standards behind the
  other items (WCAG, ADA, Office's accessibility checker, design and learning research) are in
  [references/standards.md](references/standards.md).
- `accessibility.py` needs the .pptx. For a PDF it reports that alt text, slide titles, and
  reading order weren't checked; pass that on if the file will be shared with students.

## 3. Judge

Judged items are in the "Judged items" section of [rubrics/default.md](rubrics/default.md) and of
any context rubric. For each one:

1. Read `OUTPUT_DIR/outline.md`, the text of every slide with hidden slides marked. Look at a few
   page images in `OUTPUT_DIR/pages/` where layout or emphasis matters: the title slide, any
   summary or conclusion slides, and slides whose role is unclear from the text.
2. **Key ideas (for CN-1).** Infer the 2–5 key ideas from the abstract or objectives if given,
   otherwise from the content. If you can't identify them confidently, say so: that is itself a
   finding.
3. Choose the level whose description in the rubric fits best. Use `high` confidence only when
   the evidence is clear on several slides. Ignore hidden slides.
4. Write the result as `OUTPUT_DIR/judgments.json`:

```json
{"key_ideas": ["...", "..."],
 "items": [{"id": "CN-1", "level": 3, "confidence": "medium",
            "headline": "One sentence describing the issue, not a fix.",
            "details": "Optional second sentence with specifics.",
            "pages": [4, 9, 12]},
           {"id": "CO-3", "level": 2, "confidence": "medium", "headline": "...", "pages": [7]}]}
```

**Color (for CO-3).** Look at the pages listed in `color.json` findings (CO-1, CO-2) and at
their simulated views in `OUTPUT_DIR/color/` (e.g. `p003-deutan.png`, how the page looks with
red-green color blindness). Also look at slides with charts, legends, or colored tables or
highlights. Ask: is anything lost if color can't be seen? A legend whose entries are also
labeled, or a highlight that is also bold, loses nothing. CO-1 flags colors that look alike;
only judgment can say whether they carry meaning. Photos are not checked.

**Language (for RD-4).** Read `outline.md` with the audience in mind, using the `hints` in
`readability.json`: `above_target` (words above the audience's CEFR level; "off-list" means in
neither list, often technical terms), `acronyms`, `phrasal_verbs` (candidates; many are fine),
`long_sentences`, and `names_skipped` (capitalized words treated as names; check for real words
among them). Look for idioms, culture-specific references, stacked nouns ("student learning
outcome assessment data"), and terms used before they are explained. Technical terms are fine
for experts, or when defined. For second-language readers, idioms and phrasal verbs matter most.
`signals` (Flesch, Flesch-Kincaid) are background only: slide fragments make them read as easy.

**Cognitive load (for CL-1).** Use `hints` in `layout.json`: `slides_over_40_words`,
`slides_over_6_lines`, `median_body_words`, and per-slide `units[].hints` (words, lines, bullets,
images). These point to slides to look at; they aren't limits. Look at their page images. Ask:
does each slide make one point? Would the audience read instead of listen? Is there decoration
that competes with the content? A dense slide meant as a handout or reference is less of a problem
than a dense slide shown while speaking.

**Data graphics (for DG-1).** Look at slides with charts or tables: `layout.json` → `hints.charts`
(chart type, 3-D, title, legend, axis titles, data labels, `value_axis_min`: a set minimum
above 0 on a bar or column chart truncates the bars; .pptx only) and pictures of charts in
the page images. Ask: is the message clear, are axes and units labeled, could labels replace the
legend, does anything distort the data (3-D, truncated axes)? If the deck has no data graphics,
leave DG-1 out of `judgments.json`.

Describe what is wrong, not how to fix it: "The conclusion slide lists topics rather than
findings", not "Change the conclusion to say…".

## 4. Scorecard

```
python scripts/scorecard.py OUTPUT_DIR [--rubric CONTEXT.md]
```

Show the user the contents of `OUTPUT_DIR/scorecard.md`. Then briefly offer details on any issue,
e.g. which slides are affected (`font_size.json` → `findings[].units`). Don't add rewrites.

## Rules

- One input file, one review. Never merge results from different formats of the same deck.
  Use the notices to say what another format would add.
- Every finding carries a confidence level. Measured items get theirs from the scripts.
- A measurement that couldn't be made, e.g. text inside images, is noted for checking by eye,
  not silently skipped.
