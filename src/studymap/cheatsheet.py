"""`studymap cheatsheet`: a structured exam sheet, auto-fitted to the page budget (BRIEF section 9).

The sheet is not a list of facts. It is built from labelled blocks, in the order a student uses them:

    WHAT TO EXPECT   what the papers actually ask on this cluster, derived from analysis/papers.json
    KEY FORMULAS     what to memorise, boxed
    HOW TO SOLVE     the step template to copy in the exam
    DIAGRAM          the picture the paper asks you to draw
    PAST PAPER       a real question with the key's answer
    WORKED EXAMPLE   a problem solved step by step
    TRAP             where marks are lost
    LOOKALIKES       the pairs that get confused
    WHY IT WORKS     the reason, for the explain questions
    DERIVATION       where a formula comes from

Front matter (contents with real page numbers, HOW TO THINK) and back matter (master table, sanity
checks, notation decoder) come from the optional `content/sheet.md`.

Fitting: render with Chromium, binary-search the font size (6 pt floor, growing past 8 pt when the
budget has room, because these pages get printed 4-up), then drop the lowest-scored blocks if even
6 pt overflows. Everything dropped is listed in report.md. The finished PDF is checked for page
count, minimum font size and clipped text.
"""
from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from .content import CourseContent, Node
from .manifest import write_atomic
from .render.lessons import _items, _split
from .render.text import block as md_block
from .render.text import inline

MIN_PT = 4.0                   # hard floor (the brief says 6 pt; lowered at the user's request)
DEFAULT_MIN_PT = 4.5           # default: fit everything at the floor, like a hand-made sheet
LABEL_FLOOR = 3.3              # inline labels and captions may be smaller than the body text
GROW_PT = 11.0                 # grow past 8 pt when the budget has room: these pages get printed 4-up
FONTS = '"DejaVu Sans Condensed", "Liberation Sans Narrow", "Nimbus Sans Narrow", "Arial Narrow", sans-serif'
MONO = '"DejaVu Sans Mono", "Liberation Mono", monospace'

# section key -> (printed label, css class, score). Score x the node's weight orders what survives a squeeze.
SPEC = {
    "formulas":       ("KEY FORMULAS", "key", 100),
    "steps":          ("HOW TO SOLVE", "how", 94),
    "diagram":        ("DIAGRAM", "dia", 86),
    "pitfalls":       ("TRAP", "trap", 72),
    "lookalikes":     ("LOOKALIKES", "look", 70),
    "example":        ("WORKED EXAMPLE", "ex", 66),
    "misconceptions": ("NOT", "trap", 56),
    "core":           ("", "why", 52),
    "why":            ("WHY IT WORKS", "why", 50),
    "derivation":     ("DERIVATION", "deriv", 48),
    "code":           ("CODE", "code", 46),
    "whatif":         ("WHAT CHANGES IF", "wif", 44),
    "conceptual":     ("CONCEPT Q", "conq", 74),
    "variant":        ("VARIANT", "ex", 34),
    "trace":          ("TRACE IT", "ex", 33),
    "write":          ("WRITE IT", "ex", 32),
    "mnemonic":       ("MNEMONIC", "key", 60),
    "explain":        ("EXPLAIN IT BACK", "why", 22),
}
FACT_SCORE = {"high": 82, "med": 62, "low": 40}
PASTQ_SCORE = 64
WEIGHT = {"high": 1.0, "med": 0.82, "low": 0.62}
LEGEND = [("KEY FORMULAS", "what to memorise"), ("HOW TO SOLVE", "the steps to copy in the exam"),
          ("DIAGRAM", "the picture you are asked to draw"), ("PAST PAPER", "a real question + the key's answer"),
          ("CONCEPT Q", "the conceptual questions this course likes"), ("TRAP", "where marks are lost"),
          ("WHY IT WORKS", "the reason, for the explain questions")]


# page geometry, for sizing diagrams that cannot wrap
MM = 2.834645
PAGE_W, SIDE_MARGIN, COL_GAP = 210 * MM, 6 * MM, 2.4 * MM
CHAR_W = 0.602                 # DejaVu Sans Mono advance, in em
MIN_DIA_PT = 6.0               # below this a diagram is promoted to a full-width band


def _col_width(columns: int) -> float:
    return (PAGE_W - 2 * SIDE_MARGIN - (columns - 1) * COL_GAP) / columns


