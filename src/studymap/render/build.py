"""`studymap build`: content files -> one self-contained index.html.

Ported from reference/mindmap_build.py. The data handed to the template is identical to the
reference for the same content (tests check this); the page around it is now a full HTML document.
"""
from __future__ import annotations

import html
import json
import math
import random
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .dsl import Content
from .layout import hull, label_box, layout, text_width

TEMPLATE = Path(__file__).parent / "templates" / "site.html"
PLACEHOLDER = "/*__DATA__*/null"

# --------------------------------------------------------------------------- text helpers (unchanged)

_IA, _IB = chr(0x0900), chr(0x0DFF)  # Devanagari through Sinhala
INDIC = re.compile(f"([{_IA}-{_IB}]+(?:[\\s{_IA}-{_IB}]*[{_IA}-{_IB}])?)")


def md(text):
    """Escape HTML, then **bold**, *italic*, and wrap runs of Indic script."""
    s = html.escape(text, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", s)
    return INDIC.sub(r'<span class="script">\1</span>', s)


def balanced_shuffle(qs, seed):
    """Shuffle options so correct answers are spread evenly over a-d (BRIEF section 10)."""
    rng = random.Random(seed)
    slots, out = [], []
    for q in qs:
        k = len(q["opts"])
        if not slots:
            slots = list(range(4)); rng.shuffle(slots)
        t = slots.pop()
        if t >= k:
            t = rng.randrange(k)
        right = q["opts"][q["ans"]]
        rest = [o for i, o in enumerate(q["opts"]) if i != q["ans"]]
        rng.shuffle(rest)
        opts = rest[:t] + [right] + rest[t:]
        out.append(dict(q, opts=opts, ans=t))
    return out


# --------------------------------------------------------------------------- data

@dataclass
class BuildStats:
    nodes: int
    edges: int
    facts: int
    sheets: int
    questions: int
    overlaps: int
    answer_positions: list[tuple[str, dict]]


def build_data(content: Content) -> tuple[dict, BuildStats]:
    cfg, clusters, nodes, edges = content.cfg, content.clusters, content.nodes, content.edges
    sheets, sets = content.sheets, content.sets
    center = cfg.get("center", "")
    pos, sides, cc, left = layout(clusters, nodes, edges, center)
    idx = {n["id"]: i for i, n in enumerate(nodes)}

    # label visibility: the two best-connected ideas per cluster always show; more as you zoom
    deg = {n["id"]: 0 for n in nodes}
    for e in edges:
        deg[e["s"]] += 1; deg[e["t"]] += 1
    rank = sorted(nodes, key=lambda n: -(deg[n["id"]] + (3 - n["tier"]) * 1.6))
    vis, per = {}, {}
    n1 = max(12, round(len(nodes) * 0.17)); n2 = max(30, round(len(nodes) * 0.46))
    for n in rank:
        if per.get(n["c"], 0) < 2:
            vis[n["id"]] = 1; per[n["c"]] = per.get(n["c"], 0) + 1
    for n in rank:
        if n["id"] not in vis:
            c1 = sum(v == 1 for v in vis.values()); c2 = sum(v == 2 for v in vis.values())
            vis[n["id"]] = 1 if c1 < n1 else 2 if c2 < n2 else 3

    xs, ys, cl_out = [], [], []
    for i, n in enumerate(nodes):
        l, r, h = label_box(n, sides[i])
        xs += [pos[i, 0] + l, pos[i, 0] + r]; ys += [pos[i, 1] - h, pos[i, 1] + h]
    for k, c in enumerate(clusters):
        pts = []
        for i, n in enumerate(nodes):
            if n["c"] == c["id"] and n["id"] != center:
                l, r, h = label_box(n, sides[i])
                pts += [(pos[i, 0] + l, pos[i, 1] - h), (pos[i, 0] + r, pos[i, 1] - h),
                        (pos[i, 0] + l, pos[i, 1] + h), (pos[i, 0] + r, pos[i, 1] + h)]
        hl = hull(np.array(pts))
        cen = np.mean(np.array(pts), axis=0)
        a = math.atan2(cen[1], cen[0]); u = np.array([math.cos(a), math.sin(a)])
        # the title (kicker over name) sits outside the hull, cleared by its own half-size along u
        hw = 1.15 * max(len(c["name"]) * 12.0, text_width(c["kicker"].upper(), 12, 650) + 1.7 * len(c["kicker"])) / 2
        tp = cen + u * (max(np.dot(np.array(p) - cen, u) for p in hl) + 22 + hw * abs(u[0]) + 22 * abs(u[1]))
        xs += [tp[0] - hw - 8, tp[0] + hw + 8]; ys += [tp[1] - 34, tp[1] + 30]
        cl_out.append(dict(id=c["id"], name=c["name"], kicker=c["kicker"], desc=c["desc"],
                           color=c["color"] if c["color"] is not None else k % 12,
                           hull=[[round(x, 1), round(y, 1)] for x, y in hl],
                           title=[round(float(tp[0]), 1), round(float(tp[1]), 1), round(float(cen[0]), 1), round(float(cen[1]), 1)]))
    if center:
        xs += [-140, 140]; ys += [-140, 140]
    bounds = [round(min(xs) - 40, 1), round(min(ys) - 40, 1), round(max(xs) + 40, 1), round(max(ys) + 40, 1)]

    refs = {n["id"]: [] for n in nodes}
    sets_out = []
    for s_i, (meta, qs) in enumerate(sets):
        qs2 = balanced_shuffle(qs, 101 * (s_i + 1)) if meta["order"] != "keep" else qs
        key = f"s{s_i + 1}"
        lst = []
        for k, q in enumerate(qs2, 1):
            qid = f"{key}-{k:02d}"
            lst.append(dict(id=qid, n=k, node=q["node"], tags=q["tags"], q=md(q["q"]),
                            opts=[md(o) for o in q["opts"]], ans=q["ans"], expl=md(q["expl"])))
            refs[q["node"]].append(dict(s=key, n=k, id=qid))
        sets_out.append(dict(key=key, name=meta["name"], desc=md(meta["desc"]), qs=lst))

    merged = {}
    for e in edges:
        k = tuple(sorted((e["s"], e["t"])))
        merged.setdefault(k, []).append(dict(f=e["s"], t=md(e["why"])))
    edge_out = [dict(a=a, b=b, cross=nodes[idx[a]]["c"] != nodes[idx[b]]["c"], labels=lab)
                for (a, b), lab in merged.items()]
    node_out = [dict(id=n["id"], title=md(n["title"]), plain=n["title"], label=n["label"], c=n["c"],
                     tier=n["tier"], vis=vis[n["id"]], x=round(float(pos[i, 0]), 1), y=round(float(pos[i, 1]), 1),
                     side=int(sides[i]), facts=[dict(h=md(f["t"]), tags=f["tags"]) for f in n["facts"]],
                     refs=refs[n["id"]]) for i, n in enumerate(nodes)]
    sheets_out = [dict(title=md(s["title"]), lede=md(s["lede"]), style=s["style"],
                       rows=[dict(a=md(r["a"]), b=md(r["b"]), node=r["node"]) for r in s["rows"]],
                       groups=[dict(title=md(g["title"]), node=g["node"],
                                    rows=[dict(a=md(r["a"]), b=md(r["b"]), node=r["node"]) for r in g["rows"]]) for g in s["groups"]])
                  for s in sheets]
    data = dict(
        cfg=dict(title=cfg.get("title", "Mind map"), eyebrow=cfg.get("eyebrow", ""), tagline=md(cfg.get("tagline", "")),
                 center=center, caption=cfg.get("center-caption", ""), howto=md(cfg.get("howto", "")),
                 footer=md(cfg.get("footer", "")), tags={k: dict(label=v["label"], style=v["style"]) for k, v in cfg["tags"].items()},
                 sources=cfg.get("sources", [])),
        meta=dict(nodes=len(nodes), edges=len(edge_out), facts=sum(len(n["facts"]) for n in nodes),
                  questions=sum(len(s["qs"]) for s in sets_out), bounds=bounds),
        clusters=cl_out, nodes=node_out, edges=edge_out, sheets=sheets_out, sets=sets_out)
    stats = BuildStats(nodes=len(nodes), edges=len(edge_out), facts=data["meta"]["facts"], sheets=len(sheets_out),
                       questions=data["meta"]["questions"], overlaps=int(left),
                       answer_positions=[(s["name"], dict(sorted(Counter("abcdef"[q["ans"]] for q in s["qs"]).items())))
                                         for s in sets_out])
    return data, stats


def empty_data(title: str, eyebrow: str = "") -> dict:
    """Page data with no map, for a course that has a paper analysis but no content yet."""
    return dict(cfg=dict(title=title, eyebrow=eyebrow, tagline="", center="", caption="", howto="", footer="", tags={},
                         sources=[]),
                meta=dict(nodes=0, edges=0, facts=0, questions=0, bounds=[-100, -100, 100, 100]),
                clusters=[], nodes=[], edges=[], sheets=[], sets=[])


def data_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def render_page(data: dict, template: Path = TEMPLATE) -> str:
    page = template.read_text(encoding="utf-8")
    if PLACEHOLDER not in page:
        raise ValueError(f"{template}: missing the {PLACEHOLDER} placeholder")
    page = page.replace("<title>Mind map</title>", f"<title>{html.escape(data['cfg']['title'])}</title>", 1)
    return page.replace(PLACEHOLDER, data_json(data))
