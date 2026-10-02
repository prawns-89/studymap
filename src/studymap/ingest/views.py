"""Readable views of the corpus: text/<sid>.md per source (for Claude to read in pieces) and index.json."""
from __future__ import annotations

import re

from .records import SourceRecord

COUNT_WORD = {"pdf": "pages", "pptx": "slides", "docx": "sections", "text": "sections", "code": "lines", "image": ""}


def count(rtype: str, n: int) -> str:
    word = COUNT_WORD.get(rtype) or "units"
    return f"{n} {word[:-1] if n == 1 else word}"


def fence(text: str) -> str:
    longest = max((len(m) for m in re.findall(r"`{3,}", text)), default=0)
    return "`" * max(3, longest + 1)


def source_md(rec: SourceRecord, dups: dict[str, str], paper: dict | None) -> str:
    out = [f"# {rec.path}", ""]
    bits = [f"kind: {rec.kind}", f"type: {rec.type}"]
    if rec.type == "code":
        bits.append(f"lang: {rec.meta.get('lang', '')}, {rec.meta.get('lines', 0)} lines")
    elif COUNT_WORD.get(rec.type):
        bits.append(count(rec.type, len(rec.units)))
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


def _ranges(units, dups) -> str:
    """'p1 Title | p2-4 Same title | …' with near-duplicates left out and repeated titles merged."""
    items: list[list] = []
    for u in units:
        if u.ref in dups:
            continue
        label = u.ref.rsplit("#", 1)[1] if "#" in u.ref else ""
        kind = re.match(r"[a-zA-Z]+", label).group(0) if label else ""
        title = u.title.split("\n", 1)[0].strip()[:70] or "·"
        flag = " [img]" if ("image-only" in u.flags or "low-text" in u.flags) and u.figures else ""
        if items and items[-1][3] == title + flag and items[-1][0] == kind and items[-1][2] == u.n - 1:
            items[-1][2] = u.n
        else:
            items.append([kind, u.n, u.n, title + flag])
    return " | ".join(f"{k}{a}{'-' + str(b) if b != a else ''} {t}" for k, a, b, t in items)


def outline_md(recs: list[SourceRecord], dups: dict[str, str], papers: dict[str, dict]) -> str:
    """corpus/outline.md: every source on a line or two, so a reader can plan without opening everything."""
    out = ["# Corpus outline", "",
           "Titles per page/slide/section (near-duplicates left out; `[img]` = read the page image). "
           "Cite pages as `path#p12`, ranges as `path#p8-13`; full text is in `text/<sid>.md`.", ""]
    by_kind: dict[str, list[SourceRecord]] = {}
    for r in recs:
        by_kind.setdefault(r.kind, []).append(r)
    for kind in ("slides", "papers", "notes", "extra"):
        if kind not in by_kind:
            continue
        out += [f"## {kind}", ""]
        for r in by_kind[kind]:
            head = f"**{r.path}** ({count(r.type, len(r.units))}) `text/{r.sid}.md`"
            p = papers.get(r.path)
            if p:
                head += " · " + ("answer key for " + (p["key_for"] or "?") if p["is_key"]
                                 else "key: " + (p["key"] or "none"))
            if kind == "papers" or r.type in ("code", "image"):
                io = r.meta.get("image_only_pages", 0)
                out.append(f"- {head}" + (f" · {io} image-only pages" if io else ""))
            else:
                out += [f"- {head}", f"  {_ranges(r.units, dups)}"]
        out.append("")
    if "labs" in by_kind:
        out += ["## labs", ""]
        groups: dict[str, list[SourceRecord]] = {}
        for r in by_kind["labs"]:
            parts = r.path.split("/")
            groups.setdefault("/".join(parts[:2]) if len(parts) > 2 else r.path, []).append(r)
        for g, rs in groups.items():
            langs: dict[str, int] = {}
            docs = []
            for r in rs:
                if r.type == "code":
                    lang = r.meta.get("lang", "code")
                    langs[lang] = langs.get(lang, 0) + 1
                elif r.type in ("text", "pdf", "pptx", "docx"):
                    first = next((u.title for u in r.units if u.title), "")
                    docs.append(r.path[len(g) + 1:] + (f" ({first[:50]})" if first else ""))
            bits = [", ".join(f"{k} ×{v}" for k, v in sorted(langs.items()))] if langs else []
            if docs:
                bits.append("docs: " + "; ".join(docs[:8]) + (" …" if len(docs) > 8 else ""))
            out.append(f"- **{g}/** {len(rs)} files" + (" · " + " · ".join(bits) if bits else ""))
        out.append("")
    return "\n".join(out).rstrip() + "\n"
