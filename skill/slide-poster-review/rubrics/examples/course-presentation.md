# Example: course presentation

An example context rubric for student presentations in a course, or talks at a lab or group
meeting. Edit the required slides, time limit, and citation rules to match your assignment.

Use: `python scripts/scorecard.py OUTPUT_DIR --rubric rubrics/examples/course-presentation.md`

Judging needs: the time limit (minutes), and the assignment's required slides if they differ
from FM-1 below.

## Sections

| section | weight | notes |
|---------|--------|-------|
| Format  | 2      | assignment requirements |
| Content | 3      | the main goal of the assignment |

## Judged items

### FM-1 Required slides are present
- section: Format
- weight: 2
- source: assignment (edit to match yours)
- Level 4: Title slide with the presenters' names and the date; an agenda or outline; the main content; a conclusion or summary; references; a final slide for questions or discussion.
- Level 3: One required slide is missing.
- Level 2: Two or three are missing.
- Level 1: Most are missing.

### FM-2 Sources are cited where they are used
- section: Format
- weight: 2
- source: Academic integrity guidance; assignment
- Level 4: Every figure, table, quotation, and data point from another source is cited on the slide where it appears, and the references slide lists them all.
- Level 3: Sources are in the references, but a few slides use material without a citation on the slide.
- Level 2: Several images, quotations, or data have no citation anywhere.
- Level 1: Sources are not cited.

### FM-3 Length fits the time
- section: Format
- weight: 1
- source: Common guidance of about one content slide per minute
- Level 4: The number of shown (not hidden) content slides fits the time limit, about one per minute or fewer.
- Level 3: Up to about 1.5 slides per minute; the talk will feel rushed in places.
- Level 2: Up to about 2 per minute; slides will be skipped or rushed.
- Level 1: More than 2 per minute, or far too few slides to fill the time.
