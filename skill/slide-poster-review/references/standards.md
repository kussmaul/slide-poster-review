# Standards and guidance behind the rubric

Compiled 2026-11-25 (QUEUE task 23). Items marked *unverified* were seen only in secondary sources
or summarized from memory of the standard; check the original before quoting them.
Evidence for text size is in [legibility-thresholds.md](legibility-thresholds.md), and for
readability in [readability.md](readability.md).

## WCAG 2.x

The Web Content Accessibility Guidelines (W3C; 2.2 is current, 2023) are written for web content.
They are widely applied to documents, including slides and PDFs. Level A and AA are the usual legal
targets; AAA is enhanced.

| Rubric item | WCAG success criterion | Level | How this skill applies it |
|---|---|---|---|
| CT-1, CT-2 | 1.4.3 Contrast (Minimum): 4.5:1, or 3:1 for large text | AA | Ratio of sampled text and background colors; never rounded |
| CT-1, CT-2 | 1.4.6 Contrast (Enhanced): 7:1, or 4.5:1 for large text | AAA | Level 4 |
| CO-1, CO-2, CO-3 | 1.4.1 Use of Color: color isn't the only visual means of conveying information | A | Simulated color-vision deficiency; color-only emphasis; judgment |
| CO-2 | Technique G183: links that differ from text only by color need 3:1 contrast with it | — | Level 3 boundary |
| AC-1 | 1.1.1 Non-text Content: text alternatives | A | Alt text on pictures, charts, SmartArt, media |
| AC-2 | 2.4.2 Page Titled; 2.4.6 Headings and Labels | A; AA | Slide title placeholder present and distinct |
| AC-3 | 1.3.2 Meaningful Sequence | A | Title read first |
| RD-3 | 3.1.4 Abbreviations | AAA | Acronyms spelled out somewhere in the deck |
| LY-4 | 3.2.3 Consistent Navigation; 3.2.4 Consistent Identification | AA | By analogy only: titles in a consistent place |

**Large text.** WCAG defines it as at least 18 pt, or 14 pt bold, at typical reading distance.
For projection the skill converts this to a visual angle: a cap height of 21.5′, or 16.7′ for bold
(see the contrast section of the README).

**Contrast ratio** = (L1 + 0.05) / (L2 + 0.05), with L the relative luminance of the lighter and
darker color (sRGB, linearized). Range 1:1 to 21:1.

Links: https://www.w3.org/TR/WCAG22/ and the "Understanding" pages linked from each rubric item.

## Laws that point to WCAG (United States)

- **ADA Title II rule (US Department of Justice, April 2024).** State and local governments,
  including public colleges and universities, must make web content and mobile apps conform to WCAG
  2.1 Level AA. Posted documents such as PDFs and slide decks are covered, with some exceptions
  (e.g. archived content, some pre-existing documents). Compliance dates: April 2026 for entities
  serving 50,000 people or more, April 2027 for smaller ones. *unverified: check the exceptions
  and dates in 28 CFR part 35, subpart H, before relying on them.*
- **Section 508 (Rehabilitation Act; refresh 2017).** US federal agencies' electronic content
  must meet WCAG 2.0 Level AA.
- **ADA Standards for Accessible Design (2010), 703.5.** Sizes for visual characters on signs, by
  viewing distance. These are physical signs, not slides, but they give a generous upper anchor for
  text size (see legibility-thresholds.md).

Other countries have similar rules, e.g. the EU's European Accessibility Act and EN 301 549, which
also reference WCAG.

## Viewing distance (8H)

AVIXA (formerly InfoComm) standard ANSI/AVIXA V202.01:2016, *Display Image Size for 2D Content in
Audiovisual Systems* (DISCAS), relates image height to the farthest viewer. The long-standing rule
of thumb behind it is 8H for basic viewing (reading text that fills the screen), 6H for detailed
viewing, and 4H for inspection. The skill uses 8H for slides and offers 12H for large rooms with
undersized screens. Details and conversions are in legibility-thresholds.md.

## Office accessibility checkers

Microsoft's Accessibility Checker (PowerPoint: Review > Check Accessibility) reports errors for
missing alternative text and missing slide titles, warnings for duplicate slide titles, and asks
authors to check reading order. AC-1 to AC-3 follow these rules so that results match what authors
see in PowerPoint. Since 2023, Office can generate alt text automatically and labels it as
generated (e.g. "Description automatically generated"); the skill counts this as present but
unchecked. Google Slides has no built-in checker.

## Layout and consistency (LY items)

- **Colliding or cut-off text (LY-1)** needs no standard: text that can't be seen can't be read.
- **Hierarchy (LY-2).** Titles signal structure (Mayer's signaling principle, below). The 1.1 and
  1.2 ratios are common steps in type scales (e.g. the "minor third", 1.2). They are design
  conventions, not research findings.
- **Few fonts (LY-3)** and **consistent title placement (LY-4)** follow graphic design guidance:
  Williams, *The Non-Designer's Design Book* (repetition, contrast); Duarte, *slide:ology*. The
  bounds are conventions. Revisit after validation (QUEUE 29).

## Cognitive load and multimedia learning (CL-1, CN-1)

- Sweller's cognitive load theory: working memory is limited, so extraneous load (from layout,
  decoration, redundant text) competes with learning.
- Mayer, *Multimedia Learning* (3rd ed., 2021): coherence (leave out extraneous material),
  signaling (highlight the essential), redundancy (don't put narration on screen word for word),
  spatial contiguity (put words next to the graphics they describe), segmenting (one step at a
  time).
- Alley, *The Craft of Scientific Presentations*: the assertion-evidence structure, a sentence
  headline that states the slide's message, supported by visual evidence. Studies by Alley and
  colleagues found better comprehension than with topic-and-bullet slides. *unverified: effect
  sizes.*

The hints in `layout.json` (over 40 words, over 6 lines) only point to slides to look at. No
research supports a fixed word limit for slides.

## Data graphics (DG-1)

- Cleveland & McGill (1984), *Graphical perception*: people judge position along a common scale
  most accurately, then length, angle, area, and color. Bar and dot charts beat pie and 3-D charts.
- Tufte, *The Visual Display of Quantitative Information* (1983): data-ink, chartjunk, and the
  "lie factor" (distortions such as 3-D and truncated axes).
- Few, *Show Me the Numbers* (2nd ed., 2012): direct labels over legends; when to use tables
  instead of charts.
