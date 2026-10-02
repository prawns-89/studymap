"""Find a course's content, validate it, and build index.html."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
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


def resolve_content(course: Path, content: Path | None = None) -> Path:
    """The content folder: --content, else <course>/_studymap/content, else the course folder itself
    when it directly holds a map.txt (a bare content folder, like the reference examples)."""
    if content is not None:
        return content
    inside = course / OUT_DIR / "content"
    if (inside / "map.txt").exists():
        return inside
    if (course / "map.txt").exists():
        return course
    raise FileNotFoundError(f"{course}: no content yet (expected {inside}/map.txt). "
                            "Content is written by the /study command, or by hand.")


def load_valid(course: Path, content: Path | None = None) -> dsl.Content:
    cdir = resolve_content(course, content)
    c = dsl.load(cdir, display_path(cdir))
    if c.issues:
        raise ContentError(c.issues)
    return c


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
    if has_content:
        c = load_valid(course, content)
        data, stats = build_data(c)
        files = c.files
    else:
        data = empty_data(" ".join(x for x in (cfg.code, cfg.name) if x) or course.resolve().name, "Exam plan")
    if rep.weightage is not None:
        a = rep.analysis
        data["plan"] = plan_data(cfg, rep.weightage, a.topics, a.papers)
        files += [p for p in (a.dir / "topics.json", a.dir / "papers.json") if p.exists()]
    page = render_page(data)
    default_out = course / OUT_DIR / "index.html"
    target = out or default_out
    write_atomic(target, page)
    raw = page.encode("utf-8")
    res = BuildResult(out=target, size=len(raw), sha256=hashlib.sha256(raw).hexdigest(), stats=stats, plan=rep.weightage)
    if target.resolve() == default_out.resolve():
        mp = course / OUT_DIR / "state.json"
        man = Manifest.load(mp)
        man.begin("build")
        inputs = {p.name: sha256_file(p) for p in files} | {"template": sha256_file(TEMPLATE)}
        man.finish("build", inputs=digest(inputs), output_sha256=res.sha256, bytes=res.size,
                   nodes=stats.nodes if stats else 0, questions=stats.questions if stats else 0, plan=rep.weightage is not None)
        man.save(mp)
    return res
