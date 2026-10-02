"""Data for the Plan tab, shaped from weightage.json and the paper analysis (BRIEF section 7, tab 1)."""
from __future__ import annotations

from ..analysis.models import PapersFile, TopicsFile
from ..analysis.report import Labels
from ..course import CourseConfig
from .text import block, inline


def plan_data(cfg: CourseConfig, w: dict, topics: TopicsFile, papers: PapersFile | None) -> dict:
    L = Labels(papers, topics)
    color = {c.id: k % 12 for k, c in enumerate(sorted(topics.clusters, key=lambda c: (c.order, c.id)))}
    qs = papers.questions if papers else []
    pm = {p.id: p for p in papers.papers} if papers else {}
    exams = []
    for e in w["exams"]:
        exams.append(dict(
            name=e["name"], weight=e["weight"], format=e["format"], basis=e["basis"], slide_prior=e["slide_prior"],
            reference_total=e["reference_total"], samples=len(e["samples"]),
            papers=[dict(id=p["id"], label=L.paper(p["id"]), total=p["total_marks"], relevance=p["relevance"]) for p in e["papers"]],
            topics=[dict(id=t["id"], share=t["share"], paper_share=t["paper_share"], slide_share=t["slide_share"],
                         marks=t["marks"], questions=t["questions"], samples=t["sample_questions"])
                    for t in e["topics"] if t["share"] > 0 or t["sample_questions"]],
            types=e["types"], modes=e["modes"]))
    with_papers = [e["name"] for e in w["exams"] if e["papers"]]
    return dict(
        exams=exams,
        default_exam=(with_papers or [e["name"] for e in w["exams"]] or [""])[0],
        clusters=[dict(id=c.id, name=c.name, color=color[c.id]) for c in topics.clusters],
        topics={t["id"]: dict(label=t["label"], name=t["name"], cluster=t["cluster"], color=color.get(t["cluster"], 11),
                              mode=t["mode"], weight=t["weight"], emphasis=t["emphasis"], in_slides=t["in_slides"])
                for t in w["topics"]},
        patterns=[dict(text=inline(p.text), questions=p.questions) for p in (papers.patterns if papers else [])],
        questions={q.id: dict(label=L.q_short(q.id), paper=q.paper, sample=pm[q.paper].kind == "sample", marks=q.marks,
                              type=q.type, mode=q.mode, topics=q.topics, text=block(q.text),
                              answer=block(q.answer.text) if q.answer else "",
                              caveat=inline(q.answer.caveat) if q.answer and q.answer.caveat else "",
                              hints=pm[q.paper].kind == "sample") for q in qs},
        notes=[inline(n) for n in (papers.notes if papers else [])],
        coverage=dict(not_in_slides=[dict(label=L.short(t["id"]), questions=t["questions"]) for t in w["coverage"]["not_in_slides"]],
                      unmapped=len(w["coverage"]["unmapped"]),
                      slides=[w["coverage"]["slides_covered"], w["coverage"]["slides_total"]]),
        unverified=dict(transcribed=len(w["unverified"]["transcribed"]), unofficial=len(w["unverified"]["unofficial_key"]),
                        no_answer=len(w["unverified"]["no_answer"]), caveats=len(w["unverified"]["caveats"])),
        counts=dict(papers=sum(1 for p in pm.values() if p.kind == "exam"), questions=len(qs), topics=len(topics.topics)),
    )
