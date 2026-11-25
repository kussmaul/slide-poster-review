# slide-poster-review — queue

## 11–20 Design
- 12: Check the angle thresholds against vision and legibility research. Done: adopted 10/16/22′ at 8H for slides and 1.5 m for posters (evidence in `references/legibility-thresholds.md`). Revisit after validation (29).
- 13: Find or draft example context rubrics for the format and content sections: one from a POGIL-style source, one conference or organization, and one course or lab.

## 21–40 Build
- 21: Write the rendering pipeline: PPTX/PDF → page images, plus text runs with their sizes and colors. Scale by slide height or poster print factor.
- 22: Write contrast and color-vision scripts that sample rendered pixels, including text inside images (OCR for text height). Also OCR text that the PDF stores as outlines: PowerPoint exports rotated chart axis labels as filled paths, so they never appear in `text.json`. Also consider requiring one level more for colored or low-contrast text (MIL-STD-1472F raises its minimum from 16′ to 21′ for colored characters); see `references/legibility-thresholds.md`. OCR engine: start with Windows' built-in OCR (Windows.Media.Ocr via PowerShell: nothing to install, Windows only), then move to RapidOCR (pip, cross-platform) once the skill proves useful. Step 1 (text contrast, CT-1/CT-2, `scripts/contrast.py`) done. Step 2 (Windows OCR, `scripts/ocr.py`: whole-page pass, rotated retry for glyph-like shape clusters, unread areas listed; OCR text feeds size and contrast at medium confidence) done. Step 3 (color, `scripts/color.py`: CO-1 colors confusable under CVD simulation, CO-2 emphasis by color alone, CO-3 judged; DaltonLens) done. Not done: the "one level more for colored text" idea above.
- 23: Write SKILL.md, `rubrics/default.md`, `rubrics/presets.md`, and the reference notes. First version done: SKILL.md workflow (intake → render → measure → judge → scorecard), `rubrics/default.md` (FS-1, FS-2, CN-1), `scripts/scorecard.py`, and `outline.md` for judging. Remaining: reference notes (WCAG, 8H, ADA, CEFR) and more items as measures are added.
- 24: Write the readability script: CEFR word-level profile, problem patterns, and Flesch, Flesch-Kincaid and language adaptations as secondary signals. Verify what `textstat` covers.
- 25: Build test decks and posters with known flaws, and run evals. Started: `tools/make_test_decks.py` generates flaws-slides, flaws-poster, flaws-color with `.expected.json` levels, checked by the tests. Next: more cases (4:3, footers, overflow, Google exports), and evals of the agent's judged items.
- 26: Add the initial extra checks: cognitive load, data graphics, accessibility metadata, consistency. Include title vs. body size (hierarchy) under consistency; font_size.py already tags titles, bullets, and sub-bullets. Also layout: text overlapping other text, and text overflowing its box or the slide (e.g. AEL slide 19, where a line runs into the footer; contrast.py catches it only indirectly).
- 27: Build a solid test set: PPTX and Google Slides sources, plus PDFs exported from each. Cover 4:3 and 16:9 slides, and posters at several print sizes.
- 28: Font-size measure (`scripts/font_size.py`): cap-height visual angle; L1–L4 bounds 10/16/22′; defaults 8H for slides and 1.5 m for posters, plus 12H and 2 m presets; FS-1 body text vs FS-2 supporting text; findings name the kind of small text (bullets, labels, ...). Done; explained in README.md.
- 29: Validate against human judgment. Collect real decks and posters that experts rate as good or bad, run the skill on them, and compare scores and issues with the ratings (agreement, misses, false alarms). Use the results to tune thresholds and weights. Complements 25, which uses decks built with known flaws.

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
- 51: Add render backends for other platforms: PowerPoint on macOS, and check whether a slim LibreOffice install is enough. Note that PowerPoint 2019 can't open Google's .odp exports, so .odp needs LibreOffice.
- 52: Text normalization for the readability step. PowerPoint's PDFs attach bullet glyphs to the next word ("●How"). Google's PDFs keep emoji as text. Numbered lists can be numbered differently in the two exports (Google "4. 5." vs PowerPoint "1. 2." on the same slide).
- 53 (deferred): Consider add-ons that run this skill from inside each app: a PowerPoint add-in, a Google Slides add-on, and maybe Canva. Each would send the open deck (or an export of it) and show the scorecard in a side panel.
- 54 (deferred): Let frequent users shorten or suppress repeated notices, e.g. a per-user setting listing notice codes to hide (SRC-PDF) or a "brief" mode. Warnings that change results (FONT-SUB) should still get at least a one-line mention.
