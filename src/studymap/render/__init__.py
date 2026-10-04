"""Find a course's content, validate it, and build index.html."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from ..course import OUT_DIR, display_path, load_config
from ..issues import Issue
from ..manifest import Manifest, digest, sha256_file, write_atomic
from . import dsl
from .build import TEMPLATE, BuildStats, build_data, empty_data, render_page
from .plan import plan_data


class ContentError(Exception):
    def __init__(self, issues: list[dsl.Issue]):
        self.issues = issues
        super().__init__("\n".join(map(str, issues)))


@dataclass
class BuildResult:
    out: Path
    size: int
    sha256: str
    stats: BuildStats | None      # the map's; None when the page has no map yet
    plan: dict | None = None      # weightage.json, when the page has a Plan tab
    docs: int = 0                 # documents in the Lessons tab
    broken_links: list[str] = field(default_factory=list)   # "lesson: target" for links to files that don't exist


def resolve_content(course: Path, content: Path | None = None) -> Path:
    """The content folder: --content, else <course>/_studymap/content (Markdown per cluster, or the reference
    kit's map.txt), else the course folder itself when it directly holds a map.txt (the reference examples)."""
    from ..content import is_markdown_content
    if content is not None:
        return content
    inside = course / OUT_DIR / "content"
    if (inside / "map.txt").exists() or is_markdown_content(inside):
        return inside
    if (course / "map.txt").exists():
        return course
    raise FileNotFoundError(f"{course}: no content yet (expected {inside}/map.txt). "
                            "Content is written by the /study command, or by hand.")


def load_valid(course: Path, content: Path | None = None) -> dsl.Content:
    """The reference kit's line format (map.txt)."""
    cdir = resolve_content(course, content)
    c = dsl.load(cdir, display_path(cdir))
    if c.issues:
        raise ContentError(c.issues)
    return c


def load_markdown(course: Path, cdir: Path, analysis=None, weightage: dict | None = None):
    """The Markdown content model (FORMAT.md), validated against the analysis and corpus. Raises on errors."""
    from ..analysis.corpus import Corpus
    from ..content import load, validate
    cc = load(cdir)
    cdir_corpus = course / OUT_DIR / "corpus"
    validate(cc, analysis, weightage, corpus=Corpus(cdir_corpus) if (cdir_corpus / "index.json").exists() else None)
    if cc.errors:
        raise ContentError(cc.errors)
    return cc


def cheat_embed(course: Path, cfg, cc, title: str, analysis=None) -> dict:
    """The cheat sheet for the site's tab: the fitted document if `studymap cheatsheet` has run, else a 7.5 pt draft."""
    import json
    from ..cheatsheet import collect, document
    out = course / OUT_DIR
    fitted, info = out / "cheatsheet.html", out / "cheatsheet.json"
    if fitted.exists() and info.exists():
        j = json.loads(info.read_text(encoding="utf-8"))
        lede = (f"{j['pages']} of {j['budget']} A4 pages at {j['font_pt']:g} pt, {cfg.cheatsheet.columns} columns, "
                f"{j['kept']} items" + (f", {len(j['dropped'])} left out (listed in report.md)" if j["dropped"] else "")
                + ". It prints as is; the 4-up file puts it on one sheet.")
        return dict(doc=fitted.read_text(encoding="utf-8"), lede=lede)
    parts = collect(cc, analysis)
    n = sum(len(g) for p in parts for _, g in p.groups)
    return dict(doc=document(parts, set(range(n)), 7.5, title, cfg.cheatsheet.columns, None),
                lede="Draft at 7.5 pt: run `studymap cheatsheet` to fit it to the page budget and write cheatsheet.pdf.")


def build(course: Path, content: Path | None = None, out: Path | None = None) -> BuildResult:
    """index.html from whatever the course has: the paper analysis (Plan tab, plus report.md) and/or map content."""
    from ..analysis.stage import run_report
    cfg = load_config(course)
    rep = run_report(course, cfg)
    if rep.analysis.present and rep.weightage is None:
        raise ContentError(rep.analysis.errors or [Issue(str(display_path(rep.analysis.dir)), 0, "analysis is incomplete")])
    try:
        resolve_content(course, content)
        has_content = True
    except FileNotFoundError:
        if rep.weightage is None:
            raise
        has_content = False
    files: list[Path] = []
    stats = None
    title = " ".join(x for x in (cfg.code, cfg.name) if x) or course.resolve().name
    if has_content:
        from ..content import is_markdown_content
        from .lessons import content_data, to_map
        cdir = resolve_content(course, content)
        if is_markdown_content(cdir):
            cc = load_markdown(course, cdir, rep.analysis if rep.analysis.present else None, rep.weightage)
            data, stats = build_data(to_map(cc, title, "Study map"))
            extra = content_data(cc)
            for nd in data["nodes"]:      # facts keep `code` formatting (the reference md() has none)
                nd["facts"] = [dict(h=h, tags=[]) for h in extra["nodes"][nd["id"]]["facts"]]
            data["content"] = extra
            if cfg.cheatsheet.allowed:   # `allowed: false` (open-book course): no tab, nothing to fit
                data["cheat"] = cheat_embed(course, cfg, cc, data["cfg"]["title"],
                                            rep.analysis if rep.analysis.present else None)
            files = cc.files
        else:
            c = load_valid(course, content)
            data, stats = build_data(c)
            files = c.files
    else:
        data = empty_data(title, "Exam plan")
    from .docs import load_docs
    docs, doc_files = load_docs(course, (out or course / OUT_DIR / "index.html").parent)
    broken = [f"{d['id']}: {m}" for d in docs for m in d.pop("missing")]
    if docs:                     # COURSE/lessons/*.md: the Lessons tab
        data["docs"] = docs
        files += doc_files
    if rep.weightage is not None:
        a = rep.analysis
        data["plan"] = plan_data(cfg, rep.weightage, a.topics, a.papers)
        files += [p for p in (a.dir / "topics.json", a.dir / "papers.json") if p.exists()]
    page = render_page(data)
    default_out = course / OUT_DIR / "index.html"
    target = out or default_out
    write_atomic(target, page)
    raw = page.encode("utf-8")
    res = BuildResult(out=target, size=len(raw), sha256=hashlib.sha256(raw).hexdigest(), stats=stats, plan=rep.weightage,
                      docs=len(docs), broken_links=broken)
    if target.resolve() == default_out.resolve():
        mp = course / OUT_DIR / "state.json"
        man = Manifest.load(mp)
        man.begin("build")
        inputs = {p.name: sha256_file(p) for p in files} | {"template": sha256_file(TEMPLATE)}
        man.finish("build", inputs=digest(inputs), output_sha256=res.sha256, bytes=res.size,
                   nodes=stats.nodes if stats else 0, questions=stats.questions if stats else 0, plan=rep.weightage is not None)
        man.save(mp)
    return res
