"""The Lessons tab: long-form Markdown documents from COURSE/lessons/*.md, rendered at build time.

A fuller Markdown subset than text.py's (which is for question text): headings with anchors, nested
lists, block quotes, <details> answer blocks, rules and links. Links between lesson files become
in-page links, so the whole set works offline inside index.html. Everything is HTML-escaped first.
"""
from __future__ import annotations

import html
import os
import re
from pathlib import Path
from urllib.parse import quote, unquote

DOCS_DIR = "lessons"

_FENCE = re.compile(r"^(`{3,})([\w+-]*)\s*$")
_HEAD = re.compile(r"^(#{1,6})\s+(.*?)\s*#*$")
_LIST = re.compile(r"^( *)([-*]|\d+[.)])\s+(.*)$")
_LINK = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")
_ESC = re.compile(r"\\([\\`*_\[\]|#<>-])")
_CODE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")


def _emph(s: str) -> str:
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    return re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", s)


def _indent(s: str) -> int:
    return len(s) - len(s.lstrip(" "))


def slug(text: str) -> str:
    s = re.sub(r"<[^>]+>|[`*_]", "", text).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "section"


class _Doc:
    """Renders one document. `ids` are the document ids that links may point to."""

    def __init__(self, ids: set[str], base: Path | None = None, out: Path | None = None):
        # base: the folder the Markdown's relative links start from; out: the folder of the page they end up in
        self.ids, self.toc, self._used, self.base, self.out, self.missing = ids, [], set(), base, out, []

    # ---------------------------------------------------------------- inline
    def inline(self, s: str) -> str:
        s = html.escape(s, quote=False)
        keep: list[str] = []

        def hold(text: str) -> str:
            keep.append(text)
            return f"\x00{len(keep) - 1}\x00"
        s = _CODE.sub(lambda m: hold(f"<code>{m.group(2).strip()}</code>"), s)   # `x` or ``x `y` z``
        s = _ESC.sub(lambda m: hold(m.group(1)), s)
        s = _LINK.sub(lambda m: hold(self._link(m.group(1), html.unescape(m.group(2)))), s)   # label stays escaped
        s = _emph(s)
        for _ in range(3):        # held pieces can contain held pieces (code inside link text)
            s = re.sub("\x00(\\d+)\x00", lambda m: keep[int(m.group(1))], s)
        return s

    def _link(self, label: str, href: str) -> str:
        """label is already escaped and may hold code placeholders, which inline() restores afterwards."""
        label = _emph(label)
        if re.match(r"https?://", href):
            return f'<a href="{html.escape(href)}" target="_blank" rel="noopener">{label}</a>'
        path, _, frag = href.partition("#")
        if not path:
            return f'<a href="#" data-frag="{html.escape(frag)}">{label}</a>'
        doc = Path(path).stem
        if path.endswith(".md") and doc in self.ids:
            return (f'<a href="#docs/{html.escape(doc)}" data-doc="{html.escape(doc)}"'
                    f' data-frag="{html.escape(frag)}">{label}</a>')
        if self.base is not None:             # a course file: re-aim the link from the page's own folder
            target = (self.base / unquote(path)).resolve()
            if not target.exists():
                self.missing.append(href)
                return f'<span class="xref" title="missing: {html.escape(href)}">{label}</span>'
            href = quote(os.path.relpath(target, self.out or self.base)) + (f"#{frag}" if frag else "")
        return f'<a href="{html.escape(href)}" target="_blank" rel="noopener">{label}</a>'

    # ---------------------------------------------------------------- blocks
    def _heading(self, level: int, text: str) -> str:
        base = hid = slug(text)
        n = 2
        while hid in self._used:
            hid, n = f"{base}-{n}", n + 1
        self._used.add(hid)
        if level == 2:
            self.toc.append([hid, re.sub(r"<[^>]+>", "", self.inline(text))])
        return f'<h{level} id="d-{hid}">{self.inline(text)}</h{level}>'   # d-: no clash with the page's own ids

    def _table(self, rows: list[str]) -> str:
        def cells(row: str) -> list[str]:
            out, cur, code = [], "", 0
            row = row.strip()
            row = row[1:] if row.startswith("|") else row
            row = row[:-1] if row.endswith("|") and not row.endswith("\\|") else row
            i = 0
            while i < len(row):
                c = row[i]
                if c == "\\" and i + 1 < len(row):
                    cur += row[i:i + 2]
                    i += 2
                    continue
                if c == "`":                        # a run of n backticks opens, the same run closes
                    run = len(row[i:]) - len(row[i:].lstrip("`"))
                    code = run if not code else (0 if run == code else code)
                    cur += row[i:i + run]
                    i += run
                    continue
                if c == "|" and not code:
                    out.append(cur.strip())
                    cur = ""
                else:
                    cur += c
                i += 1
            return out + [cur.strip()]
        rule = len(rows) > 1 and set(rows[1].replace("|", "").strip()) <= set("-: ")
        head, body = cells(rows[0]), [cells(r) for r in (rows[2:] if rule else rows[1:])]
        th = "".join(f"<th>{self.inline(c)}</th>" for c in head)
        tb = "".join("<tr>" + "".join(f"<td>{self.inline(c)}</td>" for c in r) + "</tr>" for r in body)
        return f'<div class="tblwrap"><table class="mini"><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table></div>'

    @staticmethod
    def _starts_block(s: str) -> bool:
        t = s.strip()
        return bool(_FENCE.match(t) or _HEAD.match(t) or _LIST.match(s) or t.startswith((">", "|", "<details")))

    def blocks(self, lines: list[str]) -> str:
        out, i, n = [], 0, len(lines)
        while i < n:
            ln, s = lines[i], lines[i].strip()
            if not s:
                i += 1
                continue
            if m := _FENCE.match(s):
                ind, fence, lang, code = _indent(ln), m.group(1), m.group(2), []
                i += 1
                while i < n and lines[i].strip() != fence:
                    code.append(lines[i][min(ind, _indent(lines[i])):])
                    i += 1
                cls = f' class="language-{lang}"' if lang else ""
                out.append(f"<pre><code{cls}>{html.escape(chr(10).join(code), quote=False)}</code></pre>")
                i += 1
            elif (m := _HEAD.match(s)) and _indent(ln) < 4:
                out.append(self._heading(len(m.group(1)), m.group(2)))
                i += 1
            elif re.fullmatch(r"(-\s*){3,}|(\*\s*){3,}", s):
                out.append("<hr>")
                i += 1
            elif s.startswith("<details"):
                summary = re.search(r"<summary>(.*?)</summary>", s)
                depth, inner = 1, []
                i += 1
                while i < n:
                    t = lines[i].strip()
                    depth += t.startswith("<details") - (t == "</details>")
                    if depth == 0:
                        break
                    inner.append(lines[i])
                    i += 1
                i += 1
                label = self.inline(summary.group(1)) if summary else "Details"
                out.append(f"<details><summary>{label}</summary>{self.blocks(inner)}</details>")
            elif s.startswith(">"):
                inner = []
                while i < n and lines[i].strip().startswith(">"):
                    inner.append(re.sub(r"^\s*> ?", "", lines[i]))
                    i += 1
                out.append(f"<blockquote>{self.blocks(inner)}</blockquote>")
            elif s.startswith("|") and i + 1 < n and lines[i + 1].strip().startswith("|"):
                rows = []
                while i < n and lines[i].strip().startswith("|"):
                    rows.append(lines[i])
                    i += 1
                out.append(self._table(rows))
            elif m := _LIST.match(ln):
                html_, i = self._list(lines, i, len(m.group(1)), m.group(2)[0].isdigit())
                out.append(html_)
            else:
                para = []
                while i < n and lines[i].strip() and not (para and self._starts_block(lines[i])):
                    para.append(lines[i].strip())
                    i += 1
                out.append(f"<p>{self.inline(' '.join(para))}</p>")
        return "".join(out)

    def _list(self, lines: list[str], i: int, base: int, ordered: bool) -> tuple[str, int]:
        items, start, n = [], None, len(lines)
        while i < n and (m := _LIST.match(lines[i])) and len(m.group(1)) == base \
                and m.group(2)[0].isdigit() == ordered:
            if start is None and ordered:
                start = int(m.group(2)[:-1])
            body, cut = [m.group(3)], m.start(3)
            i += 1
            while i < n:
                t = lines[i]
                if not t.strip():
                    j = i
                    while j < n and not lines[j].strip():
                        j += 1
                    if j < n and _indent(lines[j]) > base:
                        body += [""] * (j - i)
                        i = j
                        continue
                    break
                if _indent(t) > base:
                    body.append(t[min(cut, _indent(t)):])
                elif body[-1].strip() and not self._starts_block(t):
                    body.append(t.strip())          # a lazy continuation of the item's paragraph
                else:
                    break
                i += 1
            inner = self.blocks(body)
            if inner.startswith("<p>") and inner.count("<p>") == 1 and inner.endswith("</p>"):
                inner = inner[3:-4]                 # a tight item: no paragraph margins
            elif inner.startswith("<p>") and "</p>" in inner:
                head, rest = inner[3:].split("</p>", 1)
                inner = head + rest
            items.append(f"<li>{inner}</li>")
        tag = "ol" if ordered else "ul"
        attr = f' start="{start}"' if ordered and start not in (None, 1) else ""
        return f"<{tag}{attr}>{''.join(items)}</{tag}>", i


