"""Near-duplicate units: incremental slide builds, recap slides, decks repeated across folders.

A unit is a duplicate of another when at least DUP_CONTAINMENT of its word shingles appear in the other,
and the other is larger (or the same size and earlier). The kept unit is the most complete one.
Papers are never deduplicated: a question repeated across years is a signal, not noise.
"""
from __future__ import annotations

import re
from collections import defaultdict

DUP_CONTAINMENT = 0.9
MIN_CHARS = 40
KINDS = {"slides", "notes", "extra"}
_WORD = re.compile(r"[a-z0-9]+")


def shingles(text: str) -> set[str]:
    w = _WORD.findall(text.lower())
    if len(w) < 6:
        return set(w)
    return {" ".join(w[i:i + 3]) for i in range(len(w) - 2)}


def find_duplicates(units: list[tuple[str, str, str]]) -> dict[str, str]:
    """units: (ref, kind, text) in course order. Returns {duplicate ref: kept ref}."""
    items = []
    for order, (ref, kind, text) in enumerate(units):
        if kind in KINDS and len(text) >= MIN_CHARS:
            sh = shingles(text)
            if len(sh) >= 3:
                items.append((ref, sh, order))
    index: dict[str, list[int]] = defaultdict(list)
    for k, (_, sh, _) in enumerate(items):
        for s in sh:
            index[s].append(k)
    parent: dict[int, int] = {}
    for k, (ref, sh, order) in enumerate(items):
        hits: dict[int, int] = defaultdict(int)
        for s in sh:
            for j in index[s]:
                if j != k:
                    hits[j] += 1
        best = None
        for j, common in hits.items():
            if common < DUP_CONTAINMENT * len(sh):
                continue
            other = items[j]
            bigger = len(other[1]) > len(sh) or (len(other[1]) == len(sh) and other[2] < order)
            if bigger and (best is None or (len(items[best][1]), -items[best][2]) < (len(other[1]), -other[2])):
                best = j
        if best is not None:
            parent[k] = best
    out = {}
    for k in parent:
        root, hops = k, 0
        while root in parent and hops < len(items):
            root, hops = parent[root], hops + 1
        out[items[k][0]] = items[root][0]
    return out
