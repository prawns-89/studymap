#!/usr/bin/env python3
"""Build a single-file interactive HTML mind map from plain-text content files.

Usage:  python3 mindmap_build.py CONTENT_DIR TEMPLATE_HTML OUT_HTML

CONTENT_DIR holds:
  map.txt        required: settings, clusters, nodes, facts, links
  sheets.txt     optional: cram sheets (tables, grouped lists, cards)
  set-*.txt      optional: question sets (one file per set, sorted by name)
Needs Python 3.8+ and numpy.
"""
import html, json, math, random, re, sys, unicodedata
from pathlib import Path

import numpy as np

# --------------------------------------------------------------------------- parsing

TAGS_RE = re.compile(r"\s*\{([^{}]+)\}\s*$")


def _split(line, n):
    parts = [p.strip() for p in line.split("|")]
    return (parts + [""] * n)[:n]


def parse_map(text):
    cfg = {"tags": {}}
    clusters, nodes, edges = [], [], []
    cl = node = None
    for ln, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        s = line.strip()
        if not s or s.startswith("//"):
            continue
        if s.startswith("!"):
            key, _, val = s[1:].partition(" ")
            if key == "tag":
                k, label, style = _split(val, 3)
                cfg["tags"][k] = {"label": label or k, "style": style or "plain"}
            elif key == "source":
                t, u = _split(val, 2)
                cfg.setdefault("sources", []).append(dict(t=t, u=u))
            else:
                cfg[key] = val.strip()
        elif s.startswith("%"):
            cid, name, kicker, desc, color = _split(s[1:], 5)
            cl = dict(id=cid, name=name, kicker=kicker, desc=desc,
                      color=int(color) if color.isdigit() else None)
            clusters.append(cl)
        elif s.startswith("@"):
            if cl is None:
                raise SystemExit(f"map.txt:{ln}: node before any %cluster line")
            nid, title, label, tier = _split(s[1:], 4)
            node = dict(id=nid, title=title, label=label or title, tier=int(tier or 2),
                        c=cl["id"], facts=[])
            nodes.append(node)
        elif s.startswith("- "):
            if node is None:
                raise SystemExit(f"map.txt:{ln}: fact before any @node line")
            t = s[2:].strip()
            m = TAGS_RE.search(t)
            tags = []
            if m:
                tags = [x.strip() for x in m.group(1).split(",") if x.strip()]
                t = t[: m.start()].rstrip()
            node["facts"].append(dict(t=t, tags=tags))
        elif s.startswith("> "):
            if node is None:
                raise SystemExit(f"map.txt:{ln}: link before any @node line")
            tgt, why = _split(s[2:], 2)
            edges.append(dict(s=node["id"], t=tgt, why=why, ln=ln))
        else:
            raise SystemExit(f"map.txt:{ln}: can't read this line: {s[:80]!r}")
    return cfg, clusters, nodes, edges


def parse_sheets(text):
    sheets, sh, grp = [], None, None
    for ln, raw in enumerate(text.splitlines(), 1):
        s = raw.strip()
        if not s or s.startswith("//"):
            continue
        if s.startswith("=sheet "):
            title, lede, style = _split(s[7:], 3)
            sh = dict(title=title, lede=lede, style=style or "table", groups=[], rows=[])
            sheets.append(sh); grp = None
        elif s.startswith("## "):
            title, node = _split(s[3:], 2)
            grp = dict(title=title, node=node, rows=[])
            sh["groups"].append(grp)
        elif s.startswith("- "):
            body, node = s[2:], ""
            if " | " in body:
                body, node = body.rsplit(" | ", 1)
            a, _, b = body.partition(" :: ")
            row = dict(a=a.strip(), b=b.strip(), node=node.strip())
            (grp["rows"] if grp is not None else sh["rows"]).append(row)
        else:
            raise SystemExit(f"sheets.txt:{ln}: can't read this line: {s[:80]!r}")
    return sheets


