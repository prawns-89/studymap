# Decisions

Choices the brief left open (BRIEF section 13), with the reason for each. Newest milestone first.

## Open-book courses (added with CS F301 POPL)

- **`cheatsheet.allowed: false` now does something.** It was parsed but never read. POPL's exams are open book and open laptop, so there is no sheet to fit: `studymap cheatsheet` declines with a reason (`--anyway` overrides), and the site leaves out the Cheat sheet tab. For such a course the site itself is the exam artefact.
- **Ingest reads the paradigm languages.** A languages course compares paradigms in their own languages, and the three POPL `.lisp` files were being skipped as unsupported. Lisp, Scheme, Clojure, ML, F#, Erlang, Elixir, Scala, Ruby, Swift, C#, Objective-C, Ada, Fortran, Pascal, Smalltalk and Prolog extensions now map to their highlight.js names.
- **A Lessons tab for long-form teaching.** `COURSE/lessons/*.md` (README first, then by file name) are rendered at build time into the same offline `index.html`: a lesson list with each lesson's sections, previous/next links, and routes like `#docs/03-scope-rules/shadowing`. The Learn tab's node format is built for short exam facts; an open-book course needs readable chapters with worked programs, so these are plain Markdown, rendered by `render/docs.py` (headings with anchors, nested lists, quotes, tables, `<details>` answer blocks, links between lessons). The renderer is a fuller subset than `text.py`'s, which stays for question text. Heading ids are prefixed `d-` so they can't clash with the page's own ids. Links from a lesson to course files (`../papers/2024-midsem.pdf`, `../slides/...pdf#page=79`, `../popl_tb.pdf#page=445`) are re-aimed from the lessons folder to wherever the page is written, so they open the real PDFs locally at the right page; a link to a file that doesn't exist is reported by `build` and shown unlinked. `check` opens the tab, follows a next link, opens an answer and tests for horizontal scroll.
- **`check` scrolls a Plan bar into view before hovering it.** Playwright's `hover()` on a bar below the fold scrolls and hovers in one step, and the page's own scroll handler, which hides the tooltip so it cannot drift away from its row, then hid it. The page was right and the test was wrong; OS passed only because its first bar sits above the fold.

## Planned additions (agreed after M1)

- **Optional 3D map view (three.js).** The 2D map stays the default, as the brief requires. An "Explore in 3D" toggle on the Map tab shows the same clusters, colours and click-to-open panel in 3D. three.js (MIT) is bundled into the page, adding about 0.7 MB toward the 8 MB budget, so it works offline and needs no CDN. It is scheduled for M6 unless it's moved earlier.

## M3 and M5: content, the Learn tab and the cheat sheet

### Content format (documented in `FORMAT.md`)

