"""Load and validate the paper-analysis files against the course config and the ingested corpus."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from ..course import OUT_DIR, CourseConfig, display_path
from ..issues import Issue
from .corpus import Corpus
from .models import APPLY_TYPES, UNDERSTAND_TYPES, PapersFile, TopicsFile

TOPICS, PAPERS = "topics.json", "papers.json"


@dataclass
class Analysis:
    dir: Path
    topics: TopicsFile | None = None
    papers: PapersFile | None = None
    corpus: Corpus | None = None
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)

    @property
    def present(self) -> bool:
        return (self.dir / TOPICS).exists() or (self.dir / PAPERS).exists()


def _line(text: str, needle: str) -> int:
    i = text.find(needle)
    return text.count("\n", 0, i) + 1 if i >= 0 else 0


def _id_line(text: str, ident: str) -> int:
    return _line(text, f'"id": "{ident}"')


def _parse(path: Path, model, shown: str, errors: list[Issue]):
    text = path.read_text(encoding="utf-8")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as e:
        errors.append(Issue(shown, e.lineno, f"invalid JSON: {e.msg}"))
        return None, text
    try:
        return model.model_validate(raw), text
    except ValidationError as e:
        for err in e.errors():
            loc = err["loc"]
            line = 0
            # point at the list item the error is in, via its "id"
            if len(loc) >= 2 and isinstance(loc[1], int):
                try:
                    item = raw[loc[0]][loc[1]]
                    line = _id_line(text, item.get("id", "")) if isinstance(item, dict) and item.get("id") else 0
                except (KeyError, IndexError, TypeError):
                    pass
            errors.append(Issue(shown, line, f"{'.'.join(map(str, loc))}: {err['msg']}"))
        return None, text


def load_analysis(course: Path, cfg: CourseConfig) -> Analysis:
    adir = course / OUT_DIR / "analysis"
    a = Analysis(dir=adir)
    if not a.present:
        return a
    tp, pp = adir / TOPICS, adir / PAPERS
    ts, ps = str(display_path(tp)), str(display_path(pp))
    E = lambda f, ln, msg: a.errors.append(Issue(f, ln, msg))
    W = lambda f, ln, msg: a.warnings.append(Issue(f, ln, msg))
    if not tp.exists():
        E(ts, 0, "missing: papers.json refers to topics, so topics.json is needed too")
        return a
    corpus_dir = course / OUT_DIR / "corpus"
    if not (corpus_dir / "index.json").exists():
        E(ts, 0, "no corpus to check refs against: run `studymap ingest` first")
        return a
    a.corpus = corpus = Corpus(corpus_dir)

    topics, ttext = _parse(tp, TopicsFile, ts, a.errors)
    if topics is not None:
        a.topics = topics
        cids = set()
        for c in topics.clusters:
            if c.id in cids:
                E(ts, _id_line(ttext, c.id), f"duplicate cluster id {c.id!r}")
            cids.add(c.id)
        if not 2 <= len(topics.clusters) <= 12:
            W(ts, 0, f"{len(topics.clusters)} clusters: the map needs 2 to 12")
        seen = set()
        for t in topics.topics:
            ln = _id_line(ttext, t.id)
            if t.id in seen:
                E(ts, ln, f"duplicate topic id {t.id!r}")
            seen.add(t.id)
            if t.cluster not in cids:
                E(ts, ln, f"topic {t.id}: unknown cluster {t.cluster!r}")
            for ref in t.sources:
                r = corpus.resolve(ref)
                if isinstance(r, str):
                    E(ts, ln, f"topic {t.id}: {r}")
        for c in topics.clusters:
            if not any(t.cluster == c.id for t in topics.topics):
                W(ts, _id_line(ttext, c.id), f"cluster {c.id} has no topics")

    if not pp.exists() or topics is None:
        return a
    papers, ptext = _parse(pp, PapersFile, ps, a.errors)
    if papers is None:
        return a
    a.papers = papers
    tids = {t.id for t in topics.topics}
    exams = {e.name for e in cfg.exams}
    pids: dict[str, object] = {}
    for p in papers.papers:
        ln = _id_line(ptext, p.id)
        if p.id in pids:
            E(ps, ln, f"duplicate paper id {p.id!r}")
        pids[p.id] = p
        src = corpus.sources.get(p.path)
        if src is None:
            E(ps, ln, f"paper {p.id}: {p.path!r} is not in the corpus")
        elif src["kind"] != "papers":
            W(ps, ln, f"paper {p.id}: {p.path} is not in papers/")
        for k in p.keys:
            r = corpus.resolve(k.path)
            if isinstance(r, str):
                E(ps, ln, f"paper {p.id}: key {r}")
        if exams and p.exam not in exams:
            W(ps, ln, f"paper {p.id}: exam {p.exam!r} is not in course.yaml ({', '.join(sorted(exams))})")
        if p.kind == "exam" and p.total_marks is None:
            E(ps, ln, f"paper {p.id}: total_marks is required for an exam paper")
        if p.relevance < 1 and not p.relevance_reason:
            E(ps, ln, f"paper {p.id}: relevance below 1 needs a relevance_reason")

    qids: dict[str, object] = {}
    for q in papers.questions:
        ln = _id_line(ptext, q.id)
        if q.id in qids:
            E(ps, ln, f"duplicate question id {q.id!r}")
        qids[q.id] = q
        p = pids.get(q.paper)
        if p is None:
            E(ps, ln, f"{q.id}: unknown paper {q.paper!r}")
            continue
        if p.kind == "exam" and q.marks is None:
            E(ps, ln, f"{q.id}: marks are required on an exam paper")
        if not q.topics and not q.unmapped_reason:
            E(ps, ln, f"{q.id}: no topics; map it to a topic or explain why in unmapped_reason")
        for t in q.topics:
            if t not in tids:
                E(ps, ln, f"{q.id}: unknown topic {t!r}")
        r = corpus.resolve(q.src)
        if isinstance(r, str):
            E(ps, ln, f"{q.id}: src {r}")
        elif r and r[0].path != p.path:
            W(ps, ln, f"{q.id}: src is in {r[0].path}, not in its paper {p.path}")
        if q.answer:
            for ref in q.answer.src:
                r = corpus.resolve(ref)
                if isinstance(r, str):
                    E(ps, ln, f"{q.id}: answer src {r}")
        if q.type in APPLY_TYPES and q.mode != "apply":
            W(ps, ln, f"{q.id}: a {q.type} question is usually mode apply, not {q.mode}")
        if q.type in UNDERSTAND_TYPES and q.mode == "recall":
            W(ps, ln, f"{q.id}: a {q.type} question is usually mode understand, not recall")
    for q in papers.questions:
        for rid in q.repeats:
            other = qids.get(rid)
            if other is None:
                E(ps, _id_line(ptext, q.id), f"{q.id}: repeats unknown question {rid!r}")
            elif other.paper == q.paper:
                E(ps, _id_line(ptext, q.id), f"{q.id}: repeats {rid}, which is in the same paper")
    for p in papers.papers:
        if p.kind != "exam" or p.total_marks is None:
            continue
        total = sum(q.marks or 0 for q in papers.questions if q.paper == p.id)
        if abs(total - p.total_marks) > 1e-9:
            msg = f"paper {p.id}: question marks add up to {total:g}, but total_marks is {p.total_marks:g}"
            (W if p.marks_note else E)(ps, _id_line(ptext, p.id), msg + (f" ({p.marks_note})" if p.marks_note else ""))
    for i, pat in enumerate(papers.patterns, 1):
        if not pat.questions:
            E(ps, _line(ptext, pat.text[:40]), f"pattern {i} cites no questions")
        for qid in pat.questions:
            if qid not in qids:
                E(ps, _line(ptext, pat.text[:40]), f"pattern {i}: unknown question {qid!r}")
    analysed = {p.path for p in papers.papers} | {k.path.split("#")[0] for p in papers.papers for k in p.keys}
    for path, s in sorted(corpus.sources.items()):
        if s["kind"] == "papers" and path not in analysed and not s.get("paper", {}).get("is_key"):
            W(ps, 0, f"{path} is in papers/ but not analysed")
    return a
