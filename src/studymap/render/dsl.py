"""The reference kit's line-based content format: map.txt, sheets.txt and set-*.txt.

Parsing matches reference/mindmap_build.py exactly for valid files. The differences are all in error
handling: every problem is collected as `file:line: message` (the reference stopped at the first one,
and crashed on some malformed files), and a few extra checks catch values the layout can't draw.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..issues import Issue

TAGS_RE = re.compile(r"\s*\{([^{}]+)\}\s*$")
TAG_STYLES = {"plain", "warm", "cool", "dashed"}


@dataclass
class Content:
    cfg: dict
    clusters: list[dict]
    nodes: list[dict]
    edges: list[dict]
    sheets: list[dict]
    sets: list[tuple[dict, list[dict]]]
    files: list[Path] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    set_names: list[str] = field(default_factory=list)   # display paths of the set-*.txt files, in order


def _split(line, n):
    parts = [p.strip() for p in line.split("|")]
    return (parts + [""] * n)[:n]


def parse_map(text: str, fname: str, issues: list[Issue]):
    cfg = {"tags": {}}
    clusters, nodes, edges = [], [], []
    cl = node = None
    for ln, raw in enumerate(text.splitlines(), 1):
        s = raw.rstrip().strip()
        if not s or s.startswith("//"):
            continue
        if s.startswith("!"):
            key, _, val = s[1:].partition(" ")
            if key == "tag":
                k, label, style = _split(val, 3)
                if style and style not in TAG_STYLES:
                    issues.append(Issue(fname, ln, f"tag style {style!r}: use one of {', '.join(sorted(TAG_STYLES))}"))
                cfg["tags"][k] = {"label": label or k, "style": style or "plain"}
            elif key == "source":
                t, u = _split(val, 2)
                cfg.setdefault("sources", []).append(dict(t=t, u=u))
            else:
                cfg[key] = val.strip()
        elif s.startswith("%"):
            cid, name, kicker, desc, color = _split(s[1:], 5)
            if color and not (color.isdigit() and 0 <= int(color) <= 11):
                issues.append(Issue(fname, ln, f"cluster colour {color!r}: use 0 to 11"))
            cl = dict(id=cid, name=name, kicker=kicker, desc=desc,
                      color=int(color) if color.isdigit() and int(color) <= 11 else None, ln=ln)
            clusters.append(cl)
        elif s.startswith("@"):
            if cl is None:
                issues.append(Issue(fname, ln, "node before any %cluster line"))
                continue
            nid, title, label, tier = _split(s[1:], 4)
            if tier and tier not in ("1", "2", "3"):
                issues.append(Issue(fname, ln, f"tier {tier!r}: use 1, 2 or 3"))
                tier = ""
            node = dict(id=nid, title=title, label=label or title, tier=int(tier or 2), c=cl["id"], facts=[], ln=ln)
            nodes.append(node)
        elif s.startswith("- "):
            if node is None:
                issues.append(Issue(fname, ln, "fact before any @node line"))
                continue
            t = s[2:].strip()
            m = TAGS_RE.search(t)
            tags = []
            if m:
                tags = [x.strip() for x in m.group(1).split(",") if x.strip()]
                t = t[: m.start()].rstrip()
            node["facts"].append(dict(t=t, tags=tags, ln=ln))
        elif s.startswith("> "):
            if node is None:
                issues.append(Issue(fname, ln, "link before any @node line"))
                continue
            tgt, why = _split(s[2:], 2)
            edges.append(dict(s=node["id"], t=tgt, why=why, ln=ln))
        else:
            issues.append(Issue(fname, ln, f"can't read this line: {s[:80]!r}"))
    return cfg, clusters, nodes, edges


def parse_sheets(text: str, fname: str, issues: list[Issue]):
    sheets, sh, grp = [], None, None
    for ln, raw in enumerate(text.splitlines(), 1):
        s = raw.strip()
        if not s or s.startswith("//"):
            continue
        if s.startswith("=sheet "):
            title, lede, style = _split(s[7:], 3)
            if style and style not in ("table", "groups", "cards"):
                issues.append(Issue(fname, ln, f"sheet style {style!r}: use table, groups or cards"))
            sh = dict(title=title, lede=lede, style=style or "table", groups=[], rows=[], ln=ln)
            sheets.append(sh)
            grp = None
        elif s.startswith("## "):
            if sh is None:
                issues.append(Issue(fname, ln, "group before any =sheet line"))
                continue
            title, node = _split(s[3:], 2)
            grp = dict(title=title, node=node, rows=[], ln=ln)
            sh["groups"].append(grp)
        elif s.startswith("- "):
            if sh is None:
                issues.append(Issue(fname, ln, "row before any =sheet line"))
                continue
            body, node = s[2:], ""
            if " | " in body:
                body, node = body.rsplit(" | ", 1)
            a, _, b = body.partition(" :: ")
            row = dict(a=a.strip(), b=b.strip(), node=node.strip(), ln=ln)
            (grp["rows"] if grp is not None else sh["rows"]).append(row)
        else:
            issues.append(Issue(fname, ln, f"can't read this line: {s[:80]!r}"))
    return sheets


def parse_set(text: str, fname: str, issues: list[Issue]):
    meta, qs, q = {}, [], None
    for ln, raw in enumerate(text.splitlines(), 1):
        s = raw.strip()
        if not s or s.startswith("//"):
            continue
        if s.startswith("!set "):
            name, desc, order = _split(s[5:], 3)
            if order and order not in ("shuffle", "keep"):
                issues.append(Issue(fname, ln, f"set order {order!r}: use shuffle or keep"))
            meta = dict(name=name, desc=desc, order=order or "shuffle")
        elif s.startswith("@"):
            node, tags = _split(s[1:], 2)
            q = dict(node=node, tags=[t.strip() for t in tags.split(",") if t.strip()],
                     q="", opts=[], ans=None, expl="", ln=ln)
            qs.append(q)
        elif q is None and (s.startswith(("Q ", "+ ", "- ", "= "))):
            issues.append(Issue(fname, ln, "question line before any @node line"))
        elif s.startswith("Q "):
            q["q"] = s[2:].strip()
        elif s.startswith("+ ") or s.startswith("- "):
            if s[0] == "+":
                if q["ans"] is not None:
                    issues.append(Issue(fname, ln, "two correct answers"))
                    continue
                q["ans"] = len(q["opts"])
            q["opts"].append(s[2:].strip())
        elif s.startswith("= "):
            q["expl"] = s[2:].strip()
        else:
            issues.append(Issue(fname, ln, f"can't read this line: {s[:80]!r}"))
    if not meta:
        meta = dict(name=Path(fname).stem, desc="", order="shuffle")
    return meta, qs


def validate(c: Content, map_name: str, sheets_name: str) -> list[Issue]:
    errs: list[Issue] = []
    seen: dict[str, int] = {}
    for n in c.nodes:
        if n["id"] in seen:
            errs.append(Issue(map_name, n["ln"], f"duplicate node id {n['id']!r} (first on line {seen[n['id']]})"))
        else:
            seen[n["id"]] = n["ln"]
        if not n["id"]:
            errs.append(Issue(map_name, n["ln"], "node has no id"))
    cseen: dict[str, int] = {}
    for cl in c.clusters:
        if cl["id"] in cseen:
            errs.append(Issue(map_name, cl["ln"], f"duplicate cluster id {cl['id']!r}"))
        cseen.setdefault(cl["id"], cl["ln"])
    if not 2 <= len(c.clusters) <= 12:
        errs.append(Issue(map_name, 0, f"{len(c.clusters)} clusters: use 2 to 12"))
    for cl in c.clusters:
        if not any(n["c"] == cl["id"] for n in c.nodes):
            errs.append(Issue(map_name, cl["ln"], f"cluster {cl['id']} has no nodes"))
    for e in c.edges:
        if e["t"] not in seen:
            errs.append(Issue(map_name, e["ln"], f"link from {e['s']} to unknown node {e['t']!r}"))
        if e["t"] == e["s"]:
            errs.append(Issue(map_name, e["ln"], f"{e['s']} links to itself"))
    if c.cfg.get("center") and c.cfg["center"] not in seen:
        errs.append(Issue(map_name, 0, f"!center {c.cfg['center']!r} is not a node id"))
    for n in c.nodes:
        if not n["facts"]:
            errs.append(Issue(map_name, n["ln"], f"node {n['id']} has no facts"))
        for f in n["facts"]:
            for t in f["tags"]:
                if t not in c.cfg["tags"]:
                    errs.append(Issue(map_name, f["ln"], f"tag {{{t}}} is not declared with !tag"))
    for sh in c.sheets:
        for r in sh["rows"] + [r for g in sh["groups"] for r in g["rows"]]:
            if r["node"] and r["node"] not in seen:
                errs.append(Issue(sheets_name, r["ln"], f"unknown node {r['node']!r}"))
        for g in sh["groups"]:
            if g["node"] and g["node"] not in seen:
                errs.append(Issue(sheets_name, g["ln"], f"unknown node {g['node']!r}"))
    for (meta, qs), fname in zip(c.sets, c.set_names):
        stems: dict[str, int] = {}
        for q in qs:
            w = lambda msg: errs.append(Issue(fname, q["ln"], msg))
            if q["node"] not in seen:
                w(f"unknown node {q['node']!r}")
            if q["ans"] is None:
                w("no correct option (+)")
            if not 2 <= len(q["opts"]) <= 6:
                w(f"{len(q['opts'])} options (use 2 to 6)")
            if len({o.lower() for o in q["opts"]}) != len(q["opts"]):
                w("duplicate options")
            if not q["q"]:
                w("missing Q line")
            elif q["q"].lower() in stems:
                w(f"repeats the question on line {stems[q['q'].lower()]}")
            stems.setdefault(q["q"].lower(), q["ln"])
            for t in q["tags"]:
                if t not in c.cfg["tags"]:
                    w(f"tag {t!r} is not declared with !tag")
    return errs


def load(content_dir: Path, display: Path | None = None) -> Content:
    """Parse a content folder. `display` is the prefix used in issue paths (defaults to the folder)."""
    d = content_dir
    pre = display if display is not None else d
    name = lambda p: str(pre / p.name)
    issues: list[Issue] = []
    mp = d / "map.txt"
    if not mp.exists():
        return Content({"tags": {}}, [], [], [], [], [], [], [Issue(name(mp), 0, "missing: every content folder needs a map.txt")])
    files = [mp]
    cfg, clusters, nodes, edges = parse_map(mp.read_text(encoding="utf-8"), name(mp), issues)
    sp = d / "sheets.txt"
    sheets = []
    if sp.exists():
        files.append(sp)
        sheets = parse_sheets(sp.read_text(encoding="utf-8"), name(sp), issues)
    sets, set_names = [], []
    for p in sorted(d.glob("set-*.txt")):
        files.append(p)
        set_names.append(name(p))
        sets.append(parse_set(p.read_text(encoding="utf-8"), name(p), issues))
    c = Content(cfg, clusters, nodes, edges, sheets, sets, files, issues, set_names)
    c.issues = issues + validate(c, name(mp), name(sp))
    return c
