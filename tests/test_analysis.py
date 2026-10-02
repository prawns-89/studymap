"""Paper analysis files: validation against the corpus, with file:line problems; the JSON Schema."""
import json

from studymap.analysis import load_analysis
from studymap.cli import main
from studymap.course import load_config

from .conftest import PAPERS, TOPICS, write_analysis


def test_clean_analysis_validates(ingested_course, capsys):
    write_analysis(ingested_course)
    a = load_analysis(ingested_course, load_config(ingested_course))
    assert a.errors == [] and a.warnings == []
    assert main(["validate", str(ingested_course)]) == 0
    assert "ok · 2 clusters · 5 topics · 2 papers · 3 questions · 1 patterns" in capsys.readouterr().out


def test_problems_are_reported_with_file_and_line(ingested_course, capsys):
    topics = json.loads(json.dumps(TOPICS))
    topics["topics"][1]["sources"] = ["slides/07-sched.pdf#p9"]
    topics["topics"][2]["cluster"] = "nope"
    papers = json.loads(json.dumps(PAPERS))
    q1, q2, s1 = papers["questions"]
    q1["topics"] = ["rr", "ghost"]
    q1["repeats"] = ["2024-midsem-q2"]
    q2["topics"] = []
    q2["marks"] = 5
    s1["src"] = "papers/sample-questions.pdf#p7"
    papers["papers"][0]["relevance"] = 0.5
    d = write_analysis(ingested_course, topics, papers)
    assert main(["validate", str(ingested_course)]) == 1
    out = capsys.readouterr().out
    t, p = str(d / "topics.json"), str(d / "papers.json")
    tl = (d / "topics.json").read_text().split("\n")
    pl = (d / "papers.json").read_text().split("\n")
    line = lambda lines, ident: next(i for i, s in enumerate(lines, 1) if f'"id": "{ident}"' in s)
    for expected in [
        f"{t}:{line(tl, 'states')}: topic states: 'slides/07-sched.pdf#p9': no such page/slide/section",
        f"{t}:{line(tl, 'metrics')}: topic metrics: unknown cluster 'nope'",
        f"{p}:{line(pl, '2024-midsem-q1')}: 2024-midsem-q1: unknown topic 'ghost'",
        f"{p}:{line(pl, '2024-midsem-q1')}: 2024-midsem-q1: repeats 2024-midsem-q2, which is in the same paper",
        f"{p}:{line(pl, '2024-midsem-q2')}: 2024-midsem-q2: no topics; map it to a topic or explain why in unmapped_reason",
        f"{p}:{line(pl, 'samples-1')}: samples-1: src 'papers/sample-questions.pdf#p7': no such page",
        f"{p}:{line(pl, '2024-midsem')}: paper 2024-midsem: relevance below 1 needs a relevance_reason",
        f"{p}:{line(pl, '2024-midsem')}: paper 2024-midsem: question marks add up to 9, but total_marks is 10",
    ]:
        assert expected in out, expected


def test_schema_and_json_errors_point_at_the_line(ingested_course, capsys):
    papers = json.loads(json.dumps(PAPERS))
    papers["questions"][1]["type"] = "essay"
    d = write_analysis(ingested_course, papers=papers)
    assert main(["validate", str(ingested_course)]) == 1
    out = capsys.readouterr().out
    ln = next(i for i, s in enumerate((d / "papers.json").read_text().split("\n"), 1) if '"id": "2024-midsem-q2"' in s)
    assert f"papers.json:{ln}: questions.1.type: Input should be 'mcq'" in out
    (d / "topics.json").write_text('{\n "clusters": [\n')
    assert main(["validate", str(ingested_course)]) == 1
    assert "topics.json:3: invalid JSON" in capsys.readouterr().out


def test_schema_command_prints_json_schema(capsys):
    assert main(["schema", "papers"]) == 0
    s = json.loads(capsys.readouterr().out)
    assert s["title"] == "PapersFile" and "Question" in s["$defs"]