def render_doc(text: str, ids: set[str], base: Path | None = None, out: Path | None = None,
               missing: list[str] | None = None) -> tuple[str, list[list[str]]]:
    """HTML and the table of contents (level-2 headings as [id, text]) for one Markdown document.
    Links to other documents in `ids` stay in the page; links to files are made relative to `out`."""
    d = _Doc(ids, base, out)
    body = d.blocks(text.replace("\r\n", "\n").split("\n"))
    if missing is not None:
        missing += d.missing
    return body, d.toc


def load_docs(course: Path, out_dir: Path | None = None) -> tuple[list[dict], list[Path]]:
    """COURSE/lessons/*.md, README first, then by file name. Returns the documents and their files.
    out_dir is where the page will be written, so links to course files (PDFs, code) resolve from there."""
    folder = course / DOCS_DIR
    if not folder.is_dir():
        return [], []
    files = sorted(folder.glob("*.md"), key=lambda p: (p.stem.lower() != "readme", p.name.lower()))
    ids = {p.stem for p in files}
    docs = []
    for p in files:
        text = p.read_text(encoding="utf-8")
        missing: list[str] = []
        body, toc = render_doc(text, ids, folder, out_dir or folder, missing)
        m = re.search(r"^#\s+(.+)$", text, re.M)
        title = re.sub(r"[`*_]", "", m.group(1)).strip() if m else p.stem
        docs.append(dict(id=p.stem, title=title, html=body, toc=toc, missing=missing))
    return docs, files
