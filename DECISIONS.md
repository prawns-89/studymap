# Decisions

Choices the brief left open (BRIEF section 13), with the reason for each. Newest milestone first.

## Planned additions (agreed after M1)

- **Optional 3D map view (three.js).** The 2D map stays the default, as the brief requires. An "Explore in 3D" toggle on the Map tab shows the same clusters, colours and click-to-open panel in 3D. three.js (MIT) is bundled into the page, adding about 0.7 MB toward the 8 MB budget, so it works offline and needs no CDN. It is scheduled for M6 unless it's moved earlier.

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
