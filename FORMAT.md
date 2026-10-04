# Content format

The study content is plain Markdown in `<course>/_studymap/content/`. It is the source of truth once written: you can
edit it by hand, and `studymap validate` reports problems as `file:line: message`.

## Files

| File | What it holds |
|---|---|
| `course.md` | Optional page settings in front matter (see below). |
| `sheet.md` | Optional front and back matter for the cheat sheet (see the end of this file). |
| `NN-<cluster>.md` | One file per cluster, any name ending in `.md`; files are read in name order. |

`course.md` front matter (every key optional):

```yaml
---
title: CS F372 Operating Systems        # default: code and name from course.yaml
eyebrow: Midsem 2026
tagline: Processes, scheduling, memory.
center: os-overview                       # node at the centre of the map
center-caption: one kernel, many processes
howto: Start with the Plan tab.
---
```

## A cluster file

````markdown
---
cluster: sched
name: CPU scheduling
kicker: Unit 4
order: 4
desc: Which ready process runs next
---

## mlfq | MLFQ: queues, demotion, priority boost | MLFQ | mode=apply
- New jobs enter the top queue; a job that uses its whole quantum moves down one queue. {src: slides/7 - CPU Scheduling.pdf#p21}
- A periodic priority boost (aging) stops long jobs starving. {src: slides/7 - CPU Scheduling.pdf#p24}

### Steps
1. Put each arrival in Q0 at its arrival time.
2. ...

### Worked example {src: papers/2025-midsem.pdf#p2}
The problem, then a line that starts with **Solution**, then the worked solution.

**Solution**
...

### Variant
A fresh problem in the same pattern, with **Solution** as above.

### Where marks are lost
- Forgetting that an aged process jumps back to Q0.

### Links
- sched-policies | MLFQ runs round robin inside each queue
- context-switch | every demotion and boost is a switch
````

### Front matter

| Key | Required | Meaning |
|---|---|---|
| `cluster` | yes | id, `a-z 0-9 -` |
| `name` | yes | shown on the map and in the Learn tab |
| `kicker` | no | small caps line above the name |
| `order` | no | sort order (default: file order) |
| `desc` | no | one line |
| `color` | no | 0 to 11 (default: by order) |

### Nodes

`## <id> | <title> | <label> | key=value ...`

- `id`: `a-z 0-9 -`. When it equals a topic id in `analysis/topics.json`, the node takes that topic's weight, mode
  and past questions automatically.
- `title`: the full name. `label`: short map label (optional; defaults to the title).
- Attributes (all optional):
  - `mode=recall|understand|apply`: default is the topic's mode from the papers.
  - `weight=high|med|low`: default is the topic's weight from `weightage.json`.
  - `topic=<topic-id>`: when the id is not itself a topic, e.g. one topic split into two nodes.
  - `tier=1|2|3`: overrides the map size, which otherwise follows the weight.

### Facts

The `- ` lines directly under a node heading are its facts: one crisp, examinable statement each.

- Every fact cites where it comes from: `{src: <ref>}` at the end, several refs separated by `; `.
- Indented lines continue the fact above.
- `**bold**`, `*italic*` and `` `code` `` work.

Refs are corpus refs:

| Ref | Points at |
|---|---|
| `slides/x.pdf#p14` | a page; ranges like `#p8-13` work too |
| `deck.pptx#s3` | a slide |
| `notes/y.md#L10-42` | lines |
| `papers/2025-midsem.pdf#p2` | a paper page |

### Sections

`### <name>`, optionally followed by `{src: ...}` or `{gen: ...}`. The body is ordinary Markdown: paragraphs, lists,
` ``` ` code fences with a language, and pipe tables. The section name sets how it is shown.

| Mode | Section | Shown as |
|---|---|---|
| recall | `Formulas` | One formula per `- ` line; boxed on the cheat sheet |
| recall | `Mnemonic` | Only when it really helps |
| understand | `Core idea` | Plain words |
| understand | `Why it works` | |
| understand | `Derivation` | |
| understand | `Misconceptions` | `- wrong idea :: what is true` |
| understand | `What changes if` | `- What if the quantum doubles? :: answer`, shown as cards with hidden answers |
| understand | `Explain it back` | A prompt, then `**Model answer**` and the answer (hidden until asked) |
| apply | `Steps` | A numbered list, revealed one step at a time |
| apply | `Worked example` | Problem, then `**Solution**`; cite the source |
| apply | `Variant` | A fresh problem in the same pattern with `**Solution**` (`{gen: ...}` reserved for M4 generators) |
| apply | `Where marks are lost` | `- ` list |
| any | `Conceptual questions` | `- question :: answer` pairs: the short conceptual probes this course likes. Shown as cards in Learn and as CONCEPT Q on the cheat sheet. |
| any | `Diagram` | A picture the paper asks you to draw. Put it in a ``` fence; it is kept monospace and never wrapped. On the cheat sheet it is auto-sized to fit, and a diagram too wide for one column becomes a full-width band. Keep lines under about 80 characters. |
| apply | `Code` | Annotated reference code |
| apply | `Trace` | Given input or state, predict the output; `**Answer**` hidden |
| apply | `Write it` | A task, then `**Solution**` |
| any | `Lookalikes` | `- term A :: how it differs from term B` |
| any | `Links` | `- <node-id> \| why they are related` |

Every apply node needs a `Worked example`, a `Variant` and `Where marks are lost` (BRIEF section 12); `validate`
warns when one is missing. Past paper questions on a node's topic are attached automatically: don't copy them in.

## What goes on the cheat sheet

`studymap cheatsheet` takes, in priority order:

1. `Formulas`;
2. `Steps`, compressed;
3. facts of high-weight nodes;
4. `Lookalikes`;
5. `Where marks are lost`;
6. short `Worked example`s of the top apply nodes;
7. `Code` blocks under 12 lines;
8. the remaining facts.

Write formulas and steps so they make sense on their own.

Each block is labelled on the sheet (`KEY FORMULAS`, `HOW TO SOLVE`, `DIAGRAM`, `PAST PAPER`, `TRAP`, `WHY IT WORKS`, …), and each
cluster opens with a `WHAT TO EXPECT IN THE EXAM` panel built automatically from `analysis/papers.json`: the real questions asked on
that cluster, with their marks and why that kind of knowing is needed.

## `sheet.md`: the cheat sheet's front and back matter

Optional. Four `##` sections, each ordinary Markdown (prose, lists or pipe tables):

| Section | Where it goes | What it is for |
|---|---|---|
| `## How to think` | front, full width | The decision procedure: read the question, pick the method, and why. Write it as `**Q1. …**` paragraphs. |
| `## Master table` | back, full width | A pipe table: *what the question says* → *method* → *key formula* → *what to write*. |
| `## Sanity checks` | back | A `- ` list of checks to run before handing in. |
| `## Notation` | back | A pipe table of symbols and their meanings. |

The contents list on page 1 is generated with real page numbers, and every page carries a running header.