- **Markdown per cluster**, not the reference kit's line DSL. The brief allowed either. Markdown won because the new model needs multi-line bodies (steps, worked solutions, code, tables) that the one-fact-per-line DSL cannot hold, and because you can edit it in any editor with highlighting. The reference DSL still builds (`map.txt` content keeps working), so nothing was lost.
- **Node ids are topic ids.** A node called `mlfq` inherits that topic's mode, weight and past questions from the analysis automatically. A topic can be split into several nodes with `topic=<id>`.
- **Mode and weight are inherited, not written by hand.** `weight` comes from `weightage.json`; `mode` comes from how the papers ask. Either can be overridden per node. A node whose topic was never asked must state its own mode, and `validate` says so.
- **Sections are a fixed vocabulary** (`Steps`, `Worked example`, `Variant`, `Where marks are lost`, `Core idea`, `Why it works`, `Misconceptions`, `What changes if`, `Explain it back`, `Formulas`, `Lookalikes`, `Code`, `Trace`, `Write it`, `Links`), so the renderer and the cheat sheet know what each block is. An unknown heading is an error, not silently kept.
- **Every fact cites a source** with `{src: ref}`, and the ref is checked against the ingested corpus: a page that does not exist is an error. Facts without a source are a warning (the brief's lint).
- **Apply nodes** must have a worked example, a variant and a "where marks are lost"; missing ones are warnings, listed per node.
- **Validation** reports `file:line: message` for every problem, including the layout-breaking case where a cluster's only node is the map centre.

### Learn tab and map badges

- **Shape is mode, size is weight, colour is cluster:** squares for practise, circles for understand, diamonds for cram. Shape rather than colour because colour is already spent on clusters, and shape survives colour blindness.
- **Map filters** dim what does not match instead of removing it, so the layout never moves under you.
- **Learn** builds one lesson per node on first visit: facts with their sources on hover, then the sections. Steps reveal one at a time; worked solutions, model answers and "what changes if" answers stay hidden until opened. Past paper questions on the node's topic are attached automatically, with the key's answer.
- **The Atlas tab is hidden** when Markdown content is present: Learn supersedes it.

### Cheat sheet

Rebuilt after you showed me your MATH F432 sheet as the standard. The first version was a flat list of facts; this one copies that sheet's structure, because the structure is what makes it usable in an exam.

- **Labelled blocks, not a list.** Every piece is tagged with what it is for: `KEY FORMULAS`, `HOW TO SOLVE`, `DIAGRAM`, `PAST PAPER`, `WORKED EXAMPLE`, `TRAP`, `LOOKALIKES`, `NOT`, `WHAT CHANGES IF`, `WHY IT WORKS`, `DERIVATION`, `EXPLAIN IT BACK`. A legend at the top says what each one means.
- **`WHAT TO EXPECT IN THE EXAM`** opens every cluster and is generated, not written: the real past questions on that cluster with their marks and type, plus the recurring patterns that cite them, each with one line on why that kind of knowing is needed.
- **Front and back matter** come from the optional `content/sheet.md`: `How to think` (the decision procedure), `Master table` (question wording → method → formula), `Sanity checks`, `Notation decoder`. They are authored per course, because choosing a method is judgement, not arithmetic.
- **Contents with real page numbers.** Rendered twice: the first pass is measured to find which page each section starts on, the second prints those numbers. Sections are located by their white-on-black heading spans, so the contents listing can't be mistaken for the headings it lists.
- **Running header** on every page (course and `page N of M`), via Chromium's header template. Per-page "on this page: X → Y" like your MATH sheet is not possible with Chrome's print pipeline, which only exposes page numbers; the contents list covers the same need.
- **Diagrams.** A new `### Diagram` section holds ASCII pictures (Gantt charts, address splits, process trees, buddy splits). They cannot wrap, so each is auto-sized to its longest line, and one too wide for a 47 mm column is promoted to a full-width band after its cluster so it stays legible.
- **`CONCEPT Q` blocks.** A `### Conceptual questions` section (`- question :: answer`) carries the short conceptual probes this course rewards. It scores just below HOW TO SOLVE, so it survives a squeeze, and renders as answer-hiding cards in the Learn tab.
- **Repeated sections render.** A node may now have two `Conceptual questions` or two `Worked example` sections; the sheet renders each in file order. Before, only the first was used and the rest were silently dropped, which lost a whole authoring pass before it was noticed.
- **The 6 pt floor is a setting, not a rule.** The brief's acceptance criterion says a minimum font of 6 pt. You asked for 4 pt if it buys depth, so `MIN_PT` is now 4.0, the default floor is 4.5, and `--min-pt` sets it per run. The OS sheet currently sits at 5.4 pt with nothing dropped. This is a deliberate, requested deviation from section 12.5.
- **Fitting is legibility-aware.** The brief says search 8 pt down to 6 pt, then drop. The search now also grows past 8 pt when the budget has room (4-up printing halves the apparent size), and `--min-pt` sets the floor: at the floor, blocks are dropped by priority rather than shrunk further. The default floor is 6 pt, matching your own 8-page 6.2 pt sheet, so nothing is dropped.
- **QA distinguishes body text from labels.** The modal span size is the body text and must meet the floor; inline labels may be smaller but never below 4.4 pt. Two bugs this caught, both real: `white-space: pre` on code made the page wider than A4, so Chrome silently shrank everything to two-thirds size; and `break-inside: avoid` on a block taller than a column made Chrome drop the overflow. The clipping check compares letters only, because PDF extraction reorders list markers.

- **One source, two outputs.** The same HTML document is embedded in the site's Cheat sheet tab (with a print button) and rendered to `cheatsheet.pdf` by headless Chromium. Before `studymap cheatsheet` runs, the tab shows a 7.5 pt draft.
- **Item priority** follows the brief: formulas, compressed steps, high-weight facts, lookalikes, pitfalls, short worked examples, short code, then the remaining facts. Each item is scored by its kind times its node's weight, so low-weight material is dropped first.
- **`cheatsheet-4up.pdf`** is generated beside it: 4 pages per side, so an 8-page budget lands on one A4 sheet, both sides, which is what the OS and CA exams allow.
- **Typography**: a condensed sans (DejaVu Sans Condensed, Liberation Sans Narrow, Nimbus Sans Narrow), 4 columns, 6 mm margins, boxed formulas, black cluster bars, `break-inside: avoid` on items and `break-after: avoid` on headings so nothing is orphaned.
- **QA on the finished PDF**: page count within budget, smallest font at least 6 pt, and every kept item's rendered text found in the PDF's extracted text (the clipping check). Problems are printed and listed in `report.md`.

## M2: papers

### Analysis files

- **Who writes what.** The thinking stage (`/study-papers`) writes `analysis/topics.json` and `analysis/papers.json`. The CLI derives `analysis/weightage.json` and `report.md` from them and never changes them. `studymap schema topics|papers` prints the JSON Schema, which is also the interface for a later `--api` mode.
- **Why `topics.json`.** The brief lists only `papers.json` and `weightage.json`, but questions need topic ids before content nodes exist (M3). M3 turns each topic into one or more nodes and keeps the ids. Topics can carry slide and lab page ranges as sources, so slide emphasis and coverage can be computed.
- **Granularity.** One question is the smallest part that carries its own marks, so 2025 Q1c becomes (i), (ii) and (iii).
- **Validation.** `validate` checks the analysis against `course.yaml` and the corpus, and reports every problem as `file:line`:
  - every cited page, slide or line range must exist;
  - an exam paper's marks must add up to its total (unless `marks_note` explains a choice);
  - repeats must point to another paper;
  - a question with no topic needs an `unmapped_reason`;
  - a reduced `relevance` needs a reason.

  Mode and type mismatches against the brief's rules are warnings.
- **Scanned papers.** Claude reads them from the page renders, and `transcribed_from_image` marks every question from a scan as unverified in the report. There is no OCR, because tesseract isn't installed; the 2024 OS phone scan read cleanly anyway.

### Weightage

- **Paper share.** A topic's share of a paper is the marks it got divided by the paper's total. A question's marks are split evenly between its topics. Papers are averaged, weighted by their `relevance` (0–1, with a reason). The 2024 OS paper counts at 0.5: it was set before the current offering, in a different format, and asks three questions on material that isn't in the current slides.
- **Slides as a prior.** The paper share is blended with slide emphasis (the topic's share of covered, non-duplicate slides), the slides counting as one more paper: `(R × papers + slides) / (R + 1)`, where R is the summed relevance. With no papers this becomes slides alone, the brief's fallback, and the report and Plan tab say so. With few papers, topics that were taught but not yet asked keep some weight.
- **Sample questions** have no marks. They don't move shares, but they count toward each topic's mode and appear wherever its questions are listed.
- **Weight classes.** Points are a topic's share × its exam's weight in the grade, summed over exams. Topics making up the first 50% of points are high, the next 30% med, and the rest low.
- **Mode per topic.** The dominant mode among its questions, by marks × relevance. Ties go to apply, then understand, because practice takes longest.
- **Study order.** It is computed per exam, not course-wide. The course-wide order was dominated by the compre, which has no papers and so runs on slides alone, and the next exam is what matters. Each exam's list runs until 80% of its share; the rest is listed after it.

### Report and Plan tab

- **`report.md`** is regenerated on every `report` and `build`, and written only when it changes. It has these sections:
  - at a glance, and "read this first" notes;
  - patterns;
  - weightage per exam;
  - what to study per exam;
  - weights for the whole course;
  - repeats;
  - papers analysed;
  - coverage;
  - unverified;
  - how the numbers are made.
- **Plan tab chart.** A ranked bar list in one hue. Per the dataviz rules, that's one series with no value ramp and no per-cluster bar colours; cluster identity comes from a swatch beside the label. Every row also shows its value, so the tooltip (on hover, focus or tap) only adds the breakdown. Bars are 14 px with a 4 px rounded end.
- **Bar colour.** `--bar` is `#3A44AE` in light mode and `#7B84E6` in dark mode, both validated against their surfaces with the dataviz validator. The site's dark accent `#A7AEFF` failed the dark lightness band.
- **Mode split.** Shown as stat tiles (practise, understand, memorise), not a chart.
- **Optional map.** A course builds as soon as its papers are analysed (Plan tab only), and the map joins once there is content. `build` also refreshes `report.md`.
- **Past questions.** The Plan's study order opens each topic to its past questions with the key's answers. The full Past papers tab, with generated and verified solutions, comes in M4.
- **`check`** now exercises the Plan tab on every viewport:
  - bars render;
  - a hover, a tap on phones, and keyboard focus show the tooltip;
  - opening a topic shows its questions;
  - the exam switch redraws the page.

### Ingest additions

- **`corpus/outline.md`.** Every source on a line or two: titles per page with near-duplicates left out, `[img]` marks on visual pages, papers with their keys, and labs by language. The analysis stage plans from it instead of loading every slide (10 KB for the whole OS course).

### course.yaml, without changing the contract

- **OS syllabus.** The midsem date, cheat-sheet rule and calculator go in the midsem `format`. The syllabus goes in `notes_for_claude`, and the Pintos assignments are excluded with `ignore`. The cheat-sheet budget stays at **8 pages** even though one A4 sheet is allowed: you print 8 pages 4-up onto one sheet, both sides.
- **Proposed fields.** Optional per-exam `date` and `covers` (decks or topics) would let the Plan count down to the exam and scope the slide prior to its syllabus. That changes the folder contract, so it needs your approval first.

## M1: skeleton

### Project and tooling

- **Layout.** The package lives in `src/studymap/`, built with hatchling and managed by uv. uv wasn't installed, so it was installed with `pipx install uv`. uv picked its managed CPython 3.14 for the venv; the project needs `>=3.11`.
- **Dependencies.** Exactly the brief's stack, plus PyYAML for `course.yaml`. Nothing needs the network or a paid service at runtime.
- **Licence note.** PyMuPDF is AGPL-3.0. That's fine for a local personal tool. If Studymap is ever offered as a service or a closed product, revisit it: pypdfium2 (Apache/BSD) for rendering plus pdfplumber (MIT) for text would replace it.
- **Browser.** `check` uses Playwright's bundled Chromium when it's installed, otherwise the system Google Chrome (`channel="chrome"`). This machine has Chrome 148, so the 170 MB bundled browser wasn't downloaded. `uv run playwright install chromium` adds it.

### Ingest

- **Corpus layout** under `_studymap/corpus/`:

  | Path | Contents |
  |---|---|
  | `index.json` | Every source; papers and their keys; skipped files with reasons; warnings |
  | `sources/<sid>.json` | The full extraction record for one source |
  | `text/<sid>.md` | A readable view for Claude, one per source, with `<!-- src: … -->` provenance comments and image links |
  | `img/<sid>/` | JPEG renders and extracted pictures |
  | `dedupe.json` | Near-duplicate units and the unit each one repeats |
  | `summaries/` | Empty; the `/study` command writes per-source summaries here |

- **Provenance references:**

  | Source | Reference |
  |---|---|
  | PDF page | `file.pdf#p14` |
  | PPTX slide | `deck.pptx#s3` |
  | DOCX heading section | `notes.docx#sec2` |
  | Text and code lines | `notes.md#L10-42`, `main.c#L1-120` |
  | Notebook cell | `nb.ipynb#cell4` |
  | Image file | the plain path |

  Paper question references (`#Q2`) arrive with paper analysis in M2.
- **Source ids.** A source id (sid) is a slug of the course-relative path. A 6-character hash is appended only when two paths produce the same slug.
- **PDF text order.** Text comes out in content-stream order, which keeps textbook columns intact. Sorting by position interleaves two-column pages.
  - A line drawn twice at the same spot (a shadow or outline effect) is kept once.
  - Running headers, footers and page numbers are removed when the same text (digits ignored) sits at the same position on at least half the pages of a document of 4 or more pages. The position key means numbers inside tables survive.
- **Page renders.** Renders are JPEG at quality 85, with the long side 1400 px (1700 px for papers and image-only pages). A page is rendered when it is:
  - a paper page, including keys (every page);
  - "low-text": fewer than 100 characters of text;
  - "image-only": fewer than 25 characters and at least 50% covered by images (scans, screenshot slides);
  - "figure": non-template images cover at least 10% of it, or its vector drawings exceed `max(25, 2 × median + 10)`.

  Template decoration means the same image digest on at least half the pages. JPEG is about 8× smaller than PNG for slides (200 KB vs 1.5 MB). Only Claude reads these images; the site picks and recompresses its own figures later.
- **No OCR in M1.** tesseract isn't installed. Image-only pages are rendered for Claude to read visually, which works well on the phone-photographed 2024 OS midsem. M2 can use tesseract when it is present.
- **PPTX.** Slides can't be rendered without LibreOffice, which isn't installed. Ingest extracts:
  - text, with bullet levels;
  - tables, as Markdown;
  - speaker notes;
  - embedded pictures, skipping template pictures (the same image on at least half the slides).

  A slide with little text and no picture triggers a warning that suggests exporting the deck to PDF.
- **DOCX.** Each heading starts a new unit. Without headings, the text is chunked at about 4000 characters. Lists, tables and images are kept.
- **Code.** Copied verbatim (only CRLF becomes LF) and tagged with its highlight.js language name. `.s`, `.asm` and `.S` files are sniffed as `mipsasm` or `x86asm`. Text and code files over 1 MB are skipped as generated.
- **Unmapped glyphs.** Glyphs with no Unicode mapping come out as control bytes (a NUL for the `←` in the CA decks). They become U+FFFD `�`, so the text views stay plain text; the page render shows the real symbol.
- **Images with transparency** are rendered onto white; otherwise draw.io diagrams turn black.
- **Skipped files** are listed in `index.json` with a reason: archives (not unpacked; unpack them into the folder to include them), legacy `.ppt` and `.doc`, and unsupported types.
- **Folders.**
  - Never entered: hidden folders, `_studymap`, `__pycache__`, `node_modules` and `__MACOSX`.
  - Folder kinds match case-insensitively (`Slides/` counts as `slides/`).
  - Symlinked folders are followed, with loop protection.
- **Near-duplicates.** A unit is a duplicate when at least 90% of its word 3-grams appear in a larger unit. This catches incremental slide builds and recap slides repeated across decks.
  - The most complete copy is kept.
  - Duplicates stay in `sources/*.json` but are left out of `text/*.md`.
  - Only slides, notes and extra are deduplicated. Papers never are (a repeated question is signal), and neither is code.
- **Papers.**
  - A paper's key has the paper's name plus one of these suffixes: `-key`, `-keys`, `-solution`, `-solutions`, `-sol`, `-soln`, `-answer`, `-answers`, `-ans`.
  - An answer key with no matching paper is a warning.
  - Names outside the `YYYY-exam` pattern (such as `sample-questions.pdf`, which the brief lists) are accepted with the year unknown.
- **Caching and resuming.**
  - A source is re-extracted when its sha256, its extractor version (the `EXTRACTOR` table) or its sid changes. If size and mtime are unchanged the stored hash is reused; `--rehash` forces hashing.
  - PDFs, Office files and images are extracted in up to 4 worker processes. Text and code run inline.
  - The cross-source views are recomputed on every run but written only when they change.
  - A broken file fails on its own, is reported, and is retried on the next run.
  - The manifest is saved every 2 seconds and on interrupt, so a re-run after Ctrl-C resumes where it stopped.

### Build

- **Faithful port.** The layout code and label-width tables in `layout.py` are copied verbatim from the reference. The reference `main()` is split into functions, with the data assembly unchanged. A test builds both reference examples twice, once with the reference script and once with `studymap build`, and checks that the injected data is identical.
- **Determinism.** Builds are byte-identical across runs and Python hash seeds (tested). They are not identical across numpy versions or CPUs: the force layout is chaotic, so the shipped `examples/hss-f338.html`, built on another machine, has node positions up to about 300 units away from a rebuild here. The plan for M6 is to cache the layout in `_studymap/`, keyed by a hash of the content's graph, so a rebuild on another machine reuses the positions.
- **Full HTML document.** The template now has a doctype, `<meta charset>` and a viewport tag, because `index.html` is opened straight from disk rather than wrapped by a publisher.
- **Content format.** M1 keeps the reference line DSL so the existing examples still build. M3 decides the new format and documents it in `FORMAT.md`.
  - Parsing semantics are unchanged.
  - Errors are collected as `file:line: message` instead of stopping at the first one.
  - Malformed files that crashed the reference, such as a `Q` line before any `@node`, are now ordinary errors.
  - New checks: tier is 1–3, cluster colour is 0–11, and tag, sheet and set styles are known values.
- **Where build looks.** `build` reads `<course>/_studymap/content/`, or a folder that holds `map.txt` directly (the reference examples). `--content` and `--out` override both.
- **Fonts.** Google Fonts (Anek Latin, Newsreader) is still linked. Offline, the page falls back to system fonts, which are wider, so labels can overlap. Subsetting and inlining the fonts is M6 work, as planned in the brief. Until then `check` reports the blocked font requests as a warning.

### Check

- **Viewports.** Four: desktop and phone, each in light and dark.
- **Network.** Every request except file, data and blob URLs is blocked.
- **Failures.** `check` fails on any of these:
  - a page error or console error;
  - a map whose node count differs from the data;
  - a node click, or Enter on a focused node, that shows no facts;
  - a tab that doesn't open its view;
  - horizontal scrolling.
- **Screenshots** go to `_studymap/check/`.

### Real-course test folders

`courses/` holds contract-shaped course folders built from symlinks, so the originals in `~/Downloads` are untouched.

- **CS-F372-OS**:
  - Slides link to `~/Downloads/OS/Slide`.
  - Papers are renamed to the contract: `MIdsem-24251` → `2024-midsem` (+ key), `Midsem-2526` → `2025-midsem` (+ key), `midsem-sample-questions` → `sample-questions`. `Midsem-24252` was empty.
  - Eight lab folders are linked. The instructors' Pintos base code is excluded with `ignore` in `course.yaml`.
- **CS-F342-CA**: labs link to `~/Downloads/CompArch/Labs` and slides to `~/Downloads/CompArch/Slides`. The 5 decks added to that folder during M1 were picked up incrementally: 5 sources extracted, 131 cached.
- **HSS-F338**: the reference example's content, copied into `_studymap/content/`, to exercise the build → check path.

`courses/` and every `_studymap/` folder are git-ignored. The corpus holds extracted course material, and the CA lab files carry a BITS IPR notice against public posting.
