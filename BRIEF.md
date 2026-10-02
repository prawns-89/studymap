# Studymap: build brief

You are building **Studymap**, a local tool that turns a folder of course material (slides, notes, labs, past papers) into a study website aimed at one thing: **doing as well as possible in that course's actual exam format**.

Read this whole brief and the `reference/` folder before writing code. Build in the milestones in section 11. After each milestone, run the tests and show me the output on a real course folder. Ask me before you change the folder contract (section 3), drop a feature, or add a paid or cloud dependency.

---

## 1. Who it's for and why

I'm a third-year Electronics and Instrumentation student at BITS Pilani, Goa. I'll use this every semester, for every course, so it has to be general. The courses that matter most are technical ones like:

- **Computer Architecture (CS F342)**:
  - MIPS assembly in the MARS simulator;
  - a MIPS processor modelled in C++;
  - labs graded by viva;
  - paper questions on datapath and control, pipelining and hazards, performance/CPI, caches, and number representation.
- **Operating Systems (CS F372)**:
  - slide decks and a prescribed textbook (Silberschatz, plus OSTEP and CS:APP);
  - C programming labs and the Stanford Pintos project;
  - past midsem papers and sample questions;
  - paper questions on scheduling, memory and paging, synchronization (locks, condition variables, semaphores), deadlock, and file systems.
- Also DSP and image processing (MATLAB), analog electronics (circuits, SPICE), and recall-heavy theory or humanities courses with MCQ quizzes.

A plain MCQ generator or a summary isn't enough. For every topic it has to work out three things:

1. **What kind of knowing the exam needs**:
   - **Recall**: memorise it (definitions, constants, names, formula statements, standard results).
   - **Understand**: be able to explain why, compare, justify, and carry the idea to a new situation.
   - **Apply**: be able to *do* it on unseen inputs, for example:
     - solve a numerical;
     - draw a Gantt chart or a pipeline diagram;
     - trace or write code;
     - run and interpret a simulation.
2. **How the paper asks it**: question types, marks, recurring patterns, and what repeats across years.
3. **What I need in order to get full marks**: model answers laid out the way an examiner awards marks, worked examples, fresh practice in the same format, the pitfalls where marks are usually lost, and a dense cheatsheet.

---

## 2. What "done" looks like

I point it at a course folder, and a few minutes later I have:

- **`index.html`**: one self-contained file that works offline. I can open it locally or send it to friends over WhatsApp or Drive.
- **`cheatsheet.pdf`**: everything important packed into at most 8 A4 pages, dense but readable.
- **`report.md`**: what the papers ask, topic weightage, coverage gaps, and anything unverified.

