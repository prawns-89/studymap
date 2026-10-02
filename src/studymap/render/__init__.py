"""Find a course's content, validate it, and build index.html."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from ..course import OUT_DIR, display_path
from ..manifest import Manifest, digest, sha256_file, write_atomic
from . import dsl
from .build import TEMPLATE, BuildStats, build_data, render_page


class ContentError(Exception):
    def __init__(self, issues: list[dsl.Issue]):
        self.issues = issues
        super().__init__("\n".join(map(str, issues)))


@dataclass
class BuildResult:
    out: Path
    size: int
    sha256: str
    stats: BuildStats


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
    c = load_valid(course, content)
    data, stats = build_data(c)
    page = render_page(data)
    default_out = course / OUT_DIR / "index.html"
    target = out or default_out
    write_atomic(target, page)
    raw = page.encode("utf-8")
    res = BuildResult(out=target, size=len(raw), sha256=hashlib.sha256(raw).hexdigest(), stats=stats)
    if target.resolve() == default_out.resolve():
        mp = course / OUT_DIR / "state.json"
        man = Manifest.load(mp)
        man.begin("build")
        inputs = {p.name: sha256_file(p) for p in c.files} | {"template": sha256_file(TEMPLATE)}
        man.finish("build", inputs=digest(inputs), output_sha256=res.sha256, bytes=res.size,
                   nodes=stats.nodes, questions=stats.questions)
        man.save(mp)
    return res
