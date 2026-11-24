---
name: slide-poster-review
description: Reviews slide decks and posters (PPTX, Google Slides exports, PDF) against accessibility and presentation rubrics and produces a scorecard with a ranked issue list. Measures font size by viewing distance, color contrast (WCAG), color-only cues, and readability for the audience. Use when the user asks to review, check, critique, or score slides, a presentation, a deck, or a poster.
compatibility: Requires Python 3.10+ with pymupdf, python-pptx, and fonttools (requirements.txt). Rendering .pptx needs PowerPoint (Windows) or LibreOffice; without either, accepts PDF exports only.
metadata:
  status: "draft - pipeline only; see task 23 in QUEUE.md"
---

# Slide & poster review

Work in progress. Only the rendering pipeline exists so far.

1. Render: `python scripts/render.py INPUT --out OUTPUT_ROOT`. Show the user every notice
   printed to stderr (also in `manifest.json` → `notices`).
2. Extract text: `python scripts/extract_text.py OUTPUT_DIR` → `text.json`.
3. Font size: `python scripts/font_size.py OUTPUT_DIR [--print-size 48x36in]` → `font_size.json`.
   Viewing presets are in [rubrics/presets.md](rubrics/presets.md); evidence for them is in
   [references/legibility-thresholds.md](references/legibility-thresholds.md).
