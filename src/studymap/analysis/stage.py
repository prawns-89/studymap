"""The deterministic half of the paper-analysis stage: validate, then derive weightage.json and report.md."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..course import OUT_DIR, CourseConfig
from ..manifest import Manifest, digest, sha256_file, write_if_changed
from . import Analysis, load_analysis
from .report import render
from .weightage import compute


@dataclass
class ReportResult:
    analysis: Analysis
    weightage: dict | None = None
    report: Path | None = None
    written: int = 0


def run_report(course: Path, cfg: CourseConfig) -> ReportResult:
    """Validate the analysis; if it is clean, write analysis/weightage.json and report.md."""
    a = load_analysis(course, cfg)
    res = ReportResult(a)
    if not a.present or a.errors or a.topics is None:
        return res
    w = compute(cfg, a.topics, a.papers, a.corpus)
    out = course / OUT_DIR
    res.weightage = w
    res.report = out / "report.md"
    res.written += write_if_changed(a.dir / "weightage.json", json.dumps(w, indent=1, ensure_ascii=False) + "\n")
    ch = out / "cheatsheet.json"
    cheat = json.loads(ch.read_text(encoding="utf-8")) if ch.exists() else None
    res.written += write_if_changed(res.report, render(cfg, w, a.topics, a.papers, a.corpus.index, cheat))
    mp = out / "state.json"
    man = Manifest.load(mp)
    man.begin("report")
    inputs = {p.name: sha256_file(p) for p in (a.dir / "topics.json", a.dir / "papers.json") if p.exists()}
    inputs["corpus/index.json"] = sha256_file(out / "corpus" / "index.json")
    man.finish("report", inputs=digest(inputs), topics=len(a.topics.topics),
               questions=len(a.papers.questions) if a.papers else 0)
    man.save(mp)
    return res
