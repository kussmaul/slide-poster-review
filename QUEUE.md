# slide-poster-review — queue

## 11–20 Design
- 12: Check the angle thresholds (≈7′/12′/20′) against vision and legibility research. So far they're only calibrated against rules of thumb.
- 13: Find or draft example context rubrics for the format and content sections: one from a POGIL-style source, one conference or organization, and one course or lab.

## 21–40 Build
- 21: Write the rendering pipeline: PPTX/PDF → page images, plus text runs with their sizes and colors. Scale by slide height or poster print factor.
- 22: Write contrast and color-vision scripts that sample rendered pixels, including text inside images (OCR for text height). Also OCR text that the PDF stores as outlines: PowerPoint exports rotated chart axis labels as filled paths, so they never appear in `text.json`.
- 23: Write SKILL.md, `rubrics/default.md`, `rubrics/presets.md`, and the reference notes.
- 24: Write the readability script: CEFR word-level profile, problem patterns, and Flesch, Flesch-Kincaid and language adaptations as secondary signals. Verify what `textstat` covers.
- 25: Build test decks and posters with known flaws, and run evals.
- 26: Add the initial extra checks: cognitive load, data graphics, accessibility metadata, consistency.
- 27: Build a solid test set: PPTX and Google Slides sources, plus PDFs exported from each. Cover 4:3 and 16:9 slides, and posters at several print sizes.

## 41–60 Future
- 41: Add connectors for live Google Slides, and maybe OneDrive/SharePoint.
- 42: Support a jargon/glossary term list supplied by the user or lab, and flag undefined terms.
- 43: Produce marked-up output: annotated slide images or comments in the file, still with no rewrites.
- 44: Track WCAG 3 and APCA status, and add APCA as a secondary measure if it stabilizes.
- 45: Add poster-specific checks: reading path, the 10-second takeaway, QR code size.
- 46: Simulate projection conditions: a washed-out projector, a scaled-down Zoom window.
- 47: Compare revisions before and after.
- 48: Check POGIL facilitation slides for slides that reveal answers to activity questions.
- 49: Handle handout PDFs with several slides per page: find the slide frames, split them out, and scale each by its frame height. For now, handouts are detected and rejected.
- 50: Review DOCX and Google Docs documents (handouts, print reading). Needs its own viewing preset.
- 51: Add render backends for other platforms: PowerPoint on macOS, and check whether a slim LibreOffice install is enough.