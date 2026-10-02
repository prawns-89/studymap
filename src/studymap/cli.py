"""studymap: the deterministic half of Studymap (BRIEF section 4A). No AI calls happen here."""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from . import __version__
from .course import OUT_DIR, CourseError, display_path, load_config

LATER = {
    "verify": ("run every numerical check script and code runner", "M4"),
    "cheatsheet": ("render cheatsheet.pdf with auto-fit", "M5"),
    "serve": ("local server with live reload while editing content", "M6"),
}


def _course(p: Path) -> Path:
    if not p.is_dir():
        raise SystemExit(f"studymap: {p}: not a folder")
    return p


def cmd_ingest(a) -> int:
    from .ingest import ingest
    course = _course(a.course)
    log = (lambda s: None) if a.quiet else print
    r = ingest(course, jobs=a.jobs, force=a.force, rehash=a.rehash, log=log)
    st = r.stats
    kinds = " · ".join(f"{n} {k}" for k, n in st["by_kind"].items()) or "nothing"
    print(f"sources: {kinds}  ({st['units']} units)")
    print(f"this run: {len(r.extracted)} extracted · {len(r.cached)} cached · {len(r.removed)} removed"
          + (f" · {len(r.failed)} FAILED" if r.failed else "") + f" · {r.views_written} views written · {r.seconds:.1f}s")
    imgs = st["images"]
    if imgs:
        print("images: " + " · ".join(f"{n} {k}" for k, n in imgs.items())
              + f"  ·  image-only pages {st['image_only']} · low-text units {st['low_text']} · near-duplicates {st['duplicates']}")
    if r.papers:
        shown = []
        for p in r.papers:
            if p["is_key"]:
                continue
            name = Path(p["path"]).name
            shown.append(name + (" (+key)" if p["key"] else ""))
        print("papers: " + " · ".join(shown))
    if r.skipped:
        reasons = Counter(reason for _, reason in r.skipped)
        print(f"skipped {len(r.skipped)}: " + "; ".join(f"{reason} ×{n}" for reason, n in reasons.most_common(6))
              + (" …" if len(reasons) > 6 else "") + "  (full list in corpus/index.json)")
    for rel, err in r.failed:
        print(f"FAILED {rel}: {err}")
    for w in r.warnings[:12]:
        print(f"warning: {w}")
    if len(r.warnings) > 12:
        print(f"  … {len(r.warnings) - 12} more warnings in corpus/index.json")
    print(f"corpus: {display_path(r.corpus)}")
    return 1 if r.failed else 0


def _print_analysis(an) -> None:
    for i in an.errors:
        print(i)
    for i in an.warnings:
        print(f"warning: {i}")
    if not an.errors and an.topics is not None:
        p = an.papers
        print(f"{display_path(an.dir)}: ok · {len(an.topics.clusters)} clusters · {len(an.topics.topics)} topics"
              + (f" · {len(p.papers)} papers · {len(p.questions)} questions · {len(p.patterns)} patterns" if p else " · no papers.json"))


def cmd_validate(a) -> int:
    from .analysis import load_analysis
    from .render import ContentError, load_valid, resolve_content
    course = _course(a.course)
    an = load_analysis(course, load_config(course))
    errors = 0
    if an.present:
        _print_analysis(an)
        errors += len(an.errors)
    try:
        cdir = resolve_content(course, a.content)
    except FileNotFoundError:
        if not an.present:
            raise FileNotFoundError(f"{a.course}: nothing to validate yet (no analysis/ and no content/)") from None
        cdir = None
    if cdir is not None:
        try:
            c = load_valid(course, a.content)
            print(f"{display_path(cdir)}: ok · {len(c.clusters)} clusters · {len(c.nodes)} nodes · "
                  f"{sum(len(n['facts']) for n in c.nodes)} facts · {len(c.sheets)} sheets · "
                  f"{sum(len(q) for _, q in c.sets)} questions")
        except ContentError as e:
            print("\n".join(map(str, e.issues)))
            errors += len(e.issues)
    if errors:
        print(f"{errors} problem{'s' if errors != 1 else ''}")
    return 1 if errors else 0


def cmd_report(a) -> int:
    from .analysis.report import pct
    from .analysis.stage import run_report
    course = _course(a.course)
    r = run_report(course, load_config(course))
    if not r.analysis.present:
        print(f"studymap: no analysis yet: expected {display_path(course / OUT_DIR / 'analysis' / 'topics.json')} "
              "(the /study-papers command writes it)", file=sys.stderr)
        return 1
    _print_analysis(r.analysis)
    if r.weightage is None:
        return 1
    for e in r.weightage["exams"]:
        top = [t for t in e["topics"] if t["share"] > 0][:5]
        names = {t["id"]: t["label"] for t in r.weightage["topics"]}
        print(f"{e['name']} ({e['basis']}): " + " · ".join(f"{names[t['id']]} {pct(t['share'])}" for t in top))
    print(f"wrote {display_path(r.report)} and analysis/weightage.json ({r.written} changed)")
    return 0


