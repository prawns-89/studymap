---
description: Analyse a course's past papers into analysis/topics.json and papers.json, then write report.md and the Plan tab
argument-hint: <course-folder>
---

# Paper analysis for `$ARGUMENTS`

You are the thinking half of Studymap's paper-analysis stage (BRIEF.md sections 4B and 6.2). The CLI does all the
arithmetic; your job is to read the course and write two JSON files that are true to the papers. Never invent a
question, a mark or an answer.

## 1. Ingest and orient

1. Run `uv run studymap ingest $ARGUMENTS -q`. It is cached; only new or changed files are read again.
2. Read `$ARGUMENTS/course.yaml`, especially `exams` and `notes_for_claude` (syllabus, dates, cheat-sheet rules).
3. Read `$ARGUMENTS/_studymap/corpus/outline.md`. It lists every slide title per page, the papers and their keys,
   and the labs. **Plan from the outline; do not read every slide.** Open `corpus/text/<sid>.md` only for the pages
   you need to judge.
4. Print the schemas once: `uv run studymap schema topics` and `uv run studymap schema papers`.

## 2. Topics: `_studymap/analysis/topics.json`

- **Clusters:** 2 to 12, usually one per lecture unit in teaching order (`order` 1, 2, ...). They become the map's colours.
- **Topics:** one per thing a question could be about. 15 to 40 for a typical course.
  - `id` in kebab-case.
  - `name` a full descriptive name.
  - `label` 32 characters or fewer, for charts.
  - `sources` are page ranges from the outline, e.g. `slides/7 - CPU Scheduling.pdf#p8-13`. Labs that are in the
    syllabus count as sources too.
- A topic the papers ask about but the slides don't cover stays in the list. Give it empty `sources` and a `note`; the
  report will flag it.
- `uncovered_ok`: globs for slides that deliberately belong to no topic (title slides, course administration).

## 3. Papers: `_studymap/analysis/papers.json`

Read each paper's text view; for `image-only` pages read the page images (`corpus/img/...`). Read keys the same way.
With more than three papers, give each paper to its own subagent in parallel (topic list and schema in the prompt,
questions JSON back) and merge the results. Never load every paper at once.

**One `papers` entry per file:**

- `id`: the file stem.
- `kind`: `exam`, or `sample` for unmarked practice questions.
- `exam`: the name used in course.yaml.
- `year`, `date`, `duration_min`, `total_marks`.
- `keys`: the key files, with `status` `unofficial` when the key says so. A key page inside the paper file is cited as
  `papers/x.pdf#p3`.
- `transcribed_from_image`: true for scans.
- `relevance`: below 1 only with a `relevance_reason`, e.g. a different instructor or syllabus.
- `notes`: anything a reader of the scan should know, e.g. a student's handwriting on it.

**One `questions` entry per smallest part that carries its own marks:**

- `type`: one of the brief's list.
- `mode`, by the brief's rules:
  - compute, draw, design, write, trace or simulate → `apply`;
  - explain, why, compare or justify → `understand`;
  - definitions, names and constants → `recall`.
- `difficulty`: easy, medium or hard.
- `topics`: the most specific 1 to 4.
- `text`: transcribed faithfully. Code goes in ``` fences with a language; tables become pipe tables.
- `src`: the page the question is on.
- `answer`: the key's answer in faithful prose, with `src` pages. Check every number and every code trace yourself.
  Where the key is wrong, ambiguous or accepts several answers, say so in `caveat`.
- `repeats`: similar questions in other papers.
- `unmapped_reason`: required when `topics` is empty.

The marks of an exam paper must add up to `total_marks`; use `marks_note` to explain a choice ("any 4 of 5").

**`patterns`:** 3 to 8 plain sentences a student can act on, each citing its questions. Any number in a sentence must
match the papers.

**`notes`:** caveats for the top of the report: a change of format or instructor, the syllabus and date, stale or
missing files.

## 4. Check, derive, look

1. Run `uv run studymap validate $ARGUMENTS` and fix every error (they are `file:line`). Read the warnings and decide.
2. Run `uv run studymap report $ARGUMENTS`, then read `_studymap/report.md` critically. Does the order for each exam
   match what the papers plainly emphasise? If not, fix the analysis (topic granularity, mapping, relevance), never
   the numbers.
3. Run `uv run studymap build $ARGUMENTS` and then `uv run studymap check $ARGUMENTS`.

## 5. Tell the user

Keep it short:

- the top topics and the patterns for the next exam;
- what is unverified: transcriptions, unofficial keys, questions without answers;
- any key errors you found;
- anything they should do: missing papers, stale slides, a course.yaml field to fill in.
