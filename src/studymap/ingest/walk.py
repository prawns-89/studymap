"""Find every file in a course folder and decide how to read it, or why it is skipped."""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

from ..course import SKIP_DIRS, is_ignored, kind_of

# highlight.js language names, so the site can highlight with the same tag
CODE_LANG = {
    ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hh": "cpp", ".hxx": "cpp",
    ".s": "asm", ".asm": "asm",
    ".m": "matlab", ".py": "python", ".ipynb": "python",
    ".v": "verilog", ".vh": "verilog", ".sv": "verilog", ".svh": "verilog", ".vhd": "vhdl", ".vhdl": "vhdl",
    ".cir": "spice", ".sp": "spice", ".spice": "spice", ".net": "spice", ".ckt": "spice",
    ".java": "java", ".js": "javascript", ".ts": "typescript", ".sh": "bash", ".bash": "bash", ".mk": "makefile",
    ".rs": "rust", ".go": "go", ".sql": "sql", ".r": "r", ".jl": "julia", ".tcl": "tcl", ".xdc": "tcl",
    ".pl": "perl", ".pm": "perl", ".lua": "lua", ".hs": "haskell", ".kt": "kotlin", ".ld": "plaintext",
    # a languages course compares paradigms, so its examples are in the paradigms' own languages
    ".lisp": "lisp", ".lsp": "lisp", ".cl": "lisp", ".el": "lisp", ".scm": "scheme", ".ss": "scheme",
    ".rkt": "scheme", ".clj": "clojure", ".cljs": "clojure", ".ml": "ocaml", ".mli": "ocaml",
    ".sml": "sml", ".fs": "fsharp", ".fsi": "fsharp", ".erl": "erlang", ".ex": "elixir", ".exs": "elixir",
    ".elm": "elm", ".scala": "scala", ".rb": "ruby", ".swift": "swift", ".cs": "csharp",
    ".mm": "objectivec", ".adb": "ada", ".ads": "ada", ".f90": "fortran", ".f": "fortran",
    ".pas": "delphi", ".st": "smalltalk", ".pro": "prolog", ".p": "prolog",
}
CODE_NAMES = {"makefile": "makefile", "gnumakefile": "makefile", "dockerfile": "dockerfile", "cmakelists.txt": "cmake"}
TEXT_EXT = {".md": "md", ".markdown": "md", ".txt": "txt", ".text": "txt", ".rst": "txt", ".adoc": "txt", ".tex": "tex"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".svg"}
DOC_EXT = {".pdf": "pdf", ".pptx": "pptx", ".docx": "docx"}

SKIP_REASONS = {
    **{e: "legacy Office format: save it as .pptx/.docx/.pdf" for e in (".ppt", ".doc", ".pps", ".xls")},
    **{e: "archive: unpack it into the folder to include it" for e in (".zip", ".tar", ".gz", ".tgz", ".7z", ".rar", ".bz2", ".xz")},
}
MAX_TEXT_BYTES = 1_000_000


@dataclass
class Candidate:
    rel: str             # course-relative posix path
    path: Path
    kind: str
    type: str            # pdf | pptx | docx | text | code | image
    lang: str = ""       # code language, or the text flavour (md / txt / tex)


def classify(rel: str, path: Path) -> tuple[str, str] | str:
    """(type, lang) for a readable file, or the reason it is skipped."""
    name = path.name.lower()
    ext = path.suffix.lower()
    if ext in DOC_EXT:
        return DOC_EXT[ext], ""
    if ext in IMAGE_EXT:
        return "image", ""
    if name in CODE_NAMES:
        return "code", CODE_NAMES[name]
    if ext in TEXT_EXT or ext in CODE_LANG:
        try:
            size = path.stat().st_size
        except OSError:
            return "unreadable"
        if size > MAX_TEXT_BYTES:
            return f"text file over {MAX_TEXT_BYTES // 1000} KB (probably generated)"
        if ext in TEXT_EXT:
            return "text", TEXT_EXT[ext]
        return "code", CODE_LANG[ext]
    return SKIP_REASONS.get(ext, f"unsupported type ({ext or 'no extension'})")


def walk(root: Path, ignore: list[str]) -> tuple[list[Candidate], list[tuple[str, str]]]:
    """Sorted readable files and (path, reason) for skipped ones. Follows symlinks, without loops."""
    found, skipped = [], []
    seen_dirs: set[tuple[int, int]] = set()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        st = os.stat(dirpath)
        if (st.st_dev, st.st_ino) in seen_dirs:
            dirnames[:] = []
            continue
        seen_dirs.add((st.st_dev, st.st_ino))
        reld = Path(dirpath).relative_to(root).as_posix()
        reld = "" if reld == "." else reld + "/"
        keep = []
        for d in sorted(dirnames):
            if d.startswith(".") or d in SKIP_DIRS:
                continue
            if is_ignored(reld + d, ignore):
                skipped.append((reld + d + "/", "ignored by course.yaml"))
                continue
            keep.append(d)
        dirnames[:] = keep
        for fn in sorted(filenames):
            rel = reld + fn
            if fn.startswith(".") or fn.startswith("~$") or (not reld and fn in ("course.yaml", "course.yml")):
                continue
            if is_ignored(rel, ignore):
                skipped.append((rel, "ignored by course.yaml"))
                continue
            p = Path(dirpath) / fn
            if not p.is_file():
                skipped.append((rel, "broken link or not a regular file"))
                continue
            c = classify(rel, p)
            if isinstance(c, str):
                skipped.append((rel, c))
            else:
                found.append(Candidate(rel, p, kind_of(rel), c[0], c[1]))
    found.sort(key=lambda c: c.rel)
    skipped.sort()
    return found, skipped


def make_sids(rels: list[str]) -> dict[str, str]:
    """Stable, filesystem-safe ids from paths; a short hash is added only where two paths would collide."""
    base = {r: (re.sub(r"[^a-z0-9]+", "-", r.lower()).strip("-") or "source")[:80] for r in rels}
    count: dict[str, int] = {}
    for s in base.values():
        count[s] = count.get(s, 0) + 1
    return {r: s if count[s] == 1 else f"{s}-{hashlib.sha1(r.encode()).hexdigest()[:6]}" for r, s in base.items()}