def cmd_schema(a) -> int:
    import json
    from .analysis.models import PapersFile, TopicsFile
    print(json.dumps({"topics": TopicsFile, "papers": PapersFile}[a.which].model_json_schema(), indent=1))
    return 0


def cmd_build(a) -> int:
    from .render import ContentError, build
    course = _course(a.course)
    try:
        r = build(course, a.content, a.out)
    except ContentError as e:
        print("Fix these and run again:\n  " + "\n  ".join(map(str, e.issues)))
        return 1
    s = r.stats
    if s:
        print(f"nodes {s.nodes} · links {s.edges} · facts {s.facts} · sheets {s.sheets} · questions {s.questions} · "
              f"label overlaps left {s.overlaps}")
        for name, pos in s.answer_positions:
            print(f"  {name}: answer positions {pos}")
    else:
        print("no map content yet: the page has the Plan tab only")
    if r.plan:
        print(f"plan: {len(r.plan['exams'])} exams · {len(r.plan['topics'])} topics · report.md refreshed")
    print(f"wrote {display_path(r.out)} ({r.size / 1024:.0f} KB, sha256 {r.sha256[:12]})")
    return 0


def cmd_check(a) -> int:
    from .check import check
    course = _course(a.course)
    html = a.html or course / OUT_DIR / "index.html"
    if not html.exists():
        raise SystemExit(f"studymap: {html} doesn't exist: run `studymap build {a.course}` first")
    shots = a.shots or course / OUT_DIR / "check"
    r = check(html, shots)
    print(f"browser: {r.browser} · network blocked · {len(r.shots)} screenshots in {display_path(shots)}")
    for n in r.notes:
        print(n)
    for w in r.warnings:
        print(f"warning: {w}")
    if r.ok:
        print("check passed: no page or console errors, map and panel work, tabs open, no horizontal scroll")
        return 0
    print("check FAILED:\n  " + "\n  ".join(r.failures))
    return 1


def cmd_later(a) -> int:
    what, ms = LATER[a.cmd]
    print(f"studymap {a.cmd}: {what}. Not built yet: it arrives in milestone {ms}.")
    return 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="studymap", description="Turn a course folder into an exam-focused study site.")
    ap.add_argument("--version", action="version", version=f"studymap {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="COMMAND")

    p = sub.add_parser("ingest", help="extract text, images and code into _studymap/corpus/ (cached by file hash)")
    p.add_argument("course", type=Path)
    p.add_argument("-j", "--jobs", type=int, default=0, help="worker processes for PDFs and Office files (default: up to 4)")
    p.add_argument("--force", action="store_true", help="re-extract everything, ignoring the cache")
    p.add_argument("--rehash", action="store_true", help="re-hash every file even if its size and mtime are unchanged")
    p.add_argument("-q", "--quiet", action="store_true", help="only print the summary")
    p.set_defaults(fn=cmd_ingest)

    p = sub.add_parser("validate", help="check the paper analysis and the content files; errors as file:line")
    p.add_argument("course", type=Path)
    p.add_argument("--content", type=Path, help="content folder (default: <course>/_studymap/content)")
    p.set_defaults(fn=cmd_validate)

    p = sub.add_parser("report", help="validate the paper analysis and write report.md and analysis/weightage.json")
    p.add_argument("course", type=Path)
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("schema", help="print the JSON Schema of analysis/topics.json or analysis/papers.json")
    p.add_argument("which", choices=["topics", "papers"])
    p.set_defaults(fn=cmd_schema)

    p = sub.add_parser("build", help="render index.html")
    p.add_argument("course", type=Path)
    p.add_argument("--content", type=Path, help="content folder (default: <course>/_studymap/content)")
    p.add_argument("-o", "--out", type=Path, help="output file (default: <course>/_studymap/index.html)")
    p.set_defaults(fn=cmd_build)

    p = sub.add_parser("check", help="headless browser test of the built site, offline, with screenshots")
    p.add_argument("course", type=Path)
    p.add_argument("--html", type=Path, help="page to test (default: <course>/_studymap/index.html)")
    p.add_argument("--shots", type=Path, help="screenshot folder (default: <course>/_studymap/check)")
    p.set_defaults(fn=cmd_check)

    for name, (what, ms) in LATER.items():
        p = sub.add_parser(name, help=f"{what} [{ms}]")
        p.add_argument("course", type=Path)
        p.set_defaults(fn=cmd_later)

    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except (CourseError, FileNotFoundError) as e:
        print(f"studymap: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
