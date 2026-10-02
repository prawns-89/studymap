"""Read-only view of an ingested corpus, for resolving provenance refs like 'slides/x.pdf#p8-13'."""
from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass
from pathlib import Path

REF = re.compile(r"^(?P<path>[^#]+?)(?:#(?P<kind>p|s|sec|cell|L)(?P<a>\d+)(?:-(?P<b>\d+))?)?$")


@dataclass(frozen=True)
class UnitInfo:
    ref: str
    path: str
    kind: str          # slides | notes | labs | papers | extra
    n: int
    title: str
    chars: int
    lines: tuple[int, int] | None   # for #L units


class Corpus:
    def __init__(self, corpus_dir: Path):
        self.dir = corpus_dir
        index = json.loads((corpus_dir / "index.json").read_text(encoding="utf-8"))
        self.index = index
        dd = corpus_dir / "dedupe.json"
        self.dups: dict[str, str] = json.loads(dd.read_text(encoding="utf-8")) if dd.exists() else {}
        self.sources = {s["path"]: s for s in index["sources"]}
        self.units: dict[str, list[UnitInfo]] = {}
        for s in index["sources"]:
            rec = json.loads((corpus_dir / "sources" / f"{s['sid']}.json").read_text(encoding="utf-8"))
            lst = []
            for u in rec["units"]:
                m = REF.match(u["ref"])
                lines = (int(m["a"]), int(m["b"] or m["a"])) if m and m["kind"] == "L" else None
                lst.append(UnitInfo(u["ref"], s["path"], s["kind"], u["n"], u["title"], u["chars"], lines))
            self.units[s["path"]] = lst

    def resolve(self, ref: str) -> list[UnitInfo] | str:
        """Units a ref points at, or an error message."""
        m = REF.match(ref.strip())
        if not m:
            return f"can't read ref {ref!r}"
        path = m["path"]
        if path not in self.units:
            return f"{path!r} is not in the corpus (run `studymap ingest` or check the name)"
        units = self.units[path]
        if not m["kind"]:
            return units
        a, b = int(m["a"]), int(m["b"] or m["a"])
        if b < a:
            return f"{ref!r}: range runs backwards"
        if m["kind"] == "L":
            hit = [u for u in units if u.lines and u.lines[0] <= b and u.lines[1] >= a]
        else:
            hit = [u for u in units if u.ref.rsplit("#", 1)[-1].startswith(m["kind"]) and a <= u.n <= b
                   and u.ref.rsplit("#", 1)[-1][len(m["kind"]):].isdigit()]
        if not hit or (m["kind"] != "L" and len(hit) != b - a + 1):
            have = len(units)
            return f"{ref!r}: no such {'lines' if m['kind'] == 'L' else 'page/slide/section'} ({path} has {have} units)"
        return hit

    def slide_units(self) -> list[UnitInfo]:
        """Every non-duplicate unit of a slide deck, in course order."""
        return [u for p in sorted(self.units) for u in self.units[p] if u.kind == "slides" and u.ref not in self.dups]

    @staticmethod
    def matches(ref: str, pattern: str) -> bool:
        return fnmatch.fnmatchcase(ref, pattern)
