"""The Markdown content model (FORMAT.md): parsing, validation, lessons, and the cheat sheet."""
import json
import re

import pytest

from studymap.cli import main
from studymap.content import load, validate
from studymap.render.lessons import lesson_html, to_map

from .conftest import write_analysis

COURSE_MD = """---
title: Testing Systems
center: rr
---
"""
SCHED = """---
cluster: sched
name: CPU scheduling
kicker: Unit 1
order: 1
---

## rr | Round robin | RR | mode=apply
- Each process runs one quantum $q$, then goes to the back of the queue. {src: slides/07-sched.pdf#p2}
- A fact with two sources. {src: slides/07-sched.pdf#p3; papers/2024-midsem.pdf#p1}
- A fact continued
  over two lines. {src: slides/07-sched.pdf#p4}

### Steps
1. Order the arrivals.
2. Run each for one quantum.

### Worked example {src: papers/2024-midsem.pdf#p1}
Three processes, q = 2.

**Solution**
The Gantt chart is A B A.

### Variant
Four processes, q = 1.

**Solution**
A B C D.

### Where marks are lost
- Measuring waiting time from 0.
- Forgetting the arrival order.

### Formulas
- TAT = CT - AT

### Code
```c
int q = 2;
```

### Links
- states | the queue holds ready processes

## fcfs | First come first served | FCFS | mode=recall
- Runs processes in arrival order. {src: slides/07-sched.pdf#p2}
"""
MEM = """---
cluster: mem
name: Memory
order: 2
---

## states | Process states | States | mode=understand
- Ready, running, blocked. {src: slides/08-paging.pptx#s1}

### Core idea
Three states, two transitions each.

### Misconceptions
- blocked is ready :: a blocked process cannot be chosen

### What changes if
- What if it is preempted? :: it goes back to ready

### Lookalikes
- Ready :: can be chosen now
- Blocked :: waiting for an event
"""


def write_content(course, extra=None, sched=SCHED):
    d = course / "_studymap" / "content"
    d.mkdir(parents=True, exist_ok=True)
    (d / "course.md").write_text(COURSE_MD)
    (d / "01-sched.md").write_text(sched)
    (d / "02-mem.md").write_text(MEM)
    if extra:
        (d / "03-extra.md").write_text(extra)
    return d


def test_parses_clusters_nodes_facts_and_sections(ingested_course):
    d = write_content(ingested_course)
    cc = load(d)
    assert cc.errors == [] and cc.settings["center"] == "rr"
    assert [c.id for c in cc.clusters] == ["sched", "mem"]
    rr = cc.nodes[0]
    assert (rr.id, rr.title, rr.label, rr.cluster) == ("rr", "Round robin", "RR", "sched")
    assert len(rr.facts) == 3
    assert rr.facts[1].src == ["slides/07-sched.pdf#p3", "papers/2024-midsem.pdf#p1"]
    assert rr.facts[2].text == "A fact continued over two lines."      # continuation line folded in
    assert [s.key for s in rr.sections] == ["steps", "example", "variant", "pitfalls", "formulas", "code", "links"]
    assert rr.links == [("states", "the queue holds ready processes", 43)]
    assert "int q = 2;" in rr.section("code").body                      # the ``` block survives verbatim


def test_mode_and_weight_come_from_the_papers(ingested_course):
    write_analysis(ingested_course)
    d = write_content(ingested_course, sched=SCHED.replace(" | RR | mode=apply\n", " | RR\n"))
    from studymap.analysis import load_analysis
    from studymap.analysis.weightage import compute
    from studymap.course import load_config
    cfg = load_config(ingested_course)
    an = load_analysis(ingested_course, cfg)
    cc = load(d)
    validate(cc, an, compute(cfg, an.topics, an.papers, an.corpus))
    assert cc.errors == []
    rr = cc.nodes[0]
    states = next(n for n in cc.nodes if n.id == "states")
    assert (rr.mode, rr.weight, rr.topic) == ("apply", "med", "rr")      # weight from weightage.json
    assert (states.mode, states.weight) == ("understand", "low")         # mode kept from the file