def _pre_chars(h: str) -> int:
    """Longest line of the block's <pre> text: ASCII diagrams cannot wrap, so this sets the font size."""
    return max((len(ln) for m in re.findall(r"<pre[^>]*>(.*?)</pre>", h, re.S)
                for ln in html.unescape(m).split("\n")), default=0)


@dataclass
class Block:
    kind: str
    label: str
    html: str
    text: str          # what it renders as, for the clipping check
    score: float
    where: str         # for the dropped list
    pre_chars: int = 0


@dataclass
class Part:
    """A cluster, or a front/back section of the sheet."""
    id: str
    title: str
    kicker: str = ""
    intro: str = ""
    groups: list[tuple[str, list[Block]]] = field(default_factory=list)   # (node label, blocks)
    span: bool = False                                                    # full width


@dataclass
class CheatResult:
    pdf: Path
    pdf4: Path
    pages: int
    budget: int
    font_pt: float
    kept: int
    dropped: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    min_font: float = 0.0
    body_font: float = 0.0
    floor: float = MIN_PT
    missing: list[str] = field(default_factory=list)


def _plain(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[*`]", "", s)).strip()


def _probe(h: str) -> str:
    return _plain(html.unescape(re.sub(r"<[^>]+>", " ", h)))


def _pairs(body: str) -> list[tuple[str, str]]:
    out = []
    for row in _items(body):
        a, sep, b = row.partition("::")
        if sep:
            out.append((a.strip(), b.strip()))
    return out


def _example_html(body: str) -> str:
    q, label, a = _split(body)
    if not label:
        return md_block(body)
    return f'{md_block(q)}<div class="sol"><b>{html.escape(label)}.</b> {md_block(a)}</div>'


def node_blocks(n: Node, pastq: list[dict]) -> list[Block]:
    w = WEIGHT.get(n.weight, 0.6)
    out: list[Block] = []

    def add(key, h, text=None, score=None, label=None, kind=None):
        """text is ignored: the clipping probe always comes from what the block renders as."""
        lab, cls, sc = SPEC.get(key, ("", "plain", 30))
        out.append(Block(kind or cls, lab if label is None else label, h, _probe(h),
                         (sc if score is None else score) * w,
                         f"{n.label}: {(label or lab or key).lower()}"))

    for s in n.sections_of("formulas"):
        if (items := _items(s.body)):
            add("formulas", "".join(f'<span class="f">{html.escape(f)}</span>' for f in items))
    for s in n.sections_of("steps"):
        if (items := _items(s.body)):
            add("steps", '<ol class="st">' + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ol>")
    for s in n.sections_of("diagram"):
        h = md_block(s.body)
        add("diagram", h)
        out[-1].pre_chars = _pre_chars(h)
    if n.facts:
        fh = "".join(f"<p>{inline(f.text)}</p>" for f in n.facts)
        out.append(Block("fact", "", fh, _probe(fh), FACT_SCORE.get(n.weight, 40) * w, f"{n.label}: facts"))
    for q in pastq[:1]:
        h = (f'<p><b>{html.escape(q["label"])}</b> {q["stem"]}</p>'
             + (f'<div class="sol"><b>Answer.</b> {q["answer"]}</div>' if q["answer"] else ""))
        add("example", h, _plain(_probe(q["stem"]) + " " + _probe(q["answer"])), PASTQ_SCORE,
            label="PAST PAPER", kind="past")
    for key in ("example", "variant", "trace", "write"):
        for s in n.sections_of(key):
            add(key, _example_html(s.body))
    for s in n.sections_of("pitfalls"):
        if (items := _items(s.body)):
            add("pitfalls", "".join(f'<span class="tr">{inline(i)}</span>' for i in items))
    for s in n.sections_of("lookalikes"):
        if (ps := _pairs(s.body)):
            add("lookalikes", "".join(f"<p><b>{inline(a)}</b> — {inline(b)}</p>" for a, b in ps))
    for s in n.sections_of("misconceptions"):
        if (ps := _pairs(s.body)):
            add("misconceptions", "".join(f'<p>✗ {inline(a)} &nbsp; ✓ <b>{inline(b)}</b></p>' for a, b in ps))
    for s in n.sections_of("conceptual"):
        if (ps := _pairs(s.body)):
            add("conceptual", "".join(f'<p><b>Q.</b> {inline(a)} <b>A.</b> {inline(b)}</p>' for a, b in ps))
    for s in n.sections_of("whatif"):
        if (ps := _pairs(s.body)):
            add("whatif", "".join(f"<p><b>{inline(a)}</b> → {inline(b)}</p>" for a, b in ps))
    for s in n.sections_of("explain"):
        q, lab, a = _split(s.body)
        add("explain", f"<p>{inline(_plain(q))}</p>" + (f'<div class="sol">{md_block(a)}</div>' if a else ""))
    for key in ("core", "why", "derivation", "code", "mnemonic"):
        for s in n.sections_of(key):
            add(key, md_block(s.body))
    return out


# --------------------------------------------------------------------------- what the papers ask

TYPE_WORD = {"long-explain": "explain", "code-write": "write code", "code-trace": "trace code",
             "code-fix": "fix code", "short": "short answer", "mcq": "MCQ"}
WHY = {"apply": "you must do it on fresh numbers, so practise the steps",
       "understand": "the marks are in the reason, not the definition",
       "recall": "state it exactly; no working needed"}


def expectations(cluster_id: str, nodes: list[Node], analysis) -> str:
    """WHAT TO EXPECT IN THE EXAM: the real questions asked on this cluster, and the patterns they fit."""
    if analysis is None or analysis.papers is None:
        return ""
    topics = {n.topic for n in nodes if n.cluster == cluster_id and n.topic}
    labels = {n.topic: n.label for n in nodes if n.topic}
    papers = {p.id: p for p in analysis.papers.papers}
    qs = sorted((q for q in analysis.papers.questions if set(q.topics) & topics),
                key=lambda q: (-(q.marks or 0), q.id))
    if not qs:
        return ""
    rows = []
    for q in qs[:6]:
        p = papers[q.paper]
        when = (f"{p.year} {p.exam}" if p.year else "sample") + (f" [{q.marks:g}]" if q.marks is not None else "")
        stem = _plain(re.sub(r"```.*?```", " (code) ", q.text, flags=re.S))
        if len(stem) > 150:
            stem = stem[:147].rsplit(" ", 1)[0] + "…"
        topic = next((labels.get(t) for t in q.topics if t in topics), "")
        rows.append(f'<span class="ex-row">▶ <i>{inline(stem)}</i> ⇒ <b>{inline(topic or "")}</b>, '
                    f'{html.escape(TYPE_WORD.get(q.type, q.type))} ({html.escape(when)}). '
                    f'<span class="muted">Why: {html.escape(WHY.get(q.mode, ""))}.</span></span>')
    qids = {q.id for q in qs}
    pats = [f'<span class="ex-row">● {inline(p.text)}</span>'
            for p in analysis.papers.patterns if set(p.questions) & qids]
    return "".join(rows + pats[:2])


def _past_by_topic(analysis) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    if analysis is None or analysis.papers is None:
        return out
    papers = {p.id: p for p in analysis.papers.papers}
    for q in sorted(analysis.papers.questions, key=lambda q: -(q.marks or 0)):
        p = papers[q.paper]
        label = (f"{p.year} {p.exam} Q{q.number}" if p.year else f"sample Q{q.number}") + \
                (f" [{q.marks:g}]" if q.marks is not None else "")
        item = dict(label=label, stem=md_block(q.text), answer=md_block(q.answer.text) if q.answer else "")
        for t in q.topics:
            out.setdefault(t, []).append(item)
    return out


# --------------------------------------------------------------------------- the document

def collect(cc: CourseContent, analysis=None, columns: int = 4) -> list[Part]:
    parts: list[Part] = []
    extra = getattr(cc, "sheet", {}) or {}
    if (ht := extra.get("how to think")):
        parts.append(Part("how-to-think", "How to think: choosing the method", intro=md_block(ht), span=True))
    pastq = _past_by_topic(analysis)
    for c in cc.clusters:
        nodes = [n for n in cc.nodes if n.cluster == c.id]
        if not nodes:
            continue
        p = Part(c.id, c.name, c.kicker, expectations(c.id, cc.nodes, analysis))
        wide: list[tuple[str, list[Block]]] = []
        for n in nodes:
            blocks = node_blocks(n, pastq.get(n.topic, []))
            if not blocks:
                continue
            # a diagram too wide for one column becomes a full-width band after the cluster, so it stays legible
            narrow = [b for b in blocks if not (b.pre_chars and b.pre_chars * CHAR_W * MIN_DIA_PT > _col_width(columns))]
            for b in blocks:
                if b not in narrow:
                    wide.append((n.label, [b]))
            if narrow:
                p.groups.append((n.label, narrow))
        parts.append(p)
        if wide:
            parts.append(Part(c.id + "-dia", f"{c.name}: diagrams", groups=wide, span=True))
    for key, title, span in (("master table", "Master table: what the question says → what to do", True),
                             ("sanity checks", "Sanity checks before you hand in", False),
                             ("notation", "Notation decoder", False)):
        if (body := extra.get(key)):
            parts.append(Part(key.replace(" ", "-"), title, intro=md_block(body), span=span))
    return parts


def document(parts: list[Part], keep: set[int], font_pt: float, title: str, columns: int,
             toc: dict[str, int] | None) -> str:
    lh = 1.12 + (font_pt - MIN_PT) * 0.012
    legend = " · ".join(f'<span class="lg"><span class="lab">{a}</span> {b}</span>' for a, b in LEGEND)
    contents = ""
    if toc is not None:
        contents = '<div class="toc">' + "".join(
            f'<span class="tr2">{html.escape(p.title)} <b>p.{toc.get(p.id, 1)}</b></span>'
            for p in parts if not p.id.endswith("-dia")) + "</div>"
    body = [f'<div class="head"><h1>{html.escape(title)} — exam cheat sheet</h1>'
            f'<div class="legend">{legend}</div>{contents}</div>']
    idx = 0
    for p in parts:
        inner = []
        for label, blocks in p.groups:
            kept = []
            for b in blocks:
                if idx in keep:
                    lab = f'<span class="lab {b.kind}">{html.escape(b.label)}</span>' if b.label else ""
                    h = b.html
                    if b.pre_chars:        # size the diagram so its longest line fits the width it has
                        avail = (PAGE_W - 2 * SIDE_MARGIN) if p.span else _col_width(columns)
                        size = max(MIN_PT, min(font_pt * 0.95, avail * 0.97 / (b.pre_chars * CHAR_W)))
                        h = h.replace("<pre>", f'<pre style="font-size:{size:.2f}pt">')
                    kept.append(f'<div class="b {b.kind}">{lab}{h}</div>')
                idx += 1
            if kept:
                inner.append(f'<div class="nd"><h3>{html.escape(label)}</h3>{"".join(kept)}</div>')
        if not inner and not p.intro:
            continue
        intro = f'<div class="expect">{p.intro}</div>' if p.intro else ""
        body.append(f'<div class="{"part span" if p.span else "part"}">'
                    f'<h2>{(html.escape(p.kicker) + " · ") if p.kicker else ""}{html.escape(p.title)}</h2>'
                    f'{intro}{"".join(inner)}</div>')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{html.escape(title)} cheat sheet</title><style>
@page {{ size: A4; }}
html {{ font-size: {font_pt:.2f}pt; }}
body {{ margin: 0; font-family: {FONTS}; line-height: {lh:.3f}; color: #000; background: #fff;
  overflow-wrap: break-word; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
.sheet {{ column-count: {columns}; column-gap: 2.4mm; column-rule: .3pt solid #aaa; column-fill: auto; }}
h1 {{ font-size: 1.25em; margin: 0 0 .25em; }}
.head {{ column-span: all; border-bottom: 1pt solid #000; padding-bottom: .25em; margin-bottom: .35em; }}
.legend {{ font-size: .92em; }}
.lg {{ margin-right: .7em; }}
.toc {{ margin-top: .3em; column-count: {max(2, columns - 1)}; column-gap: 3mm; font-size: .95em; }}
.tr2 {{ display: block; break-inside: avoid; }}
.part.span {{ column-span: all; }}
h2 {{ font-size: 1.05em; margin: .5em 0 .15em; padding: .08em .35em; background: #000; color: #fff;
  break-after: avoid; break-inside: avoid; }}
h3 {{ font-size: 1em; margin: .3em 0 .08em; border-bottom: .4pt solid #666; break-after: avoid; }}
.nd > h3 + .b {{ break-before: avoid; }}
.b {{ margin: 0 0 .18em; }}                       /* long blocks may flow across columns */
.b.key, .b.dia, .b.look, .b.trap {{ break-inside: avoid; }}   /* short structured ones must not */
.b p {{ margin: 0 0 .12em; }}
.lab {{ display: inline-block; font-size: .82em; font-weight: 700; padding: 0 .25em; margin-right: .25em;
  background: #ddd; }}
.lab.key, .lab.how, .lab.trap, .lab.dia, .lab.conq {{ background: #000; color: #fff; }}
.lab.past {{ background: #444; color: #fff; }}
.b.key, .b.how, .b.past, .b.ex, .b.dia, .b.conq {{ border-left: 1.2pt solid #000; padding-left: .3em; }}
.b.trap {{ border-left: 1.2pt solid #888; padding-left: .3em; }}
.f {{ display: block; border: .5pt solid #000; padding: .05em .3em; margin-bottom: .1em; font-family: {MONO};
  font-size: .9em; }}
ol.st {{ margin: 0; padding-left: 1.35em; }}
ol.st li {{ margin-bottom: .04em; }}
.tr {{ display: block; padding-left: .9em; text-indent: -.9em; }}
.tr::before {{ content: "⚠ "; }}
.sol {{ border-left: 1pt solid #999; padding-left: .3em; margin-top: .1em; }}
.expect {{ background: #eee; padding: .2em .35em; margin-bottom: .25em; break-inside: avoid; }}
.ex-row {{ display: block; padding-left: .9em; text-indent: -.9em; margin-bottom: .1em; }}
.muted {{ color: #444; }}
code {{ font-family: {MONO}; font-size: .92em; }}
pre {{ font-family: {MONO}; font-size: .86em; margin: .1em 0; white-space: pre-wrap; overflow-wrap: break-word;
  border-left: 1pt solid #000; padding-left: .3em; line-height: 1.08; }}
.b.dia pre {{ border-left: 0; padding-left: 0; white-space: pre; overflow-wrap: normal; }}
table {{ border-collapse: collapse; font-size: .92em; width: 100%; }}
th, td {{ border: .4pt solid #666; padding: .05em .25em; text-align: left; vertical-align: top; }}
th {{ background: #eee; }}
@media screen {{ body {{ padding: 8px 10px; }} .sheet {{ column-fill: balance; }} }}
</style></head><body><div class="sheet">{''.join(body)}</div></body></html>"""


# --------------------------------------------------------------------------- fitting and output

def _pages(pdf: bytes) -> int:
    with pymupdf.open(stream=pdf, filetype="pdf") as d:
        return d.page_count


def build(cc: CourseContent, out_dir: Path, title: str, pages: int = 8, columns: int = 4,
          analysis=None, weightage: dict | None = None, min_pt: float = DEFAULT_MIN_PT) -> CheatResult:
    from playwright.sync_api import sync_playwright

    from .check import launch
    parts = collect(cc, analysis, columns)
    blocks = [b for p in parts for _, g in p.groups for b in g]
    order = sorted(range(len(blocks)), key=lambda i: (-blocks[i].score, i))
    header = ('<div style="font-family:sans-serif;font-size:7pt;width:100%;margin:0 6mm;'
              'display:flex;justify-content:space-between;color:#000">'
              f'<span>{html.escape(title)} — cheat sheet</span>'
              '<span>page <span class="pageNumber"></span> of <span class="totalPages"></span></span></div>')
    with sync_playwright() as p:
        browser, _ = launch(p)
        page = browser.new_page()

        def render(fs: float, keep: set[int], toc=None) -> bytes:
            page.set_content(document(parts, keep, fs, title, columns, toc), wait_until="load")
            return page.pdf(format="A4", margin=dict(top="9mm", bottom="6mm", left="6mm", right="6mm"),
                            print_background=True, display_header_footer=True,
                            header_template=header, footer_template="<span></span>")
        allk = set(range(len(blocks)))
        floor = max(MIN_PT, min_pt)
        fits = lambda fs, keep, toc=None: _pages(render(fs, keep, toc)) <= pages
        if not fits(floor, allk):
            # keep it readable and drop the lowest-scored blocks instead of shrinking below the floor
            a, b = 0, len(blocks)
            while a < b:
                mid = (a + b + 1) // 2
                if fits(floor, set(order[:mid])):
                    a = mid
                else:
                    b = mid - 1
            fs, keep = floor, set(order[:a])
        else:
            lo, hi = floor, GROW_PT
            while hi - lo > 0.1:
                mid = round((lo + hi) / 2, 2)
                if fits(mid, allk):
                    lo = mid
                else:
                    hi = mid
            fs, keep = lo, allk
        pdf = render(fs, keep)                       # second pass: real page numbers in the contents
        toc = _toc_pages(pdf, parts)
        if (pdf2 := render(fs, keep, toc)) and _pages(pdf2) <= pages:
            pdf = pdf2
            if (toc2 := _toc_pages(pdf, parts)) != toc:     # the contents shifted the flow: settle once
                if _pages(p3 := render(fs, keep, toc2)) <= pages:
                    pdf, toc = p3, toc2
        else:
            toc = None
        html_doc = document(parts, keep, fs, title, columns, toc)
        browser.close()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "cheatsheet.pdf"
    with pymupdf.open(stream=pdf, filetype="pdf") as d:
        d.set_metadata({"title": f"{title} cheat sheet", "producer": "studymap", "creator": "studymap"})
        d.save(target, garbage=3, deflate=True, no_new_id=True)
    write_atomic(out_dir / "cheatsheet.html", html_doc)
    res = CheatResult(target, out_dir / "cheatsheet-4up.pdf", _pages(target.read_bytes()), pages, fs, len(keep),
                      dropped=[blocks[i].where for i in sorted(set(range(len(blocks))) - keep)], floor=floor)
    _qa(res, [blocks[i] for i in sorted(keep)])
    _four_up(target, res.pdf4)
    write_atomic(out_dir / "cheatsheet.json", json.dumps(
        dict(pages=res.pages, budget=pages, font_pt=fs, body_font=res.body_font, kept=res.kept,
             dropped=res.dropped, min_font=res.min_font, missing=res.missing, problems=res.problems), indent=1) + "\n")
    return res


def _toc_pages(pdf: bytes, parts: list[Part]) -> dict[str, int]:
    """Which page each part starts on. Headings are the white-on-black spans, so the contents
    listing (black text, same words) can never be mistaken for the heading itself."""
    out: dict[str, int] = {}
    heads = []
    with pymupdf.open(stream=pdf, filetype="pdf") as d:
        for pg in d:
            white = [sp["text"] for b in pg.get_text("dict")["blocks"] for ln in b.get("lines", [])
                     for sp in ln["spans"] if sp.get("color") == 0xFFFFFF]
            heads.append(re.sub(r"\s+", " ", " ".join(white)))
    for part in parts:
        needle = re.sub(r"\s+", " ", part.title)[:40]
        out[part.id] = next((i for i, t in enumerate(heads, 1) if needle and needle in t), 1)
    return out


def _qa(res: CheatResult, kept: list[Block]) -> None:
    with pymupdf.open(res.pdf) as d:
        sizes, text = [], []
        for pg in d:
            top, bottom = 22.0, pg.rect.height - 12.0      # Chrome draws the running header in the margin
            for b in pg.get_text("dict")["blocks"]:
                for ln in b.get("lines", []):
                    for sp in ln["spans"]:
                        if sp["text"].strip() and top <= sp["bbox"][1] and sp["bbox"][3] <= bottom:
                            sizes.append(sp["size"])
            text.append(pg.get_text())
    res.min_font = round(min(sizes), 2) if sizes else 0.0
    from collections import Counter
    res.body_font = round(Counter(round(x, 1) for x in sizes).most_common(1)[0][0], 2) if sizes else 0.0
    letters = lambda s: re.sub(r"[^a-zA-Z]", "", s)
    flat = letters("".join(text))
    for b in kept:
        t = letters(b.text)
        # clipping removes the END of a block, so that is the probe; the start is the fallback
        if len(t) >= 12 and t[-20:] not in flat and t[:20] not in flat:
            res.missing.append(b.where)
    if res.pages > res.budget:
        res.problems.append(f"{res.pages} pages, budget {res.budget}")
    if res.body_font < res.floor - 0.05:
        res.problems.append(f"body text {res.body_font} pt is under {res.floor} pt")
    if res.min_font < LABEL_FLOOR - 0.05:
        res.problems.append(f"smallest text {res.min_font} pt is under {LABEL_FLOOR} pt")
    if res.missing:
        res.problems.append(f"{len(res.missing)} blocks not found in the PDF text (clipped?)")


def _four_up(src: Path, dest: Path) -> None:
    """4 pages per side, so an 8-page budget prints on one A4 sheet, both sides."""
    with pymupdf.open(src) as s, pymupdf.open() as d:
        w, h = s[0].rect.width, s[0].rect.height
        for i in range(0, s.page_count, 4):
            pg = d.new_page(width=w, height=h)
            for k in range(min(4, s.page_count - i)):
                x, y = (k % 2) * w / 2, (k // 2) * h / 2
                pg.show_pdf_page(pymupdf.Rect(x, y, x + w / 2, y + h / 2), s, i + k)
        d.set_metadata({"title": "cheat sheet, 4 pages per side", "producer": "studymap", "creator": "studymap"})
        d.save(dest, garbage=3, deflate=True, no_new_id=True)