When I add new material (a new slide deck, this year's paper), I re-run it. Only what changed is reprocessed, and my edits are preserved.

**Not wanted**:
- accounts or a server;
- a cloud database or paid APIs (see section 4);
- a generic note-taking app;
- spaced-repetition scheduling. That might come later; don't build it now.

---

## 3. Input folder contract

```
CS-F372-OS/
  course.yaml          optional settings (see below)
  slides/              lecture decks: .pdf .pptx
  notes/               anything else to read: .pdf .docx .md .txt, textbook chapters
  labs/                lab sheets (.pdf/.md) and code (.c .cpp .h .s .asm .m .py .v .sv .cir ...), one subfolder per lab is fine
  papers/              past papers and keys, named YYYY-exam[-variant].pdf
                       e.g. 2024-midsem.pdf, 2024-midsem-key.pdf, 2023-compre.pdf, sample-questions.pdf
  extra/               anything else (tutorial sheets, assignments, reference notes)
```

Rules:
- Every subfolder is optional, and unknown subfolders are treated as `notes/`.
- With no papers, it still works. It weights topics from slide emphasis and tutorial sheets, and says so plainly in the report and on the site.
- Answer keys are matched to their paper by name (`-key`, `-solutions`, `-sol`).
- Scanned or handwritten PDFs are expected; old papers often are.
- `course.yaml` (every field optional):

```yaml
name: Operating Systems
code: CS F372
exams:
  - name: midsem
    weight: 30
    format: "90 min, closed book, 5 long questions"
  - name: compre
    weight: 40
    format: "3 h, part A short answers, part B long"
cheatsheet: { pages: 8, paper: A4, columns: 4, allowed: true }
labs_viva: true                 # generate viva question banks for labs
focus: ["scheduling", "synchronization"]   # topics I want extra depth on
ignore: ["slides/00-intro.pdf"]
notes_for_claude: "Midsem covers decks 1-12 only."
```

---

## 4. Architecture

There are two halves, kept strictly apart.

**A. Deterministic tool: `studymap`**, a Python CLI. No AI calls. It handles everything mechanical:
- `studymap ingest <course>`: extract text, images and code from every source into `_studymap/corpus/`, with provenance (file plus page or slide number). Results are cached by file hash.
- `studymap validate <course>`: parse and validate the content files (section 8), with errors given as `file:line`.
- `studymap verify <course>`: run every numerical check script and code runner (section 6.5) and record which items pass, fail, or are unverified.
- `studymap build <course>`: render `index.html`.
- `studymap cheatsheet <course>`: render `cheatsheet.pdf` with auto-fit (section 9).
- `studymap check <course>`: headless browser test of the built site, covering console errors, screenshots and offline loading.
- `studymap serve <course>`: optional local server with live reload while I edit content.

**B. Thinking, done by Claude Code itself**, through a project slash command `/study <course-folder>` (in `.claude/commands/`, or a project skill). It orchestrates the stages in section 6:
1. run `ingest`;
2. read the corpus;
3. write the analysis and content files;
4. run `validate` and `verify`, then fix problems;
5. run `build` and `cheatsheet`;
6. run `check`;
7. summarise.

This way I need no API key, it runs on my Claude plan, and Claude can read scanned papers and slide images directly.

**Optional, later**: an `--api` mode where the CLI calls the Anthropic API for headless runs. Design the stage interfaces so this is possible, but don't build it yet.

Requirements for the orchestration:
- **Never load a whole course into one context.**
  - Summarise per source first (`corpus/summaries/<source>.md`), then synthesise per cluster.
  - Use subagents in parallel for per-source work.
- **Resumable**: keep a manifest (`_studymap/state.json`) of stage, inputs and hashes, so an interrupted run continues and a re-run only redoes what changed.
- **My edits win**:
  - Content files are the source of truth once generated.
  - Regenerating never silently overwrites a file I've edited. Detect edits by hash and ask, or write a `.proposed` file next to it.
  - Initialise a git repo in `_studymap/content/` so every run is a diffable commit.

Output tree:

```
<course>/_studymap/
  index.html  cheatsheet.pdf  report.md
  content/      source of truth (human-editable text, section 8)
  analysis/     papers.json, weightage.json
  corpus/       extracted text, images, summaries
  verify/       per-question check scripts and results
  generators/   drill generators for this course (section 6.4)
  state.json
```

---

## 5. Suggested stack (change with a reason)

- **Python and libraries**:
  - Python 3.11+ with `uv`, `pydantic` for schemas, `numpy` (map layout) and `pytest`.
  - Extraction: `pymupdf` for PDFs (text plus page renders), `python-pptx`, `python-docx`.
- **Browser and rendering**:
  - `playwright` with Chromium for the PDF cheatsheet and site checks.
  - KaTeX for maths and highlight.js (or Prism) for code. Bundle both and inline them into the HTML; no CDN in the output.
  - Fonts subset and inlined as woff2 so the site is offline-first.
- **Code and simulation runners**: auto-detect them, and mark items "unverified" if a runner is missing.
  - `gcc`/`g++` for C/C++;
  - MARS (`java -jar Mars.jar nc ...`) or `spim` for MIPS;
  - `iverilog` or Verilator for Verilog;
  - GNU Octave for MATLAB code;
  - `ngspice` for circuits;
  - `python` for Python.

---

## 6. Pipeline stages

### 6.1 Ingest
- Extract text with page or slide provenance from every file.
- Render page images for:
  - figures (datapath diagrams, circuits, Gantt charts, plots);
  - pages with little extractable text, so they can be OCR'd or read visually.
- Copy code verbatim and keep the language tag.
- Deduplicate near-identical slides, since decks often repeat.

### 6.2 Paper analysis (`analysis/papers.json` plus a section in `report.md`)

For every past-paper question, record:
- `id`, `paper`, `year`, `exam`, `number`, `marks`
- `type`, one of:
  - `mcq`, `short`, `long-explain`, `compare`
  - `numerical`, `derivation`, `diagram`
  - `code-write`, `code-trace`, `code-fix`
  - `design`, `simulation`
- `topics` (content node ids), `difficulty`, and `repeats` (ids of similar questions in other years)
- `answer`, if a key exists

Derive from this:
- topic weightage (marks per topic per exam, and frequency);
- the question-type mix per exam;
- the **recurring patterns**, written as plain sentences. For example:
  - "every OS midsem has a 6–8-mark scheduling numerical with 4–5 processes, asking for average waiting time under two policies";
  - "CA always asks to draw a 5-stage pipeline diagram with forwarding for a 4–6 instruction MIPS snippet".

### 6.3 Content synthesis (the map)

- Clusters (2–12) of nodes. A node is one thing a question could be about.
- Every node has:
  - `id`, `title`, `label`, `tier`
  - `mode`: recall, understand or apply
  - `weight`: high, med or low, from the paper analysis, with slide emphasis as a fallback
  - `facts`, each with provenance
  - `links` to other nodes, each with a short reason
- Then, depending on the mode:
  - **Recall**: crisp facts and formulas; a mnemonic only if it genuinely helps. These go to the cram sheets and the cheatsheet.
  - **Understand**:
    - the core idea in plain words;
    - why it works;
    - a derivation sketch where relevant;
    - common misconceptions;
    - a "what changes if…" transfer question (e.g. "what if the quantum doubles?", "what if the cache becomes 2-way?");
    - an "explain it back" prompt with a model explanation.
  - **Apply**:
    - the procedure as numbered steps;
    - at least one worked example taken from the material, cited;
    - at least one fresh variant with a full solution;
    - "where marks are lost";
    - for **code**:
      - annotated reference code;
      - a trace exercise (given this input or register state, predict the output or final state);
      - a write-it-yourself task with a reference solution and tests;
    - for **simulations**:
      - the setup;
      - the expected output shape and why;
      - a parameter → effect table;
      - how to read the plot.
- **Mode rules.** Use paper evidence first:
  - Definitions, constants, names and standard results → recall.
  - Asked as explain, why, compare or justify, or underpins several apply nodes → understand.
  - Asked as compute, draw, design, write, trace or simulate → apply.
  - A topic can be split into several nodes with different modes. For example, "Banker's algorithm: what it guarantees" is understand; "Banker's algorithm: run it on a table" is apply.
- **Contradictions.** Where sources disagree (slides vs textbook vs key), add a watch-out fact that states both and says which one the paper follows.

### 6.4 Practice (`content/practice/`)

- **Practice papers in each exam's format.** For example, "Practice midsem in the style of 2024":
  - the same sections, mark split, question-type mix and time;
  - fresh questions, not copies, but the same patterns;
  - model answers laid out like a topper's answer sheet, with marks per step.
- **Topic drills**: 5–15 questions per high-weight node, in every type the paper uses for that node.
- MCQs only where the course's papers actually have MCQs.
- **Drill generators** (`generators/*.py`, written by you per course when the analysis shows a recurring, algorithmic numerical). Each one produces a random new instance plus a step-by-step solution, deterministic for a given seed. For CA and OS that means at least:
  - CPU scheduling: FCFS, SJF, SRTF, RR, priority. Gantt chart, waiting and turnaround times.
  - Page replacement: FIFO, LRU, OPT, clock. Fault counts and frame tables.
  - Address translation with paging or TLB, and multi-level page tables.
  - Banker's algorithm safety and resource requests.
  - Cache mapping: direct, set-associative. Tag/index/offset split and the hit/miss sequence for an address trace.
  - Pipeline timing: a cycle diagram with and without forwarding, stall counts, and CPI.
  - Number formats: two's complement and IEEE 754 encode/decode.
  - MIPS encoding: instruction ↔ machine code.

  The site embeds each generator's logic, ported to JS or precomputed as a bank of about 50 seeded instances, so I get unlimited "new question" clicks offline.
- **Viva question banks** per lab (when `labs_viva: true`): what the code does, why each design choice, what breaks if X changes, and related theory, with model answers.

### 6.5 Verification. Nothing reaches the site unchecked.
- **Every numerical**: a Python check script in `verify/` recomputes the answer.
- **Every code question**: run it with the matching runner and compare the output with the stated answer.
- **Generators**: property tests (e.g. scheduling totals add up, fault counts are monotone where theory says they should be).
- **Facts**: every fact cites a source, and a lint flags facts without one.
- **Official keys**: where a key exists, compare the generated solution with it; disagreements go into the report.
- **Failures**: anything that fails is fixed, or shown on the site with a visible "unverified" badge.

### 6.6 Build and 6.7 Cheatsheet: see sections 7 and 9.

---

## 7. The site (`index.html`)

Tabs:
1. **Plan**: the exam strategy page.
   - weightage by topic and exam (a simple bar chart);
   - the recurring patterns;
   - the mode breakdown: what to cram vs understand vs practise;
   - a suggested order of study weighted by marks.
2. **Map**: port the reference renderer (section 10).
   - Colour is the cluster.
   - A badge or shape marks the mode.
   - Dot size shows weight.
   - Filters for mode and weight.
   - Clicking a node opens a panel with its facts, links, worked example and questions.
3. **Learn**: understand and apply nodes as short lessons.
   - step-by-step reveals for procedures;
   - code with highlighting, plus trace exercises;
   - "what changes if…" cards.
4. **Practice**: practice papers, drills and generator "new question" buttons.
   - Answers are visible by default; a toggle hides them so I can test myself.
   - Self-marking per step against the model answer.
   - Progress is saved in localStorage, wrapped in try/catch.
5. **Past papers**: by year, every question tagged with its topics, type, marks and solution (official where it exists, otherwise generated and verified).
6. **Cram**: lookalike pairs, formulas, constants, "which is NOT" sets, sequences.
7. **Cheatsheet**:
   - a preview of the same content as the PDF;
   - a **"Make cheatsheet" button** that opens the print layout and calls `window.print()`, so I can make one from the browser;
   - a link to the prebuilt `cheatsheet.pdf` next to the HTML.

Global search across everything, accent-insensitive.

Requirements:
- **Single file and offline.** The test blocks the network and the site must still work fully.
- **Size**: under about 8 MB for a full course. Compress images and keep only figures that are referenced.
- **Rendering**: maths in KaTeX, which may be pre-rendered at build time. Code highlighted.
- **Layout**: light and dark themes; a phone layout with a 16px gutter and no horizontal scroll; keyboard navigation.
- **Speed**: fast with 300 nodes and 800 questions. Build the heavy views lazily.

---

## 8. Content format (source of truth)

Plain text, human-editable, diff-friendly, and validated with `file:line` errors. It must handle multi-line text, code blocks and LaTeX. The reference kit uses a line-based DSL (`reference/examples/*/map.txt`). You may keep and extend it, or switch to Markdown files per cluster. Document the final format in `FORMAT.md` with a full example.

My suggestion:

````markdown
---
cluster: sched
name: CPU scheduling
kicker: Unit 4
order: 4
---

## rr | Round robin | tier=1 mode=apply weight=high
- Each process runs for at most one quantum $q$, then goes to the back of the ready queue. {src: slides/07-sched.pdf#p14}
- Small $q$ → more context switches; $q \to \infty$ behaves like FCFS. {src: notes/ostep-07.pdf#p9}

### Steps
1. Order arrivals; put the processes that have arrived at t=0 in the queue.
2. ...

### Worked example {src: papers/2024-midsem.pdf#Q2}
...

### Variant {gen: scheduling seed=11}

### Where marks are lost
- Forgetting that a process arriving at the same time as a pre-emption joins the queue *before* the pre-empted one (state the convention you use).

### Links
- fcfs | RR with an infinite quantum
- context-switch | the overhead that a small q multiplies
````

---

## 9. Cheatsheet (`cheatsheet.pdf`)

- **Page budget** from `course.yaml`: default 8 pages, A4 portrait, 4 columns, 6 mm margins.
- **Type**: a condensed sans (the reference uses Anek Latin at a narrow width) with bold keywords and boxed formulas. No wasted whitespace and no orphan headings.
- **Auto-fit**:
  1. Render with Playwright to PDF.
  2. Binary-search the font size (8 pt down to 6 pt) and line height until it fits the page budget.
  3. If it still doesn't fit at 6 pt, drop the lowest-priority items (weight × mode priority) one at a time.
  4. List everything dropped in `report.md`.
- **Content priority**:
  1. formulas and key results;
  2. apply procedures as compressed steps;
  3. high-weight recall facts;
  4. lookalike and NOT tables;
  5. tiny worked examples for the top apply nodes;
  6. code idioms (e.g. MIPS calling convention, semaphore patterns);
  7. small diagrams only if they earn their space.

  Long explanations stay out.
- **Order**: by cluster, with headings.
- **QA**: extract text from the finished PDF and check that nothing is clipped or overflowing, the page count is within budget, and the minimum font size is at least 6 pt.

---

## 10. Reference kit (`reference/`): reuse it, don't rewrite it

The kit is a tested, working version of the map and question site, built for one humanities course (HSS F338). It already has:
- deterministic force layout clustered around a centre;
- label widths measured for Anek Latin, so labels end up with zero overlaps;
- semantic zoom (labels appear by visibility tier as you zoom), pan, pinch and wheel;
- search with suggestions, a side panel, an atlas, cram sheets, and question sets (answers visible, with a test-me toggle);
- light and dark themes, a phone layout, keyboard access.

Files:
- `mindmap_build.py`: parser, validator, layout (numpy), and JSON injection.
- `mindmap_template.html`: the whole front end (CSS and JS) in one file.
- `mindmap_check.py`: Playwright smoke test.
- `examples/photosynthesis/`: a tiny content set showing every directive.
- `examples/hss-f338/`: a real full course (153 ideas, 534 facts, 319 questions).
- `examples/hss-f338.html`: what the built page looks like.

Port the layout algorithm, label-width tables and map interactions as they are. Extend the rest.

Lessons already learned, so don't repeat these bugs:
- **Label clicks**:
  - Map labels must receive clicks; hulls, edges and titles must have `pointer-events: none`.
  - Call `setPointerCapture` only after a drag starts (more than 5 px). Calling it on `pointerdown` retargets the click and node selection breaks.
  - Detect a click on `pointerup` using the element recorded at `pointerdown`.
- **Readability at full-map zoom**:
  - Use semantic zoom with counter-scaled label size.
  - Show only the top two labels per cluster (about 17% of labels in total) when zoomed out.
  - Fade cross-cluster edges.
- **Ids and hashes**: never give an element an id equal to a route hash (`#map`). The browser will scroll to it on load.
- **SVG gradients**: in SVG gradient stops, put `var()` colours in the `style` attribute, not in presentation attributes.
- **Escapes**: don't write `\u`-style escapes in tool calls when generating files. Write the literal characters, or use `chr()` in Python.
- **Cluster titles**: place them outside their hull, offset by the title's own half-size along the direction from the centre.
- **Fonts in tests**: Google Fonts is often unreachable in sandboxes. Bundle fonts, and in tests serve local font files so screenshots match reality.
- **Answer positions**: balance correct-answer positions across a–d when shuffling MCQs.

---

## 11. Milestones

1. **M1 Skeleton**:
   - CLI scaffold, `ingest` for PDF, PPTX, DOCX and code, plus the manifest and caching.
   - Port the reference renderer behind `build` so existing content files still build.
   - Tests.
2. **M2 Papers**: paper analysis with scanned-paper support, `papers.json`, the report, and the Plan tab.
   - **Stop and show me** the report for one real course before going further.
3. **M3 Content**: the new content model with modes, weights and provenance, `validate`, the Learn tab, and map badges.
4. **M4 Practice**: practice papers in exam format, drills, viva banks, generators for the CA and OS list in 6.4, runners, `verify`, and "unverified" badges.
5. **M5 Cheatsheet**: print layout, auto-fit PDF, the in-site button, and the PDF QA.
6. **M6 Polish**:
   - offline inlining and size budget;
   - search, performance and phone pass;
   - `README.md` and `FORMAT.md`;
   - the `/study` command and incremental re-runs that preserve my edits.

---

## 12. Acceptance criteria

1. **Paper coverage**: every past-paper question maps to at least one node. Unmapped questions are listed in the report and must be zero or explained.
2. **Source coverage**: sample 30 content-bearing sentences from the slides; at least 90% must be findable (fuzzy match) in the content. The report shows the score and the misses.
3. **Content completeness**:
   - every fact has provenance;
   - every apply node has a worked example, a variant and a "where marks are lost" section;
   - every numerical and code answer is verified or visibly flagged.
4. **Format match**: each practice paper matches its source exam's total marks, sections and question-type mix.
5. **Cheatsheet**: at most N pages, minimum font at least 6 pt, no clipped text, dropped items listed.
6. **Site checks**:
   - `studymap check` passes with no console errors;
   - screenshots on desktop and phone, light and dark;
   - the site works with the network blocked.
7. **Determinism**: the same content gives a byte-identical build.
8. **Incremental re-runs**: re-running after adding one file reprocesses only what depends on it and never overwrites my edits.
9. **Real-course test**: tested end to end on at least two real courses with different shapes: one technical (OS or CA) and the HSS example.

---

## 13. When to ask me

- After M2, with the paper analysis report.
- If a course's exam format is unclear and there are no papers.
- Before adding any dependency that needs a licence, a paid service or the network at runtime.

Otherwise make sensible decisions, note them in `DECISIONS.md`, and keep going.
