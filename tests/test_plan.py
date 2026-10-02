"""The Plan tab: question text rendering, plan data in the page, and building with or without a map."""
import json
import shutil

from studymap.cli import main
from studymap.render.text import block, inline

from .conftest import EXAMPLES, PAPERS, write_analysis


def payload(page: str) -> dict:
    i = page.index("const D = ") + len("const D = ")
    return json.loads(page[i:page.index(";\n(function", i)].replace("<\\/", "</"))


def test_question_text_markdown_subset():
    assert inline("a `x < y` and **b** <i>") == "a <code>x &lt; y</code> and <b>b</b> &lt;i&gt;"
    html = block("Run this:\n\n```c\nif (a < b) printf(\"x\");\n```\n\n| PTE | frame |\n|---|---|\n| 0 | 101100 |\n\nThen *say* why.")
    assert html == ('<p>Run this:</p><pre><code class="language-c">if (a &lt; b) printf("x");</code></pre>'
                    '<div class="tblwrap"><table class="mini"><thead><tr><th>PTE</th><th>frame</th></tr></thead>'
                    '<tbody><tr><td>0</td><td>101100</td></tr></tbody></table></div><p>Then <i>say</i> why.</p>')


def test_plan_only_page(ingested_course, capsys):
    write_analysis(ingested_course)
    assert main(["build", str(ingested_course)]) == 0
    out = capsys.readouterr().out
    assert "no map content yet: the page has the Plan tab only" in out and "plan: 1 exams · 5 topics" in out
    page = (ingested_course / "_studymap" / "index.html").read_text(encoding="utf-8")
    D = payload(page)
    assert D["nodes"] == [] and D["cfg"]["title"] == "CS F999 Testing Systems"
    P = D["plan"]
    assert P["default_exam"] == "midsem" and [t["id"] for t in P["exams"][0]["topics"]][:2] == ["ipc", "metrics"]
    assert P["questions"]["2024-midsem-q1"]["answer"] == "<p>5.67 ms</p>"
    assert P["counts"] == {"papers": 1, "questions": 3, "topics": 5}
    assert (ingested_course / "_studymap" / "report.md").exists()        # build refreshes the report too


def test_plan_and_map_together(ingested_course):
    write_analysis(ingested_course)
    shutil.copytree(EXAMPLES / "photosynthesis", ingested_course / "_studymap" / "content")
    assert main(["build", str(ingested_course)]) == 0
    D = payload((ingested_course / "_studymap" / "index.html").read_text(encoding="utf-8"))
    assert len(D["nodes"]) == 13 and D["plan"]["counts"]["topics"] == 5


def test_build_refuses_a_broken_analysis(ingested_course, capsys):
    papers = json.loads(json.dumps(PAPERS))
    papers["questions"][0]["marks"] = 3
    write_analysis(ingested_course, papers=papers)
    assert main(["build", str(ingested_course)]) == 1
    assert "question marks add up to 9, but total_marks is 10" in capsys.readouterr().out
    assert not (ingested_course / "_studymap" / "index.html").exists()
