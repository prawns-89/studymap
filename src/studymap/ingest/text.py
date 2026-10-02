"""Markdown / text / LaTeX notes (split by heading), code (verbatim, language-tagged), notebooks, images."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .common import char_count, clean_text, first_line, save_image_bytes, save_pixmap
from .records import Figure, Unit

TEXT_CHUNK = 4000          # characters per unit for prose without headings
CODE_CHUNK = 600           # lines per unit for very long code files
HEADING = {
    "md": re.compile(r"^#{1,3}\s+\S"),
    "tex": re.compile(r"^\s*\\(?:chapter|section|subsection)\*?\{"),
    "txt": re.compile(r"$^"),     # never matches: plain text splits on size only
}
MIPS = re.compile(r"\$(?:zero|at|v[01]|a[0-3]|t[0-9]|s[0-8]|k[01]|gp|sp|fp|ra|[0-9]{1,2})\b|^\s*(?:syscall|jal|jr|lw|sw|addiu?|beq|bne)\b", re.M)
X86 = re.compile(r"\b(?:e?[abcd]x|[abcd][lh]|e?[sd]i|e?[sb]p|r[abcd]x|r[sd]i|%e?[abcd]x)\b|\.model\b|\bint\s+21h\b|\bmovl?\b", re.I)


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            s = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        s = raw.decode("latin-1")
    return s.replace("\r\n", "\n").replace("\r", "\n")


def asm_flavour(src: str) -> str:
    m, x = len(MIPS.findall(src)), len(X86.findall(src))
    if m > x and m >= 2:
        return "mipsasm"
    if x > m and x >= 2:
        return "x86asm"
    return "plaintext"


def _spans(lines: list[str], starts: list[int], limit_chars: int) -> list[tuple[int, int]]:
    """Split [0, len) at heading starts, then split any oversize span at blank lines."""
    bounds = sorted(set([0] + starts)) + [len(lines)]
    out = []
    for a, b in zip(bounds, bounds[1:]):
        if a >= b:
            continue
        s, size = a, 0
        for i in range(a, b):
            size += len(lines[i]) + 1
            if size > limit_chars and not lines[i].strip() and i > s:
                out.append((s, i))
                s, size = i + 1, 0
        if s < b:
            out.append((s, b))
    return out


def extract_text(path: Path, rel: str, kind: str, flavour: str):
    src = read_text(path)
    lines = src.split("\n")
    pat = HEADING.get(flavour, HEADING["txt"])
    starts, fence = [], False
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("```"):
            fence = not fence
        elif not fence and pat.match(ln):
            starts.append(i)
    units = []
    for a, b in _spans(lines, starts, TEXT_CHUNK):
        body = "\n".join(lines[a:b]).strip("\n")
        if not body.strip():
            continue
        text = clean_text(body) if flavour != "md" else body.rstrip()
        title = first_line(lines[a]) if a in starts else ""
        units.append(Unit(ref=f"{rel}#L{a + 1}-{b}", n=len(units) + 1, title=title, text=text,
                          chars=char_count(text), lang=flavour))
    return units, {"lines": len(lines)}, []


def extract_code(path: Path, rel: str, kind: str, lang: str):
    """Code is copied verbatim (only line endings are normalised to LF)."""
    src = read_text(path)
    if lang == "asm":
        lang = asm_flavour(src)
    if path.suffix.lower() == ".ipynb":
        return _notebook(src, rel)
    lines = src.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    units = []
    for a in range(0, max(len(lines), 1), CODE_CHUNK):
        b = min(len(lines), a + CODE_CHUNK)
        text = "\n".join(lines[a:b])
        units.append(Unit(ref=f"{rel}#L{a + 1}-{b}", n=len(units) + 1, title=path.name if a == 0 else "",
                          text=text, lang=lang, chars=char_count(text)))
    return units, {"lines": len(lines), "lang": lang}, []


def _notebook(src: str, rel: str):
    try:
        nb = json.loads(src)
    except ValueError as e:
        return [], {}, [f"not a valid notebook: {e}"]
    lang = (nb.get("metadata", {}).get("kernelspec", {}).get("language") or "python").lower()
    units = []
    for i, cell in enumerate(nb.get("cells", []), 1):
        body = "".join(cell.get("source", []))
        if not body.strip():
            continue
        is_code = cell.get("cell_type") == "code"
        units.append(Unit(ref=f"{rel}#cell{i}", n=i, text=body, lang=lang if is_code else "md",
                          title=first_line(body) if not is_code else "", chars=char_count(body)))
    return units, {"cells": len(nb.get("cells", [])), "lang": lang}, []


def extract_image(path: Path, rel: str, kind: str, img_dir: Path, img_rel: str):
    import pymupdf
    name = "image.jpg"
    try:
        if path.suffix.lower() == ".svg":
            doc = pymupdf.open(path)
            page = doc[0]
            zoom = 1400 / max(page.rect.width, page.rect.height, 1)
            wh = save_pixmap(page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False), img_dir / name)
        else:
            wh = save_image_bytes(path.read_bytes(), img_dir / name)
    except Exception as e:
        return [], {}, [f"can't decode image: {str(e).splitlines()[0] if str(e) else type(e).__name__}"]
    if wh is None:
        return [], {}, ["image too small or in a format that can't be decoded"]
    fig = Figure(path=f"{img_rel}/{name}", why="image-file", w=wh[0], h=wh[1])
    return [Unit(ref=rel, n=1, title=path.stem, flags=["figure", "low-text"], figures=[fig])], {}, []
