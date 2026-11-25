# Example: POGIL-style class session

An example context rubric for slides used to facilitate a class session in which student teams
work through a guided-inquiry activity (POGIL-style: teams of 3-4 with roles, a model to explore,
guiding questions, report-outs). The slides support team work rather than present content.
Adapt it to your own course; it is not an official POGIL Project document.

Use: `python scripts/scorecard.py OUTPUT_DIR --rubric rubrics/examples/pogil-class-session.md`

Judging needs: the activity (or its title and learning objectives), if available.

## Sections

| section | weight | notes |
|---------|--------|-------|
| Format  | 3      | slides that structure team work |
| Content | 2      | key ideas = the session's content and process objectives |

## Judged items

### CN-1 Session objectives are identifiable
- Level 4: The session's content objectives and process skills (e.g. teamwork, information processing) are stated or clearly signaled, and the sequence of slides follows the activity toward them.
- Level 3: The objectives can be identified, but one is only implied, or process skills are not mentioned.
- Level 2: The objectives must be inferred from the activity; slides list tasks without saying what they are for.
- Level 1: No objectives can be identified; the slides read as unrelated instructions or content.

### CL-1 Slides support team work, not lecture
- Level 4: Each slide shows what teams should do now; content slides are short and point back to the activity.
- Level 3: Mostly task-focused, but a few slides present content that teams are meant to work out themselves.
- Level 2: Many slides present content at length, so the session is likely to turn into a lecture.
- Level 1: The deck is mainly a lecture; team work is an afterthought.

### FM-1 Session structure is visible
- section: Format
- weight: 2
- source: POGIL facilitation practice (teams with roles; explore, invent, apply; report-out; closure)
- Level 4: Slides cover forming teams and assigning roles, each part of the activity, report-outs, and a closing reflection or summary.
- Level 3: One of these is missing, e.g. no closing reflection.
- Level 2: Several are missing; teams would need the facilitator to tell them how the session runs.
- Level 1: No visible structure; the slides don't follow the activity.

### FM-2 Instructions are actionable
- section: Format
- weight: 2
- source: POGIL facilitation practice
- Level 4: Every task slide says which questions or part to work on, for how long, and what teams produce or report.
- Level 3: Most task slides do, but some omit the time or the expected product.
- Level 2: Task slides name the questions only; teams must ask what to do or when to stop.
- Level 1: Tasks are unclear or missing.

### FM-3 Answers are not revealed early
- section: Format
- weight: 2
- source: Guided inquiry (students construct concepts before they are told)
- Level 4: No slide shows answers to activity questions before teams have worked on them; any answers or summaries come after the matching report-out.
- Level 3: One slide gives away part of an answer that teams are meant to work out.
- Level 2: Several slides show answers or the concept before teams have explored the model.
- Level 1: The slides present the concepts first, so the activity becomes confirmation rather than inquiry.
