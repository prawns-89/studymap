"""Derived weightage.json and report.md: the arithmetic, the wording, the no-papers fallback."""
import json

from studymap.analysis.stage import run_report
from studymap.cli import main
from studymap.course import load_config

from .conftest import PAPERS, write_analysis


def test_weightage_arithmetic(ingested_course):
    write_analysis(ingested_course)
    w = run_report(ingested_course, load_config(ingested_course)).weightage
    (e,) = w["exams"]
    assert e["basis"] == "papers+slides" and e["slide_prior"] == 0.5 and e["reference_total"] == 10
    share = {t["id"]: t["share"] for t in e["topics"]}
    # papers: rr 2/10, metrics 2/10, ipc 6/10; slides (near-duplicate p2 counted once): rr 1/7, states 1/7,
    # metrics 2/7, paging 3/7; blended half and half (one paper of evidence + the slides as one more)
    assert share == {"ipc": 0.3, "metrics": round(0.1 + 1 / 7, 4), "paging": round(1.5 / 7, 4),
                     "rr": round(0.1 + 0.5 / 7, 4), "states": round(0.5 / 7, 4)}
    assert [t["id"] for t in e["topics"]] == ["ipc", "metrics", "paging", "rr", "states"]
    assert {t["id"]: t["marks"] for t in e["topics"]}["rr"] == {"2024-midsem": 2.0}
    assert {t["id"]: t["sample_questions"] for t in e["topics"]}["paging"] == ["samples-1"]
    assert [(x["type"], x["share"]) for x in e["types"]] == [("long-explain", 0.6), ("numerical", 0.4)]
    assert [(x["mode"], x["share"]) for x in e["modes"]] == [("apply", 0.4), ("understand", 0.6)]
    rows = {t["id"]: t for t in w["topics"]}
    assert rows["ipc"]["points"] == 9.0 and [t["id"] for t in w["topics"]] == ["ipc", "metrics", "paging", "rr", "states"]
    assert [rows[t]["weight"] for t in w["order"]] == ["high", "high", "med", "med", "low"]
    assert rows["rr"]["mode"] == "apply" and rows["ipc"]["mode"] == "understand" and rows["paging"]["mode"] == "understand"
    assert rows["states"]["mode"] is None and rows["ipc"]["in_slides"] is False
    cov = w["coverage"]
    assert cov["not_in_slides"] == [{"id": "ipc", "name": "IPC", "questions": ["2024-midsem-q2"]}]
    assert cov["uncovered_slides"] == [] and cov["slides_total"] == 8 and cov["slides_covered"] == 7
    assert cov["unmapped"] == [] and cov["unanalysed_papers"] == []
    un = w["unverified"]
    assert un["transcribed"] == ["2024-midsem-q1", "2024-midsem-q2"] and un["no_answer"] == ["2024-midsem-q2", "samples-1"]


def test_report_reads_well_and_is_stable(ingested_course, capsys):
    write_analysis(ingested_course)
    assert main(["report", str(ingested_course)]) == 0
    assert "midsem (papers+slides): IPC 30% · Scheduling metrics 24%" in capsys.readouterr().out
    rep = (ingested_course / "_studymap" / "report.md").read_text()
    for s in ["# CS F999 Testing Systems: exam report", "## At a glance", "## Recurring patterns",
              "- Every paper has a scheduling numerical.  \n  *2024 midsem Q1 [4]*",
              "| # | Topic | Share | ≈ marks /10 | 2024 midsem | Samples | Slides |",
              "| 1 | IPC | 30% | 3 | 6 | · | · |", "| 2 | Scheduling metrics | 24% | 2.4 | 2 | · | 2 |", "## Coverage", "**Unmapped questions: 0.**",
              "**Asked in papers but not in your slides:** IPC (2024 midsem Q2 [6])",
              "**Transcribed from scans (2):**", "**No answer yet (2):**", "## How the numbers are made"]:
        assert s in rep, s
    before = rep
    assert main(["report", str(ingested_course)]) == 0
    assert "(0 changed)" in capsys.readouterr().out and (ingested_course / "_studymap" / "report.md").read_text() == before
    st = json.loads((ingested_course / "_studymap" / "state.json").read_text())["stages"]["report"]
    assert st["status"] == "done" and st["summary"]["questions"] == 3


def test_no_papers_falls_back_to_slides_and_says_so(ingested_course):
    write_analysis(ingested_course, papers=None)
    r = run_report(ingested_course, load_config(ingested_course))
    (e,) = r.weightage["exams"]
    assert e["basis"] == "slides" and e["papers"] == []
    assert {t["id"]: t["share"] for t in e["topics"]}["paging"] == round(3 / 7, 4)
    rep = r.report.read_text()
    assert "**No past papers yet.**" in rep and "slide emphasis only" in rep


def test_a_broken_analysis_derives_nothing(ingested_course, capsys):
    papers = json.loads(json.dumps(PAPERS))
    papers["questions"][0]["topics"] = ["ghost"]
    write_analysis(ingested_course, papers=papers)
    r = run_report(ingested_course, load_config(ingested_course))
    assert r.weightage is None and not (ingested_course / "_studymap" / "report.md").exists()
    assert main(["report", str(ingested_course)]) == 1
    assert "unknown topic 'ghost'" in capsys.readouterr().out
