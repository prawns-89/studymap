"""Corpus records: one JSON per source file, one unit per page / slide / section / code file."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

SCHEMA = 1


class Figure(BaseModel):
    path: str            # relative to corpus/, e.g. "img/slides-07-sched-pdf/p014.png"
    why: str             # figure | low-text | scanned | paper | embedded | image-file
    w: int
    h: int


class Unit(BaseModel):
    ref: str             # provenance: "slides/07-sched.pdf#p14", "labs/l1/a.c#L1-80"
    n: int               # 1-based page / slide / section number within the source
    title: str = ""
    text: str = ""
    lang: str = ""       # highlight.js language tag for code ("c", "mipsasm", "verilog", ...)
    chars: int = 0
    flags: list[str] = []
    notes: str = ""      # speaker notes (pptx)
    figures: list[Figure] = []


class SourceRecord(BaseModel):
    schema_version: int = SCHEMA
    sid: str
    path: str            # course-relative posix path
    kind: str            # slides | notes | labs | papers | extra
    type: str            # pdf | pptx | docx | text | code | image
    sha256: str
    extractor: str
    meta: dict[str, Any] = {}
    warnings: list[str] = []
    units: list[Unit] = []
