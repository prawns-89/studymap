"""Markdown content (FORMAT.md) -> map data for the ported renderer, plus a lesson per node for the Learn tab."""
from __future__ import annotations

import html
import re

from ..content import CourseContent, Node
from .dsl import Content
from .text import block, inline

TIER = {"high": 1, "med": 2, "low": 3}
SPLIT = re.compile(r"^\s*\*\*(Solution|Answer|Model answer)\*\*:?\s*(.*)$", re.I)
ITEM = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(.*)$")
TITLES = {"conceptual": "Conceptual questions the course likes", "example": "Worked example", "variant": "Variant: try it", "pitfalls": "Where marks are lost",
          "whatif": "What changes if…", "explain": "Explain it back", "write": "Write it yourself"}


def to_map(cc: CourseContent, title: str, eyebrow: str) -> Content:
    """The structures reference/mindmap_build.py expects, so the layout and map stay the ported ones."""
    s = cc.settings
    cfg = {"tags": {}, "title": s.get("title") or title, "eyebrow": s.get("eyebrow") or eyebrow,
           "tagline": s.get("tagline", ""), "center": s.get("center", ""), "center-caption": s.get("center-caption", ""),
           "howto": s.get("howto", ""), "footer": s.get("footer", "")}
    cfg = {k: v for k, v in cfg.items() if v != ""} | {"tags": {}}
    clusters = [dict(id=c.id, name=c.name, kicker=c.kicker, desc=c.desc, color=c.color, ln=c.line) for c in cc.clusters]
    centre = s.get("center", "")
    nodes, edges = [], []
    for n in cc.nodes:
        tier = 1 if n.id == centre else int(n.attrs.get("tier") or TIER.get(n.weight, 2))
        nodes.append(dict(id=n.id, title=n.title, label=n.label, tier=tier, c=n.cluster,
                          facts=[dict(t=f.text, tags=[]) for f in n.facts], ln=n.line))
        edges += [dict(s=n.id, t=t, why=why, ln=ln) for t, why, ln in n.links]
    return Content(cfg, clusters, nodes, edges, [], [])


def _items(body: str) -> list[str]:
    out = []
    for ln in body.split("\n"):
        m = ITEM.match(ln)
        if m:
            out.append(m.group(1).strip())
        elif ln.startswith(("  ", "\t")) and ln.strip() and out:
            out[-1] += " " + ln.strip()
    return out


def _split(body: str) -> tuple[str, str, str]:
    lines = body.split("\n")
    fence = False
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("```"):
            fence = not fence
        m = None if fence else SPLIT.match(ln)
        if m:
            rest = "\n".join(([m.group(2)] if m.group(2) else []) + lines[i + 1:])
            return "\n".join(lines[:i]).strip(), m.group(1).capitalize(), rest.strip()
    return body.strip(), "", ""


def _section(key: str, name: str, body: str, attrs: dict) -> str:
    title = TITLES.get(key, name)
    src = f'<span class="src" title="{html.escape(attrs["src"])}">source</span>' if attrs.get("src") else ""
    head = f'<h4>{html.escape(title)}{src}</h4>'
    if key == "steps":
        items = _items(body)
        if items:
            lis = "".join(f"<li>{inline(i)}</li>" for i in items)
            return (f'<div class="sec steps-sec">{head}<ol class="steps">{lis}</ol>'
                    f'<div class="steps-ctl"><button class="btn" type="button" data-step="next">Next step</button>'
                    f'<button class="linkbtn" type="button" data-step="all">Show all</button></div></div>')
    if key == "conceptual":
        pairs = [i.split("::", 1) for i in _items(body)]
        if pairs and all(len(p) == 2 for p in pairs):
            cards = "".join(f'<details class="wcard"><summary>{inline(q.strip())}</summary><p>{inline(a.strip())}</p></details>'
                            for q, a in pairs)
            return f'<div class="sec">{head}<div class="wcards">{cards}</div></div>'
    if key in ("whatif", "misconceptions", "lookalikes"):
        pairs = [i.split("::", 1) for i in _items(body)]
        if pairs and all(len(p) == 2 for p in pairs):
            if key == "whatif":
                cards = "".join(f'<details class="wcard"><summary>{inline(q.strip())}</summary><p>{inline(a.strip())}</p></details>'
                                for q, a in pairs)
                return f'<div class="sec">{head}<div class="wcards">{cards}</div></div>'
            if key == "misconceptions":
                rows = "".join(f'<li><span class="no">✗ {inline(w.strip())}</span><span class="ok">✓ {inline(r.strip())}</span></li>'
                               for w, r in pairs)
                return f'<div class="sec">{head}<ul class="miscon">{rows}</ul></div>'
            rows = "".join(f"<tr><td>{inline(a.strip())}</td><td>{inline(b.strip())}</td></tr>" for a, b in pairs)
            return f'<div class="sec">{head}<div class="tblwrap"><table class="mini look">{rows}</table></div></div>'
    if key in ("pitfalls", "notes", "mnemonic"):
        items = _items(body)
        if items and len(items) * 2 > body.count("\n"):
            return f'<div class="sec">{head}<ul class="plainlist">' + "".join(f"<li>{inline(i)}</li>" for i in items) + "</ul></div>"
    if key == "formulas":
        items = _items(body)
        if items:
            return f'<div class="sec">{head}<ul class="formulas">' + "".join(f"<li><code>{html.escape(i)}</code></li>" for i in items) + "</ul></div>"
    if key in ("example", "variant", "write", "trace", "explain"):
        q, label, a = _split(body)
        if label:
            open_ = " open" if key == "example" else ""
            word = {"Model answer": "Model answer", "Answer": "Answer"}.get(label, "Solution")
            return (f'<div class="sec">{head}{block(q)}<details class="sol"{open_}><summary>{word}</summary>{block(a)}</details></div>')
    return f'<div class="sec">{head}{block(body)}</div>'


def lesson_html(n: Node) -> str:
    return "".join(_section(s.key, s.name, s.body, s.attrs) for s in n.sections if s.key != "links")


def content_data(cc: CourseContent) -> dict:
    """Per-node extras the template needs beyond the map: mode, weight, topic, fact sources, the lesson."""
    return dict(
        clusters=[c.id for c in cc.clusters],
        nodes={n.id: dict(mode=n.mode, weight=n.weight, topic=n.topic, cluster=n.cluster,
                          facts=[inline(f.text) for f in n.facts], srcs=[f.src for f in n.facts],
                          lesson=lesson_html(n)) for n in cc.nodes},
        order=[n.id for c in cc.clusters for n in cc.nodes if n.cluster == c.id],
    )
