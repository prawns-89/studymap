"""Map layout, ported unchanged from reference/mindmap_build.py (BRIEF section 10).

Deterministic force layout clustered around a centre, label boxes measured with Anek Latin advance widths,
an overlap resolver that leaves zero label overlaps, and convex hulls for the cluster backgrounds.
Do not tune this casually: tests compare its output with the reference implementation.
"""
import math
import unicodedata

import numpy as np


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
