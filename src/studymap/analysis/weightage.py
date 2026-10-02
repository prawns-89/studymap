"""Derive weightage.json from the analysis: topic shares per exam, question-type and mode mixes,
a study order, coverage gaps and what is unverified. Pure arithmetic, no judgement.

Share of a topic in an exam:
  paper share   = marks the topic got in a paper / the paper's total (a question's marks are split
                  evenly between its topics), averaged over the exam's papers weighted by relevance
  slide share   = the topic's slides / all slides that topics cover (near-duplicates counted once)
  share         = blend of the two, the slides counting as one more paper of evidence:
                  (R * paper share + 1 * slide share) / (R + 1), R = sum of the papers' relevance.
                  No papers: the slide share alone (BRIEF section 3).
Course points of a topic = sum over exams of share x the exam's weight in course.yaml.
High / med / low: topics making up the first 50% of points are high, the next 30% med, the rest low.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from ..course import CourseConfig
from .corpus import Corpus
from .models import PapersFile, TopicsFile

MODE_ORDER = ("apply", "understand", "recall")   # tie-break: practice takes longest, so it wins
R = lambda x: round(x, 4)


def emphasis_of(topics: TopicsFile, corpus: Corpus) -> dict[str, list[str]]:
    out = {}
    for t in topics.topics:
        refs: set[str] = set()
        for ref in t.sources:
            r = corpus.resolve(ref)
            if isinstance(r, list):
                refs |= {u.ref for u in r if u.kind == "slides" and u.ref not in corpus.dups}
        out[t.id] = sorted(refs)
    return out


def compute(cfg: CourseConfig, topics: TopicsFile, papers: PapersFile | None, corpus: Corpus) -> dict:
    tlist = topics.topics
    emph = {k: len(v) for k, v in emphasis_of(topics, corpus).items()}
    tot_emph = sum(emph.values())
    slide_share = {t: e / tot_emph for t, e in emph.items()} if tot_emph else {}
    plist = papers.papers if papers else []
    qs = papers.questions if papers else []
    pmap = {p.id: p for p in plist}
    qpaper = {q.id: q.paper for q in qs}

    names = [e.name for e in cfg.exams]
    names += sorted({p.exam for p in plist} - set(names))
    weights = {e.name: e.weight for e in cfg.exams}
    weighted = bool(names) and all(weights.get(n) is not None for n in names)

    exams_out, points = [], defaultdict(float)
    for name in names:
        ecfg = next((e for e in cfg.exams if e.name == name), None)
        eps = [p for p in plist if p.exam == name and p.kind == "exam" and p.total_marks]
        sps = [p for p in plist if p.exam == name and p.kind == "sample"]
        rel = sum(p.relevance for p in eps)
        paper_share, marks, asked = defaultdict(float), defaultdict(dict), defaultdict(list)
        tshare, mshare = defaultdict(float), defaultdict(float)
        tcount, mcount = Counter(), Counter()
        for p in eps:
            for q in qs:
                if q.paper != p.id:
                    continue
                m = q.marks or 0.0
                tcount[q.type] += 1
                mcount[q.mode] += 1
                if rel:
                    tshare[q.type] += p.relevance * m / p.total_marks / rel
                    mshare[q.mode] += p.relevance * m / p.total_marks / rel
                for t in q.topics:
                    part = m / len(q.topics)
                    marks[t][p.id] = R(marks[t].get(p.id, 0.0) + part)
                    asked[t].append(q.id)
                    if rel:
                        paper_share[t] += p.relevance * part / p.total_marks / rel
        sample_hits = defaultdict(list)
        for p in sps:
            for q in qs:
                if q.paper == p.id:
                    for t in q.topics:
                        sample_hits[t].append(q.id)
        if rel and slide_share:
            basis, lam = "papers+slides", 1 / (rel + 1)
        elif rel:
            basis, lam = "papers", 0.0
        elif slide_share:
            basis, lam = "slides", 1.0
        else:
            basis, lam = "none", 0.0
        share = {t.id: (1 - lam) * paper_share.get(t.id, 0.0) + lam * slide_share.get(t.id, 0.0) for t in tlist}
        w = weights.get(name) if weighted else 1.0
        for t, s in share.items():
            points[t] += s * w
        ref_paper = max(eps, key=lambda p: (p.year or 0, p.relevance), default=None)
        order = sorted(tlist, key=lambda t: (-share[t.id], -emph[t.id], t.id))
        exams_out.append(dict(
            name=name, weight=weights.get(name), format=ecfg.format if ecfg else "",
            basis=basis, slide_prior=R(lam),
            papers=[dict(id=p.id, year=p.year, total_marks=p.total_marks, relevance=p.relevance)
                    for p in sorted(eps, key=lambda p: (-(p.year or 0), p.id))],
            samples=[p.id for p in sps],
            reference_total=ref_paper.total_marks if ref_paper else None,
            topics=[dict(id=t.id, share=R(share[t.id]), paper_share=R(paper_share.get(t.id, 0.0)),
                         slide_share=R(slide_share.get(t.id, 0.0)), marks=marks.get(t.id, {}),
                         papers_asked=len({qpaper[x] for x in asked.get(t.id, [])}),
                         questions=asked.get(t.id, []), sample_questions=sample_hits.get(t.id, []))
                    for t in order],
            types=[dict(type=k, share=R(tshare[k]), count=tcount[k]) for k in sorted(tcount, key=lambda k: (-tshare[k], k))],
            modes=[dict(mode=k, share=R(mshare[k]), count=mcount[k]) for k in MODE_ORDER if mcount[k]],
            papers_total=len(eps)))

    # one row per topic for the whole course
    votes = defaultdict(Counter)
    tq = defaultdict(list)
    for q in qs:
        p = pmap.get(q.paper)
        if p is None:
            continue
        v = (q.marks or 1.0) * p.relevance
        for t in q.topics:
            votes[t][q.mode] += v
            tq[t].append(q.id)
    total_pts = sum(points.values())
    order = sorted(tlist, key=lambda t: (-points[t.id], -emph[t.id], t.id))
    klass, run = {}, 0.0
    for t in order:
        before = run / total_pts if total_pts else 1.0
        klass[t.id] = "low" if not points[t.id] else "high" if before < 0.5 else "med" if before < 0.8 else "low"
        run += points[t.id]
    topic_rows = []
    for t in order:
        vs = votes.get(t.id)
        mode = max(MODE_ORDER, key=lambda m: (vs[m], -MODE_ORDER.index(m))) if vs else None
        topic_rows.append(dict(id=t.id, name=t.name, cluster=t.cluster, emphasis=emph[t.id], in_slides=emph[t.id] > 0,
                               points=R(points[t.id]), weight=klass[t.id], mode=mode, questions=tq.get(t.id, [])))

    return dict(schema_version=1, weighted=weighted, exams=exams_out, topics=topic_rows,
                order=[t.id for t in order], coverage=_coverage(topics, papers, corpus, emph, tq),
                unverified=_unverified(papers), repeats=_repeat_groups(papers))


def _coverage(topics, papers, corpus, emph, tq) -> dict:
    covered = set().union(*emphasis_of(topics, corpus).values()) if topics.topics else set()
    ok = [u.ref for u in corpus.slide_units()
          if any(Corpus.matches(u.ref, o.ref) for o in topics.uncovered_ok)]
    gaps = []
    for u in corpus.slide_units():
        if u.ref in covered or u.ref in ok:
            continue
        if gaps and gaps[-1]["path"] == u.path and gaps[-1]["last"] == u.n - 1:
            g = gaps[-1]
            g["last"] = u.n
            if u.title and u.title not in g["titles"]:
                g["titles"].append(u.title)
        else:
            gaps.append(dict(path=u.path, first=u.n, last=u.n, titles=[u.title] if u.title else []))
    qs = papers.questions if papers else []
    analysed = {p.path for p in papers.papers} | {k.path.split("#")[0] for p in papers.papers for k in p.keys} if papers else set()
    return dict(
        unmapped=[dict(id=q.id, reason=q.unmapped_reason) for q in qs if not q.topics],
        not_in_slides=[dict(id=t.id, name=t.name, questions=tq[t.id]) for t in topics.topics if tq.get(t.id) and not emph[t.id]],
        uncovered_slides=[dict(path=g["path"], pages=f"p{g['first']}" + (f"-{g['last']}" if g["last"] != g["first"] else ""),
                               titles=g["titles"][:6]) for g in gaps],
        deliberately_uncovered=len(ok),
        slides_total=len(corpus.slide_units()), slides_covered=len(covered),
        unanalysed_papers=sorted(p for p, s in corpus.sources.items()
                                 if s["kind"] == "papers" and p not in analysed and not s.get("paper", {}).get("is_key")))


def _unverified(papers) -> dict:
    if not papers:
        return dict(transcribed=[], unofficial_key=[], no_answer=[], caveats=[])
    pm = {p.id: p for p in papers.papers}
    unofficial = {p.id for p in papers.papers if any(k.status == "unofficial" for k in p.keys)}
    return dict(
        transcribed=[q.id for q in papers.questions if pm[q.paper].transcribed_from_image],
        unofficial_key=[q.id for q in papers.questions if q.answer and q.paper in unofficial],
        no_answer=[q.id for q in papers.questions if q.answer is None],
        caveats=[dict(id=q.id, caveat=q.answer.caveat) for q in papers.questions if q.answer and q.answer.caveat])


def _repeat_groups(papers) -> list[list[str]]:
    if not papers:
        return []
    parent = {q.id: q.id for q in papers.questions}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for q in papers.questions:
        for r in q.repeats:
            if r in parent:
                parent[find(q.id)] = find(r)
    groups = defaultdict(list)
    order = {q.id: i for i, q in enumerate(papers.questions)}
    for q in papers.questions:
        groups[find(q.id)].append(q.id)
    return sorted((sorted(g, key=order.get) for g in groups.values() if len(g) > 1), key=lambda g: order[g[0]])
