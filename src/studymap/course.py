"""The input folder contract (BRIEF section 3): course.yaml, folder kinds, paper names."""
from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

OUT_DIR = "_studymap"
KINDS = ("slides", "notes", "labs", "papers", "extra")
# never descend into these; hidden folders (".git", ".claude") are skipped too
SKIP_DIRS = {OUT_DIR, "__pycache__", "node_modules", "__MACOSX"}


class Exam(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    weight: float | None = None
    format: str = ""


class Cheatsheet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pages: int = Field(8, ge=1, le=40)
    paper: str = "A4"
    columns: int = Field(4, ge=1, le=6)
    allowed: bool = True


class CourseConfig(BaseModel):
    """course.yaml. Every field is optional; unknown fields are an error so typos surface."""
    model_config = ConfigDict(extra="forbid")
    name: str = ""
    code: str = ""
    exams: list[Exam] = []
    cheatsheet: Cheatsheet = Cheatsheet()
    labs_viva: bool = False
    focus: list[str] = []
    ignore: list[str] = []
    notes_for_claude: str = ""


class CourseError(Exception):
    pass


def load_config(root: Path) -> CourseConfig:
    path = root / "course.yaml"
    if not path.exists():
        return CourseConfig()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f"{path}:{mark.line + 1}" if mark else str(path)
        raise CourseError(f"{where}: can't parse YAML: {getattr(e, 'problem', e)}") from None
    if not isinstance(raw, dict):
        raise CourseError(f"{path}: expected a mapping of settings at the top level")
    try:
        return CourseConfig.model_validate(raw)
    except ValidationError as e:
        lines = [f"{path}: {'.'.join(map(str, err['loc'])) or '(top)'}: {err['msg']}" for err in e.errors()]
        raise CourseError("\n".join(lines)) from None


def display_path(p: Path) -> Path:
    """Relative to the working directory when inside it (clickable in terminals), else absolute."""
    try:
        rel = os.path.relpath(p)
    except ValueError:
        return p
    return Path(rel) if not rel.startswith("..") else p.resolve()


def kind_of(rel: str) -> str:
    """Folder kind for a course-relative posix path. Unknown folders and root files are notes."""
    parts = rel.split("/")
    if len(parts) < 2:
        return "notes"
    top = parts[0].lower()
    return top if top in KINDS else "notes"


def is_ignored(rel: str, patterns: list[str]) -> bool:
    """Glob patterns from course.yaml `ignore`, matched against the path and each parent folder."""
    if not patterns:
        return False
    parts = rel.split("/")
    prefixes = ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]
    for pat in patterns:
        pat = pat.strip().rstrip("/")
        if pat.startswith("./"):
            pat = pat[2:]
        if any(fnmatch.fnmatchcase(p, pat) for p in prefixes):
            return True
    return False


# --------------------------------------------------------------------------- paper names

KEY_RE = re.compile(r"[-_ ](?:key|keys|solutions?|sol|soln|answers?|ans)$")
PAPER_RE = re.compile(r"^(\d{4})-([a-z][a-z0-9]*)(?:-(.+))?$")


@dataclass(frozen=True)
class PaperName:
    base: str            # stem without the key suffix, lower case: "2024-midsem"
    is_key: bool
    year: int | None
    exam: str            # "midsem", or the whole base for names like "sample-questions"
    variant: str


def parse_paper_name(stem: str) -> PaperName:
    s = stem.strip().lower()
    m = KEY_RE.search(s)
    is_key = bool(m)
    base = s[: m.start()] if m else s
    pm = PAPER_RE.match(base)
    if pm:
        return PaperName(base, is_key, int(pm.group(1)), pm.group(2), pm.group(3) or "")
    return PaperName(base, is_key, None, base, "")
