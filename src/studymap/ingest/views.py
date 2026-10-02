"""Readable views of the corpus: text/<sid>.md per source (for Claude to read in pieces) and index.json."""
from __future__ import annotations

import re

from .records import SourceRecord

COUNT_WORD = {"pdf": "pages", "pptx": "slides", "docx": "sections", "text": "sections", "code": "lines", "image": ""}


def fence(text: str) -> str:
    longest = max((len(m) for m in re.findall(r"`{3,}", text)), default=0)
    return "`" * max(3, longest + 1)


def source_md(rec: SourceRecord, dups: dict[str, str], paper: dict | None) -> str:
    out = [f"# {rec.path}", ""]
    bits = [f"kind: {rec.kind}", f"type: {rec.type}"]
    if rec.type == "code":
        bits.append(f"lang: {rec.meta.get('lang', '')}, {rec.meta.get('lines', 0)} lines")
    elif COUNT_WORD.get(rec.type):
        bits.append(f"{len(rec.units)} {COUNT_WORD[rec.type]}")
    rendered = sum(len(u.figures) for u in rec.units)
    if rendered:
        bits.append(f"{rendered} images")
    if rec.meta.get("image_only_pages"):
        bits.append(f"{rec.meta['image_only_pages']} image-only pages")
    nd = sum(u.ref in dups for u in rec.units)
    if nd:
        bits.append(f"{nd} near-duplicates omitted")
    out.append(" · ".join(bits))
    if paper:
        p = [f"paper: {paper['exam']}" + (f" {paper['year']}" if paper["year"] else "") +
             (f" ({paper['variant']})" if paper["variant"] else "")]
        if paper.get("is_key"):
            p.append(f"answer key for: {paper['key_for'] or '(no matching paper)'}")
        elif paper.get("key"):
            p.append(f"answer key: {paper['key']}")
        out.append(" · ".join(p))
    for w in rec.warnings:
        out.append(f"> warning: {w}")
    out.append("")
    for u in rec.units:
        label = u.ref.rsplit("#", 1)[1] if "#" in u.ref else "file"
        if u.ref in dups:
            out += [f"## {label} · near-duplicate of {dups[u.ref]} (omitted)", ""]
            continue
        title = u.title.split("\n", 1)[0].strip()
        head = f"## {label}" + (f" · {title}" if title and rec.type != "code" else "")
        flags = [f for f in u.flags if f != "figure"]
        if flags:
            head += f"  [{', '.join(flags)}]"
        out += [head, f"<!-- src: {u.ref} -->"]
        for f in u.figures:
            out.append(f"![{f.why}](../{f.path})")
        if u.text:
            if u.lang and u.lang not in ("md", "txt", "tex"):
                fz = fence(u.text)
                out += ["", f"{fz}{u.lang}", u.text, fz]
            else:
                out += ["", u.text]
        if u.notes:
            out += ["", "> **Speaker notes:** " + u.notes.replace("\n", "\n> ")]
        out.append("")
    return "\n".join(out).rstrip() + "\n"
