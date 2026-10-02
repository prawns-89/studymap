# Studymap

Studymap turns a folder of course material into an offline study site aimed at the course's exam format. [BRIEF.md](BRIEF.md) is the specification and [DECISIONS.md](DECISIONS.md) records the choices made so far. The full README arrives in milestone M6.

## Setup

```sh
pipx install uv          # if uv isn't installed yet
uv sync                  # creates .venv with every dependency
```

`studymap check` needs Chromium. It uses Playwright's bundled browser if it's installed (`uv run playwright install chromium`), otherwise the system Google Chrome.

## Commands

| Command | What it does |
|---|---|
| `uv run studymap ingest COURSE` | Extracts text, images and code into `COURSE/_studymap/corpus/`, cached by file hash. Options: `-j N` worker processes, `--force` re-extract everything, `--rehash` re-hash every file, `-q` summary only. |
| `uv run studymap validate COURSE` | Checks the paper analysis and the content files, and reports problems as `file:line: message`. |
| `uv run studymap report COURSE` | From the paper analysis, writes `COURSE/_studymap/report.md` and `analysis/weightage.json`. |
| `uv run studymap schema topics\|papers` | Prints the JSON Schema of an analysis file. |
| `uv run studymap build COURSE` | Writes `COURSE/_studymap/index.html`, with the Plan tab when there is a paper analysis and the map when there is content. It also refreshes `report.md`. `--content DIR` and `-o FILE` override the defaults. |
| `uv run studymap check COURSE` | Opens the built site in headless Chromium with the network blocked, tests it at four viewports, and saves screenshots to `COURSE/_studymap/check/`. |

`verify`, `cheatsheet` and `serve` exist, but each one only prints the milestone that delivers it (M4, M5 and M6).

The paper analysis is written by Claude Code. In this repo, run `/study-papers <course-folder>`; its instructions are in `.claude/commands/study-papers.md`.

The reference examples build directly:

```sh
uv run studymap build studymap-starter/reference/examples/hss-f338 -o /tmp/hss.html
```

## Tests

```sh
uv run pytest                    # everything, including real-browser checks
uv run pytest -m "not browser"   # skip the browser tests
```