def test_problems_are_reported_with_file_and_line(ingested_course, capsys):
    bad = """---
cluster: bad
name: Bad
---

## x | X | X | mode=sideways tier=9 nope=1
- no source here
- bad ref {src: slides/07-sched.pdf#p99}

### Nonsense section
text

### Links
- ghost | nowhere
- x | itself

## x | Duplicate | Dup | mode=recall
- fine {src: slides/07-sched.pdf#p2}

## empty | Empty | E | mode=apply
"""
    write_analysis(ingested_course)
    d = write_content(ingested_course, extra=bad)
    assert main(["validate", str(ingested_course)]) == 1
    out = capsys.readouterr().out
    f = str(d / "03-extra.md")
    for want in [
        f"{f}:6: mode 'sideways'", f"{f}:6: tier '9': use 1, 2 or 3", f"{f}:6: unknown attribute 'nope'",
        f"{f}:8: 'slides/07-sched.pdf#p99': no such page", f"{f}:10: unknown section 'Nonsense section'",
        f"{f}:14: link to unknown node 'ghost'", f"{f}:15: x links to itself",
        f"{f}:17: duplicate node id 'x'", f"{f}:20: node empty has no facts",
        f"warning: {f}:7: fact without a", f"warning: {f}:20: apply node empty has no Worked example, Variant, Where marks are lost",
    ]:
        assert want in out, want


def test_map_data_and_lesson_html(ingested_course):
    d = write_content(ingested_course)
    cc = load(d)
    validate(cc)
    m = to_map(cc, "T", "E")
    assert m.cfg["title"] == "Testing Systems" and m.cfg["center"] == "rr"
    assert [n["id"] for n in m.nodes] == ["rr", "fcfs", "states"] and m.edges[0]["t"] == "states"
    h = lesson_html(cc.nodes[0])
    assert '<ol class="steps"><li>Order the arrivals.</li>' in h and 'data-step="next"' in h
    assert '<details class="sol" open><summary>Solution</summary><p>The Gantt chart is A B A.</p></details>' in h
    assert '<ul class="plainlist"><li>Measuring waiting time from 0.</li>' in h
    assert '<code>TAT = CT - AT</code>' in h and '<pre><code class="language-c">int q = 2;' in h
    assert "Links" not in h                                             # links are rendered by the page, not the lesson
    hm = lesson_html(next(n for n in cc.nodes if n.id == "states"))
    assert '<details class="wcard"><summary>What if it is preempted?</summary>' in hm
    assert '<span class="no">✗ blocked is ready</span>' in hm and 'class="mini look"' in hm


def test_build_puts_content_and_cheat_sheet_in_the_page(ingested_course):
    write_analysis(ingested_course)
    write_content(ingested_course)
    assert main(["build", str(ingested_course)]) == 0
    page = (ingested_course / "_studymap" / "index.html").read_text(encoding="utf-8")
    i = page.index("const D = ") + len("const D = ")
    D = json.loads(page[i:page.index(";\n(function", i)].replace("<\\/", "</"))
    assert len(D["nodes"]) == 3 and D["content"]["nodes"]["rr"]["mode"] == "apply"
    assert D["content"]["nodes"]["rr"]["srcs"][1] == ["slides/07-sched.pdf#p3", "papers/2024-midsem.pdf#p1"]
    assert "Each process runs one quantum" in D["cheat"]["doc"] and "7.5 pt" in D["cheat"]["lede"]     # draft until `cheatsheet` runs
    assert D["plan"]["counts"]["questions"] == 3


@pytest.mark.browser
def test_cheatsheet_fits_the_budget_and_passes_qa(ingested_course, capsys):
    write_analysis(ingested_course)
    write_content(ingested_course)
    from studymap.check import launch
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            b, _ = launch(p)
            b.close()
    except Exception:
        pytest.skip("no browser")
    assert main(["cheatsheet", str(ingested_course), "--pages", "2"]) == 0
    out = capsys.readouterr().out
    assert "of 2 pages at" in out and "nothing left out" in out
    import pymupdf
    out_dir = ingested_course / "_studymap"
    with pymupdf.open(out_dir / "cheatsheet.pdf") as doc:
        assert doc.page_count <= 2
        text = re.sub(r"\s+", " ", "".join(p.get_text() for p in doc))
    assert "Each process runs one quantum" in text and "TAT = CT - AT" in text
    assert (out_dir / "cheatsheet-4up.pdf").exists()
    j = json.loads((out_dir / "cheatsheet.json").read_text())
    assert j["problems"] == [] and j["body_font"] >= 6 and j["missing"] == []
    assert "## Cheat sheet" in (out_dir / "report.md").read_text()