def parse_set(text, fname):
    meta, qs, q = {}, [], None
    for ln, raw in enumerate(text.splitlines(), 1):
        s = raw.strip()
        if not s or s.startswith("//"):
            continue
        if s.startswith("!set "):
            name, desc, order = _split(s[5:], 3)
            meta = dict(name=name, desc=desc, order=order or "shuffle")
        elif s.startswith("@"):
            node, tags = _split(s[1:], 2)
            q = dict(node=node, tags=[t.strip() for t in tags.split(",") if t.strip()],
                     q="", opts=[], ans=None, expl="", ln=ln)
            qs.append(q)
        elif s.startswith("Q "):
            q["q"] = s[2:].strip()
        elif s.startswith("+ ") or s.startswith("- "):
            if s[0] == "+":
                if q["ans"] is not None:
                    raise SystemExit(f"{fname}:{ln}: two correct answers")
                q["ans"] = len(q["opts"])
            q["opts"].append(s[2:].strip())
        elif s.startswith("= "):
            q["expl"] = s[2:].strip()
        else:
            raise SystemExit(f"{fname}:{ln}: can't read this line: {s[:80]!r}")
    if not meta:
        meta = dict(name=Path(fname).stem, desc="", order="shuffle")
    return meta, qs


def validate(cfg, clusters, nodes, edges, sheets, sets):
    errs = []
    ids = [n["id"] for n in nodes]
    seen = set()
    for i in ids:
        if i in seen:
            errs.append(f"duplicate node id: {i}")
        seen.add(i)
    if len({c["id"] for c in clusters}) != len(clusters):
        errs.append("duplicate cluster id")
    if not 2 <= len(clusters) <= 12:
        errs.append(f"{len(clusters)} clusters: use 2 to 12")
    for c in clusters:
        if not any(n["c"] == c["id"] for n in nodes):
            errs.append(f"cluster {c['id']} has no nodes")
    for e in edges:
        if e["t"] not in seen:
            errs.append(f"map.txt:{e['ln']}: link from {e['s']} to unknown node {e['t']!r}")
        if e["t"] == e["s"]:
            errs.append(f"map.txt:{e['ln']}: {e['s']} links to itself")
    if cfg.get("center") and cfg["center"] not in seen:
        errs.append(f"!center {cfg['center']!r} is not a node id")
    for n in nodes:
        if not n["facts"]:
            errs.append(f"node {n['id']} has no facts")
        for f in n["facts"]:
            for t in f["tags"]:
                if t not in cfg["tags"]:
                    errs.append(f"node {n['id']}: tag {{{t}}} is not declared with !tag")
    for sh in sheets:
        for r in sh["rows"] + [r for g in sh["groups"] for r in g["rows"]]:
            if r["node"] and r["node"] not in seen:
                errs.append(f"sheet {sh['title']!r}: unknown node {r['node']!r}")
        for g in sh["groups"]:
            if g["node"] and g["node"] not in seen:
                errs.append(f"sheet {sh['title']!r}: unknown node {g['node']!r}")
    for meta, qs in sets:
        stems = set()
        for i, q in enumerate(qs, 1):
            w = f"set {meta['name']!r} Q{i} (line {q['ln']})"
            if q["node"] not in seen:
                errs.append(f"{w}: unknown node {q['node']!r}")
            if q["ans"] is None:
                errs.append(f"{w}: no correct option (+)")
            if not 2 <= len(q["opts"]) <= 6:
                errs.append(f"{w}: {len(q['opts'])} options (use 2 to 6)")
            if len({o.lower() for o in q["opts"]}) != len(q["opts"]):
                errs.append(f"{w}: duplicate options")
            if not q["q"]:
                errs.append(f"{w}: missing Q line")
            if q["q"].lower() in stems:
                errs.append(f"{w}: repeats an earlier question in the set")
            stems.add(q["q"].lower())
            for t in q["tags"]:
                if t not in cfg["tags"]:
                    errs.append(f"{w}: tag {t!r} is not declared with !tag")
    return errs


# --------------------------------------------------------------------------- text helpers

_IA, _IB = chr(0x0900), chr(0x0DFF)  # Devanagari through Sinhala
INDIC = re.compile(f"([{_IA}-{_IB}]+(?:[\\s{_IA}-{_IB}]*[{_IA}-{_IB}])?)")


