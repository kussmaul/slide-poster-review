# Default rubric

Built-in items for slides and posters. A context rubric (organization, conference, course, lab)
can override any field of an item by repeating its ID, add new items, or change section weights.

Each item is rated at one of four levels, from Level 4 (best) to Level 1. A section's score is the
weighted average of its items' levels (e.g. 2.5 of 4). The overall score is the weighted average of
the section scores. Items that haven't been assessed are left out of both and listed separately.

Measured items are computed by scripts. Judged items are rated by the reviewing agent, and every
rating records its confidence.

## Sections

| section     | weight | notes                                      |
|-------------|--------|--------------------------------------------|
| Text size   | 3      | measured accessibility: weighted higher    |
| Contrast    | 3      | measured accessibility: weighted higher    |
| Color       | 2      | measured (planned)                         |
| Readability | 2      | measured + judged (planned)                |
| Content     | 2      | judged                                     |
| Format      | 1      | judged; mostly set by context rubrics (planned) |

## Measured items

### FS-1 Body text size
- section: Text size
- weight: 3
- measure: font_size
- source: ISO 9241-303; ANSI/HFES 100; MIL-STD-1472
- more: references/legibility-thresholds.md
- Level 4: On at least 90% of slides, all body text has a cap height of 22′ or more (about 40 pt at 8H). Comfortable for everyone, including the back row.
- Level 3: On at least 90% of slides, all body text is 16′ or more (about 29 pt at 8H). Comfortable reading.
- Level 2: On at least 90% of slides, all body text is 10′ or more (about 18 pt at 8H). Readable with effort.
- Level 1: On more than 10% of slides, some body text is under 10′. Hard to read from the back.

### FS-2 Supporting text size
- section: Text size
- weight: 1
- measure: font_size
- source: ANSI/HFES 100 (10′ minimum for footnotes and subscripts)
- more: references/legibility-thresholds.md
- Level 4: Footers, slide numbers, citations, and superscripts are 22′ or more.
- Level 3: Supporting text is 16′ or more.
- Level 2: Supporting text is 10′ or more: legible, though not comfortable.
- Level 1: Supporting text is under 10′ on more than 10% of slides.

### CT-1 Body text contrast
- section: Contrast
- weight: 3
- measure: contrast
- source: WCAG 2.x 1.4.3 Contrast (Minimum), 1.4.6 Contrast (Enhanced)
- more: https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html
- Level 4: On at least 90% of slides, all body text reaches 7:1 (4.5:1 for large text). Meets WCAG AAA.
- Level 3: On at least 90% of slides, all body text reaches 4.5:1 (3:1 for large text). Meets WCAG AA.
- Level 2: On at least 90% of slides, all body text reaches 3:1. Fails WCAG AA for normal-size text.
- Level 1: On more than 10% of slides, some body text is below 3:1.

### CT-2 Supporting text contrast
- section: Contrast
- weight: 1
- measure: contrast
- source: WCAG 2.x 1.4.3 Contrast (Minimum)
- more: https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html
- Level 4: Footers, slide numbers, citations, and superscripts reach 7:1 (4.5:1 if large).
- Level 3: Supporting text reaches 4.5:1 (3:1 if large).
- Level 2: Supporting text reaches 3:1.
- Level 1: Supporting text is below 3:1 on more than 10% of slides.

## Judged items

### CN-1 Key ideas are identifiable
- section: Content
- weight: 2
- source: Cognitive load and multimedia learning research (Mayer, signaling principle)
- Level 4: A viewer could state the 2–5 key ideas from the slides alone. Each is clearly signaled (titles, emphasis, summary) and the sequence builds toward them.
- Level 3: The key ideas can be identified, but one or two are weakly signaled or buried among details.
- Level 2: Key ideas must be inferred; titles are topics rather than messages, and emphasis is spread evenly.
- Level 1: No clear key ideas; slides read as a collection of loosely related content.
