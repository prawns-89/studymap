"""The content model (FORMAT.md): Markdown per cluster, parsed and validated with file:line problems."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .course import display_path
from .issues import Issue

ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
MODES = ("recall", "understand", "apply")
WEIGHTS = ("high", "med", "low")
SECTIONS = {
    "core idea": "core", "why it works": "why", "derivation": "derivation", "misconceptions": "misconceptions",
    "what changes if": "whatif", "explain it back": "explain",
    "steps": "steps", "worked example": "example", "variant": "variant", "where marks are lost": "pitfalls",
    "code": "code", "trace": "trace", "write it": "write",
    "formulas": "formulas", "mnemonic": "mnemonic", "lookalikes": "lookalikes", "links": "links", "notes": "notes",
    "diagram": "diagram", "conceptual questions": "conceptual", "conceptual": "conceptual",
}
APPLY_NEEDS = (("example", "Worked example"), ("variant", "Variant"), ("pitfalls", "Where marks are lost"))
SRC = re.compile(r"\s*\{src:\s*([^{}]+)\}\s*$")
ATTRS = re.compile(r"\s*\{(\w+):\s*([^{}]*)\}\s*$")
FENCE = re.compile(r"^\s*(`{3,})")


@dataclass
class Fact:
    text: str
    src: list[str]
    line: int


@dataclass
class Section:
    key: str
    name: str
    attrs: dict[str, str]
    body: str
    line: int


@dataclass
class Node:
    id: str
    title: str
    label: str
    cluster: str
    file: str
    line: int
    attrs: dict[str, str] = field(default_factory=dict)
    facts: list[Fact] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    links: list[tuple[str, str, int]] = field(default_factory=list)
    # resolved by validate()
    mode: str = ""
    weight: str = ""
    topic: str = ""

    def section(self, key: str) -> Section | None:
        return next((s for s in self.sections if s.key == key), None)

    def sections_of(self, key: str) -> list[Section]:
        """Every section with this key, in file order: a node may repeat one (two worked examples, say)."""
        return [s for s in self.sections if s.key == key]


@dataclass
class Cluster:
    id: str
    name: str
    kicker: str
    desc: str
    order: int
    color: int | None
    file: str
    line: int


@dataclass
class CourseContent:
    dir: Path
    settings: dict
    sheet: dict = field(default_factory=dict)      # content/sheet.md: how to think, master table, sanity, notation
    clusters: list[Cluster] = field(default_factory=list)
    nodes: list[Node] = field(default_factory=list)
    files: list[Path] = field(default_factory=list)
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)


SHEET_SECTIONS = ("how to think", "master table", "sanity checks", "notation")


def is_markdown_content(d: Path) -> bool:
    return d.is_dir() and any(p.suffix == ".md" and p.name not in ("course.md", "sheet.md") for p in d.iterdir())


def parse_sheet(text: str, shown: str, errors: list[Issue]) -> dict[str, str]:
    """content/sheet.md: '## <name>' sections whose bodies go at the front and back of the cheat sheet."""
    lines = text.split("\n")
    _, start = _front(lines, shown, errors)
    out, name, buf = {}, "", []
    for ln, raw in enumerate(lines[start:], start + 1):
        if raw.startswith("## "):
            if name:
                out[name] = "\n".join(buf).strip("\n")
            name, buf = raw[3:].strip().lower(), []
            if name not in SHEET_SECTIONS:
                errors.append(Issue(shown, ln, f"unknown sheet section {raw[3:].strip()!r} "
                                               f"(use: {', '.join(SHEET_SECTIONS)})"))
        elif name:
            buf.append(raw)
        elif raw.strip():
            errors.append(Issue(shown, ln, "text before the first ## section"))
    if name:
        out[name] = "\n".join(buf).strip("\n")
    return out


def _front(lines: list[str], fname: str, errors: list[Issue]) -> tuple[dict, int]:
    if not lines or lines[0].strip() != "---":
        return {}, 0
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            try:
                data = yaml.safe_load("\n".join(lines[1:i])) or {}
            except yaml.YAMLError as e:
                mark = getattr(e, "problem_mark", None)
                errors.append(Issue(fname, (mark.line + 2) if mark else 1, f"front matter: {getattr(e, 'problem', e)}"))
                data = {}
            if not isinstance(data, dict):
                errors.append(Issue(fname, 1, "front matter must be key: value lines"))
                data = {}
            return data, i + 1
    errors.append(Issue(fname, 1, "front matter starts with --- but never ends"))
    return {}, len(lines)


def _heading(text: str):
    """'id | Title | Label | k=v k=v' -> (id, title, label, attrs)."""
    parts = [p.strip() for p in text.split("|")]
    attrs, bad = {}, []
    if len(parts) > 1 and "=" in parts[-1]:
        for tok in parts.pop().split():
            k, eq, v = tok.partition("=")
            if eq:
                attrs[k] = v.strip('"')
            else:
                bad.append(tok)
    nid = parts[0] if parts else ""
    title = parts[1] if len(parts) > 1 else ""
    label = parts[2] if len(parts) > 2 else ""
    return nid, title, label, attrs, bad


def parse_file(path: Path, shown: str, errors: list[Issue]) -> tuple[Cluster | None, list[Node]]:
    lines = path.read_text(encoding="utf-8").split("\n")
    front, start = _front(lines, shown, errors)
    cluster = None
    if front:
        cid = str(front.get("cluster", "")).strip()
        if not cid or not ID.match(cid):
            errors.append(Issue(shown, 2, f"front matter: cluster id {cid!r} must be a-z, 0-9 and -"))
        if not front.get("name"):
            errors.append(Issue(shown, 2, "front matter: name is required"))
        color = front.get("color")
        if color is not None and not (isinstance(color, int) and 0 <= color <= 11):
            errors.append(Issue(shown, 2, f"front matter: color {color!r} must be 0 to 11"))
            color = None
        unknown = set(front) - {"cluster", "name", "kicker", "order", "desc", "color"}
        for k in sorted(unknown):
            errors.append(Issue(shown, 2, f"front matter: unknown key {k!r}"))
        cluster = Cluster(cid, str(front.get("name", "")), str(front.get("kicker", "") or ""), str(front.get("desc", "") or ""),
                          int(front.get("order", 0) or 0), color, shown, 1)
    elif any(ln.startswith("## ") for ln in lines):
        errors.append(Issue(shown, 1, "a cluster file starts with front matter (--- cluster: ... name: ... ---)"))
    nodes: list[Node] = []
    node = sec = None
    sec_lines: list[str] = []
    fence = ""

    def close_section():
        nonlocal sec, sec_lines
        if sec is not None:
            sec.body = "\n".join(sec_lines).strip("\n")
            if sec.key == "links":
                for k, raw in enumerate(sec_lines):
                    s = raw.strip()
                    if not s:
                        continue
                    if not s.startswith("- ") or "|" not in s:
                        errors.append(Issue(shown, sec.line + 1 + k, "a link is '- <node-id> | why'"))
                        continue
                    tgt, _, why = s[2:].partition("|")
                    node.links.append((tgt.strip(), why.strip(), sec.line + 1 + k))
        sec, sec_lines = None, []

    for ln, raw in enumerate(lines[start:], start + 1):
        s = raw.rstrip()
        m = FENCE.match(s)
        if fence:
            if m and m.group(1) == fence and s.strip() == fence:
                fence = ""
            if sec is not None:
                sec_lines.append(s)
            continue
        if m:
            fence = m.group(1)
            if sec is None:
                errors.append(Issue(shown, ln, "code outside a section: put it under a ### heading"))
            else:
                sec_lines.append(s)
            continue
        if s.startswith("## "):
            close_section()
            nid, title, label, attrs, bad = _heading(s[3:])
            if not ID.match(nid or "-"):
                errors.append(Issue(shown, ln, f"node id {nid!r} must be a-z, 0-9 and -"))
            if not title:
                errors.append(Issue(shown, ln, "a node heading is '## id | Title | Label | key=value'"))
            for b in bad:
                errors.append(Issue(shown, ln, f"can't read attribute {b!r}: use key=value"))
            node = Node(nid, title, label or title, cluster.id if cluster else "", shown, ln, attrs)
            nodes.append(node)
        elif s.startswith("### "):
            close_section()
            if node is None:
                errors.append(Issue(shown, ln, "section before any ## node"))
                continue
            name, attrs = s[4:].strip(), {}
            while (am := ATTRS.search(name)):
                attrs[am.group(1)] = am.group(2).strip()
                name = name[: am.start()].rstrip()
            key = SECTIONS.get(name.lower().rstrip("?.… ").strip())
            if key is None:
                errors.append(Issue(shown, ln, f"unknown section {name!r} (see FORMAT.md)"))
                key = "notes"
            sec = Section(key, name, attrs, "", ln)
            node.sections.append(sec)
        elif sec is not None:
            sec_lines.append(s)
        elif node is None:
            if s.strip():
                errors.append(Issue(shown, ln, "text before the first ## node"))
        elif s.startswith("- "):
            t, src = s[2:].strip(), []
            mm = SRC.search(t)
            if mm:
                src = [r.strip() for r in mm.group(1).split(";") if r.strip()]
                t = t[: mm.start()].rstrip()
            node.facts.append(Fact(t, src, ln))
        elif s.startswith(("  ", "\t")) and s.strip() and node.facts:
            f = node.facts[-1]
            t = f.text + " " + s.strip()
            mm = SRC.search(t)
            if mm:
                f.src += [r.strip() for r in mm.group(1).split(";") if r.strip()]
                t = t[: mm.start()].rstrip()
            f.text = t
        elif s.strip():
            errors.append(Issue(shown, ln, "text under a node must be a '- ' fact or go under a ### section"))
    close_section()
    if fence:
        errors.append(Issue(shown, len(lines), "a ``` code block is never closed"))
    return cluster, nodes


def load(content_dir: Path) -> CourseContent:
    errors: list[Issue] = []
    shown = lambda p: str(display_path(p))
    settings = {}
    cm = content_dir / "course.md"
    if cm.exists():
        settings, _ = _front(cm.read_text(encoding="utf-8").split("\n"), shown(cm), errors)
    sheet: dict[str, str] = {}
    sp = content_dir / "sheet.md"
    if sp.exists():
        sheet = parse_sheet(sp.read_text(encoding="utf-8"), shown(sp), errors)
    files = sorted(p for p in content_dir.glob("*.md") if p.name not in ("course.md", "sheet.md"))
    clusters, nodes = [], []
    for k, p in enumerate(files):
        c, ns = parse_file(p, shown(p), errors)
        if c:
            if not c.order:
                c.order = k + 1
            clusters.append(c)
        nodes += ns
    clusters.sort(key=lambda c: (c.order, c.id))
    return CourseContent(content_dir, settings, sheet, clusters, nodes,
                         ([cm] if cm.exists() else []) + ([sp] if sp.exists() else []) + files, errors)


def validate(cc: CourseContent, analysis=None, weightage: dict | None = None, corpus=None) -> None:
    """Resolve each node's topic, mode and weight, and check everything against the analysis and the corpus."""
    E = lambda f, ln, m: cc.errors.append(Issue(f, ln, m))
    W = lambda f, ln, m: cc.warnings.append(Issue(f, ln, m))
    topics = {t.id: t for t in analysis.topics.topics} if analysis and analysis.topics else {}
    trow = {t["id"]: t for t in weightage["topics"]} if weightage else {}
    corpus = corpus or (analysis.corpus if analysis else None)
    qnums = {}
    if analysis and analysis.papers:
        pp = {p.id: p.path for p in analysis.papers.papers}
        qnums = {(pp[q.paper], q.number.lower().lstrip("q")) for q in analysis.papers.questions}
    seen: dict[str, Node] = {}
    cids = {}
    for c in cc.clusters:
        if c.id in cids:
            E(c.file, 2, f"cluster {c.id!r} is also defined in {cids[c.id]}")
        cids[c.id] = c.file
    if cc.nodes and not 2 <= len(cc.clusters) <= 12:
        E(str(display_path(cc.dir)), 0, f"{len(cc.clusters)} clusters: use 2 to 12")
    for n in cc.nodes:
        if n.id in seen:
            E(n.file, n.line, f"duplicate node id {n.id!r} (first in {seen[n.id].file}:{seen[n.id].line})")
        seen[n.id] = n
        for k in n.attrs:
            if k not in ("mode", "weight", "topic", "tier"):
                E(n.file, n.line, f"unknown attribute {k!r} (mode, weight, topic, tier)")
        n.topic = n.attrs.get("topic", n.id if n.id in topics else "")
        if "topic" in n.attrs and topics and n.topic not in topics:
            E(n.file, n.line, f"topic {n.topic!r} is not in analysis/topics.json")
        row = trow.get(n.topic, {})
        n.mode = n.attrs.get("mode") or row.get("mode") or ""
        n.weight = n.attrs.get("weight") or row.get("weight") or ""
        if n.mode not in MODES:
            E(n.file, n.line, f"mode {n.mode!r}: set mode=recall|understand|apply" if n.mode else
              f"node {n.id}: no mode (its topic was never asked): set mode=recall|understand|apply")
        if n.weight and n.weight not in WEIGHTS:
            E(n.file, n.line, f"weight {n.weight!r}: use high, med or low")
        n.weight = n.weight if n.weight in WEIGHTS else "low"
        if n.attrs.get("tier") and n.attrs["tier"] not in ("1", "2", "3"):
            E(n.file, n.line, f"tier {n.attrs['tier']!r}: use 1, 2 or 3")
        if not n.facts:
            E(n.file, n.line, f"node {n.id} has no facts")
        for f in n.facts:
            if not f.src:
                W(n.file, f.line, "fact without a {src: ...}")
            for ref in f.src:
                _check_ref(ref, corpus, qnums, lambda m, ln=f.line: E(n.file, ln, m))
        for s in n.sections:
            if "src" in s.attrs:
                for ref in s.attrs["src"].split(";"):
                    _check_ref(ref.strip(), corpus, qnums, lambda m, ln=s.line: E(n.file, ln, m))
        if n.mode == "apply":
            missing = [name for key, name in APPLY_NEEDS if not n.section(key)]
            if missing:
                W(n.file, n.line, f"apply node {n.id} has no {', '.join(missing)}")
    for n in cc.nodes:
        for tgt, why, ln in n.links:
            if tgt not in seen:
                E(n.file, ln, f"link to unknown node {tgt!r}")
            elif tgt == n.id:
                E(n.file, ln, f"{n.id} links to itself")
    centre = cc.settings.get("center")
    if centre and centre not in seen:
        E(str(display_path(cc.dir / "course.md")), 0, f"center {centre!r} is not a node")
    for cl in cc.clusters:
        mine = [n for n in cc.nodes if n.cluster == cl.id]
        if mine and centre and all(n.id == centre for n in mine):
            E(cl.file, 2, f"cluster {cl.id} has only the centre node {centre!r}: the map needs another node to draw it")
    covered = {n.topic for n in cc.nodes}
    for t in topics:
        if t not in covered:
            W(str(display_path(cc.dir)), 0, f"topic {t} has no node yet")


def _check_ref(ref: str, corpus, qnums, err) -> None:
    if corpus is None:
        return
    m = re.match(r"^(.+?)#Q([\w()]+)$", ref)
    if m:
        if (m.group(1), m.group(2).lower()) not in qnums:
            err(f"{ref!r}: no question {m.group(2)} in {m.group(1)} (see analysis/papers.json)")
        return
    r = corpus.resolve(ref)
    if isinstance(r, str):
        err(r)
