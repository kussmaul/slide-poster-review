# Example: conference poster

An example context rubric for a research poster at an academic conference. Replace the required
parts and sizes with those in your conference's call for posters; it is not any particular
conference's rubric.

Use: `python scripts/scorecard.py OUTPUT_DIR --rubric rubrics/examples/conference-poster.md`
(and pass the print size to font_size.py and contrast.py, e.g. `--print-size 48x36in`).

Judging needs: the print size and orientation the conference allows; the abstract, if available.

## Sections

| section | weight | notes |
|---------|--------|-------|
| Format  | 2      | parts the conference expects; reading path |
| Content | 3      | posters are read in passing: key ideas matter most |

## Measured items

### LY-4 Titles in a consistent place
- weight: 0
- notes: not used for posters

## Judged items

### CN-1 The main finding is clear in seconds
- Level 4: A passer-by could state the main finding within about 10 seconds: it is in the title or a large takeaway statement, and the results support it visibly.
- Level 3: The main finding is stated, but small or placed where it is easy to miss.
- Level 2: The finding must be pieced together from the results section.
- Level 1: No finding is stated; the poster describes a project without saying what was learned.

### FM-1 Required parts are present
- section: Format
- weight: 2
- source: typical call for posters (edit to match yours)
- Level 4: Title; authors and affiliations; motivation or research question; methods; results; conclusions or takeaways; references; contact information (e.g. email or QR code).
- Level 3: One part is missing or hard to find.
- Level 2: Two or three parts are missing.
- Level 1: Most parts are missing; the poster is an abstract or a set of figures.

### FM-2 Reading path is obvious
- section: Format
- weight: 1
- source: Poster design guidance (columns or rows, numbered or headed sections)
- Level 4: Sections read in an obvious order (columns or rows, with headings or numbers); nothing competes with the path.
- Level 3: The order is mostly clear, with one place where readers must search for what comes next.
- Level 2: Readers must work out the order; sections are scattered or unlabeled.
- Level 1: No discernible order.

### FM-3 Size and orientation follow the call
- section: Format
- weight: 1
- source: the conference's call for posters
- Level 4: The page size and orientation match what the conference allows, at the stated print size.
- Level 3: The shape matches, but the file is at a different scale and must be enlarged to print (fine if the text is still large enough).
- Level 2: The orientation or proportions differ from what is allowed, so printing would crop or leave margins.
- Level 1: The poster can't be printed at an allowed size.
