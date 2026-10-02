"""A small Markdown subset for question and answer text: paragraphs, ``` code fences, pipe tables,
`inline code`, **bold** and *italic*. Everything is HTML-escaped first; KaTeX and highlighting come later."""
from __future__ import annotations

import html
import re

_INLINE_CODE = re.compile(r"`([^`\n]+)`")


def inline(s: str) -> str:
    s = html.escape(s, quote=False)
    codes: list[str] = []

    def keep(m):
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"
    s = _INLINE_CODE.sub(keep, s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", s)
    return re.sub("\x00(\\d+)\x00", lambda m: f"<code>{codes[int(m.group(1))]}</code>", s)


def _table(rows: list[str]) -> str:
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    has_rule = len(rows) > 1 and set(rows[1].replace("|", "").strip()) <= set("-: ")
    head, body = cells[0], cells[2:] if has_rule else cells[1:]
    th = "".join(f"<th>{inline(c)}</th>" for c in head)
    tb = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body)
    return f'<div class="tblwrap"><table class="mini"><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table></div>'


def block(text: str) -> str:
    out, para, lines, i = [], [], text.replace("\r\n", "\n").split("\n"), 0

    def flush():
        if para:
            out.append("<p>" + "<br>".join(inline(p) for p in para) + "</p>")
            para.clear()
    while i < len(lines):
        ln = lines[i]
        m = re.match(r"^(`{3,})(\w*)\s*$", ln.strip())
        if m:
            flush()
            fence, lang, code = m.group(1), m.group(2), []
            i += 1
            while i < len(lines) and lines[i].strip() != fence:
                code.append(lines[i])
                i += 1
            cls = f' class="language-{lang}"' if lang else ""
            out.append(f"<pre><code{cls}>{html.escape(chr(10).join(code), quote=False)}</code></pre>")
        elif ln.strip().startswith("|") and i + 1 < len(lines) and lines[i + 1].strip().startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            out.append(_table(rows))
            continue
        elif not ln.strip():
            flush()
        else:
            para.append(ln.strip())
        i += 1
    flush()
    return "".join(out)