def md(text):
    """Escape HTML, then **bold**, *italic*, and wrap runs of Indic script."""
    s = html.escape(text, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", s)
    return INDIC.sub(r'<span class="script">\1</span>', s)


# Anek Latin at wdth 88: advance widths per 1000 units, printable ASCII 32..126
W450 = [176, 210, 312, 509, 413, 658, 529, 163, 254, 255, 370, 420, 176, 283, 176, 320, 468, 298, 390, 400, 424, 423, 440, 370, 456, 449, 179, 181, 434, 434, 434, 362, 741, 482, 481, 400, 494, 423, 394, 477, 518, 213, 329, 472, 396, 635, 523, 486, 466, 500, 479, 413, 372, 500, 431, 665, 461, 390, 423, 268, 346, 268, 358, 377, 265, 412, 438, 336, 438, 392, 316, 422, 454, 194, 207, 419, 195, 688, 454, 401, 438, 438, 312, 356, 325, 448, 415, 634, 413, 415, 375, 298, 220, 298, 471]
W600 = [175, 226, 347, 518, 429, 681, 566, 180, 274, 275, 379, 430, 198, 282, 199, 342, 495, 322, 413, 418, 453, 444, 464, 397, 480, 475, 202, 203, 438, 440, 438, 378, 758, 507, 502, 414, 516, 441, 411, 502, 541, 234, 339, 500, 410, 671, 550, 513, 490, 527, 502, 429, 416, 522, 472, 709, 487, 422, 441, 280, 367, 280, 379, 376, 297, 434, 460, 347, 461, 412, 327, 442, 477, 217, 230, 453, 218, 717, 477, 420, 460, 461, 330, 373, 337, 472, 440, 665, 442, 441, 392, 308, 232, 308, 482]
EXTRA = {"·": 190, "–": 420, "—": 720, "→": 640, "←": 640, "’": 176, "‘": 176, "“": 320, "”": 320, "…": 560, "×": 420}


def text_width(label, size, weight):
    table = W600 if weight >= 550 else W450
    total = 0
    for ch in label:
        o = ord(ch)
        if 32 <= o <= 126:
            total += table[o - 32]
        elif ch in EXTRA:
            total += EXTRA[ch]
        else:
            base = unicodedata.normalize("NFD", ch)[0]
            total += table[ord(base) - 32] if 32 <= ord(base) <= 126 else 560
    return total / 1000 * size


# --------------------------------------------------------------------------- layout

FONT = {1: (14.0, 600), 2: (12.5, 500), 3: (11.5, 450)}
RAD = {1: 8.5, 2: 6.0, 3: 4.5}


def label_box(n, side):
    fs, wt = FONT[n["tier"]]
    w = text_width(n["label"], fs, wt) * 1.04
    r = RAD[n["tier"]]
    hh = fs * 0.72 + 4
    return (-r - 5, r + 6 + w + 8, hh) if side >= 0 else (-(r + 6 + w + 8), r + 5, hh)


def resolve(pos, boxes, fixed):
    L = pos[:, 0] + boxes[:, 0]; R = pos[:, 0] + boxes[:, 1]
    T = pos[:, 1] - boxes[:, 2]; B = pos[:, 1] + boxes[:, 2]
    ox = np.minimum(R[:, None], R[None, :]) - np.maximum(L[:, None], L[None, :])
    oy = np.minimum(B[:, None], B[None, :]) - np.maximum(T[:, None], T[None, :])
    m = (ox > 0) & (oy > 0)
    np.fill_diagonal(m, False)
    ii, jj = np.nonzero(np.triu(m))
    for i, j in zip(ii, jj):
        dx = (pos[j, 0] + (boxes[j, 0] + boxes[j, 1]) / 2) - (pos[i, 0] + (boxes[i, 0] + boxes[i, 1]) / 2)
        dy = (pos[j, 1] - pos[i, 1]) * 1.6
        norm = math.hypot(dx, dy) or 1.0
        push = min(ox[i, j], oy[i, j] * 2.0) / 2 + 0.6
        v = np.array([dx / norm * push, dy / norm * push])
        if i != fixed:
            pos[i] -= v
        if j != fixed:
            pos[j] += v
    return len(ii)


def layout(clusters, nodes, edges, center_id, seed=7, iters=900):
    rng = np.random.default_rng(seed)
    idx = {n["id"]: i for i, n in enumerate(nodes)}
    n = len(nodes)
    order = [c["id"] for c in clusters]
    sizes = {c: sum(1 for x in nodes if x["c"] == c and x["id"] != center_id) for c in order}
    scale = min(1.3, max(0.5, math.sqrt(n / 150)))
    need = {c: math.sqrt(max(sizes[c], 1)) for c in order}
    tot = sum(need.values())
    ang, a = {}, -math.pi / 2
    for c in order:
        span = 2 * math.pi * need[c] / tot
        ang[c] = a + span / 2
        a += span
    RX, RY = 470 * scale, 320 * scale
    cc = {c: np.array([RX * math.cos(ang[c]), RY * math.sin(ang[c])]) for c in order}
    crad = {c: 78 * math.sqrt(max(sizes[c], 1)) for c in order}
    pos = np.zeros((n, 2))
    for i, nd in enumerate(nodes):
        t = rng.uniform(0, 2 * math.pi)
        rr = crad[nd["c"]] * math.sqrt(rng.uniform(0.05, 1))
        pos[i] = cc[nd["c"]] + rr * np.array([math.cos(t), math.sin(t)])
    ci = idx.get(center_id, -1)
    if ci >= 0:
        pos[ci] = 0
    sides = np.ones(n)
    boxes = np.array([label_box(nd, 1) for nd in nodes])
    cidx = np.array([order.index(nd["c"]) for nd in nodes])
    centers = np.array([cc[nd["c"]] for nd in nodes])
    E = []
    for e in edges:
        i, j = idx[e["s"]], idx[e["t"]]
        if ci in (i, j):
            continue
        same = nodes[i]["c"] == nodes[j]["c"]
        E.append((i, j, 150.0 if same else 420.0 * scale, 0.05 if same else 0.003))
    E = np.array(E, dtype=float) if E else np.zeros((0, 4))
    ei, ej = E[:, 0].astype(int), E[:, 1].astype(int)
    for it in range(iters):
        alpha = 1.0 - it / iters
        d = pos[:, None, :] - pos[None, :, :]
        dist2 = (d ** 2).sum(-1) + 25.0
        k = np.where(cidx[:, None] == cidx[None, :], 9000.0, 14000.0)
        f = (d * (k / dist2)[..., None]).sum(1)
        pos += 0.9 * alpha * np.clip(f, -30, 30)
        if len(E):
            delta = pos[ej] - pos[ei]
            L = np.sqrt((delta ** 2).sum(-1)) + 1e-6
            fs = (E[:, 3] * (L - E[:, 2]) / L)[:, None] * delta * alpha
            np.add.at(pos, ei, fs)
            np.add.at(pos, ej, -fs)
        pos += (0.018 + 0.012 * (1 - alpha)) * (centers - pos)
        if ci >= 0:
            pos[ci] = 0
        if it in (int(iters * 0.4), int(iters * 0.7)):
            for i in range(n):
                sides[i] = 1 if pos[i, 0] >= centers[i, 0] - 10 else -1
                boxes[i] = label_box(nodes[i], sides[i])
        if it > iters * 0.45:
            resolve(pos, boxes, ci)
    clear = 135 * max(scale, 0.75)
    for _ in range(3):
        for _ in range(200):
            if not resolve(pos, boxes, ci):
                break
        for i in range(n):
            dist = np.linalg.norm(pos[i])
            if i != ci and dist < clear:
                pos[i] *= clear / max(dist, 1)
    left = resolve(pos, boxes, ci)
    return pos, sides, cc, left


def hull(points):
    pts = sorted(set(map(tuple, points)))
    if len(pts) <= 2:
        return pts
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def balanced_shuffle(qs, seed):
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


# --------------------------------------------------------------------------- build

def main():
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    cdir, tpl, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    cfg, clusters, nodes, edges = parse_map((cdir / "map.txt").read_text(encoding="utf-8"))
    sheets = parse_sheets((cdir / "sheets.txt").read_text(encoding="utf-8")) if (cdir / "sheets.txt").exists() else []
    sets = [parse_set(p.read_text(encoding="utf-8"), p.name) for p in sorted(cdir.glob("set-*.txt"))]
    errs = validate(cfg, clusters, nodes, edges, sheets, sets)
    if errs:
        print("Fix these and run again:\n  " + "\n  ".join(errs)); sys.exit(1)

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
    page = tpl.read_text(encoding="utf-8")
    if "/*__DATA__*/null" not in page:
        raise SystemExit("template is missing the /*__DATA__*/null placeholder")
    page = page.replace("<title>Mind map</title>", f"<title>{html.escape(data['cfg']['title'])}</title>", 1)
    page = page.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
    out.write_text(page, encoding="utf-8")
    print(f"nodes {len(nodes)} · links {len(edge_out)} · facts {data['meta']['facts']} · sheets {len(sheets_out)} · "
          f"questions {data['meta']['questions']} · label overlaps left {left}")
    for s in sets_out:
        from collections import Counter
        print(f"  {s['name']}: answer positions", dict(sorted(Counter('abcdef'[q['ans']] for q in s['qs']).items())))
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
