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
| Color       | 2      | measured + judged                          |
| Readability | 2      | measured + judged                          |
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

### CO-1 Colors distinguishable with color-vision deficiency
- section: Color
- weight: 1
- measure: color
- source: WCAG 2.x 1.4.1 Use of Color; Vienot et al. 1999, Brettel et al. 1997, Machado et al. 2009 (simulation)
- more: https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html
- Level 4: On at least 90% of slides, no two main colors look alike with color-vision deficiency.
- Level 3: Some colors look alike only with blue-yellow color blindness (tritanopia, about 1 in 10,000 people).
- Level 2: On more than 10% of slides, some colors look alike with red-green color blindness (about 2% of men).
- Level 1: On more than 10% of slides, some colors look alike even with moderate red-green deficiency (about 8% of men in all).

### CO-2 Emphasis not by color alone
- section: Color
- weight: 1
- measure: color
- source: WCAG 2.x 1.4.1 Use of Color; technique G183 (3:1 lightness difference)
- more: https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html
- Level 4: Emphasized words and links also differ in weight, style, size, or underline, not only in color.
- Level 3: Some words are emphasized by color alone, but also differ in lightness from the surrounding text by 3:1 or more.
- Level 2: On more than 10% of slides, words are emphasized by color alone with less than 3:1 lightness difference.
- Level 1: On more than 10% of slides, words emphasized by color alone look the same as the surrounding text with color blindness.

### RD-1 Vocabulary level
- section: Readability
- weight: 2
- measure: readability
- source: CEFR-J Wordlist 1.5 and Octanove C1/C2 profile; vocabulary coverage research (Laufer 1989; Hu & Nation 2000; Laufer & Ravenhorst-Kalovski 2010)
- more: references/readability.md
- Level 4: 98% or more of the words are at or below the audience's CEFR level (B2 for a general audience, B1 for second-language readers). Most readers understand without help.
- Level 3: 95% or more. Readers get the gist but need some support, e.g. definitions or the speaker.
- Level 2: 90% or more. Many readers will miss parts of the text.
- Level 1: Under 90%. The vocabulary is a barrier for this audience.

### RD-2 Sentence length
- section: Readability
- weight: 1
- measure: readability
- source: Plain-language guidance (15–20 words per sentence on average)
- more: references/readability.md
- Level 4: On at least 90% of slides, every sentence has 15 words or fewer. A bullet without end punctuation counts as one sentence.
- Level 3: On at least 90% of slides, 20 words or fewer.
- Level 2: On at least 90% of slides, 30 words or fewer.
- Level 1: On more than 10% of slides, some sentence or bullet has more than 30 words.

### RD-3 Acronyms spelled out
- section: Readability
- weight: 1
- measure: readability
- source: Plain-language guidance; WCAG 2.x 3.1.4 Abbreviations (AAA)
- more: https://www.w3.org/WAI/WCAG22/Understanding/abbreviations.html
- Level 4: Every acronym is spelled out somewhere in the deck, e.g. "Think-Pair-Share (TPS)".
- Level 3: One or two acronyms are never spelled out.
- Level 2: Three to five acronyms are never spelled out.
- Level 1: Six or more acronyms are never spelled out.

## Judged items

### CO-3 Meaning doesn't depend on color alone
- section: Color
- weight: 2
- source: WCAG 2.x 1.4.1 Use of Color
- more: https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html
- Level 4: Every chart, legend, diagram, and highlight that uses color also uses labels, patterns, shapes, or position; nothing is lost in grayscale or simulation.
- Level 3: One or two places rely on color, but the meaning is also stated in nearby text.
- Level 2: Some charts or legends can only be read by color, e.g. series told apart only by a color key.
- Level 1: Key content depends on color alone, e.g. "the red items are…", or results shown only as colored cells.

### RD-4 Language suits the audience
- section: Readability
- weight: 2
- source: Plain-language guidance; CEFR; research on second-language reading
- more: references/readability.md
- Level 4: Wording is plain and direct for this audience: technical terms are defined or expected, with no idioms, culture-specific references, or stacked nouns that would trip up readers.
- Level 3: A few idioms, phrasal verbs, or undefined terms, but the meaning is clear from context.
- Level 2: Several places where readers outside the field, or reading in a second language, would likely misread or stall.
- Level 1: Jargon, idioms, or dense phrasing throughout; much of the text is hard for this audience.

### CN-1 Key ideas are identifiable
- section: Content
- weight: 2
- source: Cognitive load and multimedia learning research (Mayer, signaling principle)
- Level 4: A viewer could state the 2–5 key ideas from the slides alone. Each is clearly signaled (titles, emphasis, summary) and the sequence builds toward them.
- Level 3: The key ideas can be identified, but one or two are weakly signaled or buried among details.
- Level 2: Key ideas must be inferred; titles are topics rather than messages, and emphasis is spread evenly.
- Level 1: No clear key ideas; slides read as a collection of loosely related content.
