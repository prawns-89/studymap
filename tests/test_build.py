"""`studymap build` / `validate`: the ported renderer, its determinism, and file:line errors."""
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from studymap.cli import main
from studymap.manifest import Manifest
from studymap.render import layout

from .conftest import EXAMPLES, REF

pytestmark = pytest.mark.skipif(not REF.exists(), reason="reference kit not found")


def payload(page: str) -> str:
    i = page.index("const D = ") + len("const D = ")
    return page[i:page.index(";\n(function", i)]


def reference_build(example: str, out: Path) -> str:
    subprocess.run([sys.executable, str(REF / "mindmap_build.py"), str(EXAMPLES / example),
                    str(REF / "mindmap_template.html"), str(out)], check=True, capture_output=True)
    return out.read_text(encoding="utf-8")


@pytest.mark.parametrize("example", ["photosynthesis", "hss-f338"])
def test_port_matches_the_reference_builder(example, tmp_path, capsys):
    """Same content -> the same data as reference/mindmap_build.py (same machine, same numpy)."""
    ref = reference_build(example, tmp_path / "ref.html")
    assert main(["build", str(EXAMPLES / example), "-o", str(tmp_path / "new.html")]) == 0
    assert "label overlaps left 0" in capsys.readouterr().out
    new = (tmp_path / "new.html").read_text(encoding="utf-8")
    assert payload(new) == payload(ref)


def test_label_tables_and_layout_constants_are_unchanged():
    spec = importlib.util.spec_from_file_location("ref_build", REF / "mindmap_build.py")
    ref = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ref)
    assert (layout.W450, layout.W600, layout.EXTRA, layout.FONT, layout.RAD) == \
           (ref.W450, ref.W600, ref.EXTRA, ref.FONT, ref.RAD)


def test_output_is_a_complete_html_document(tmp_path):
    assert main(["build", str(EXAMPLES / "photosynthesis"), "-o", str(tmp_path / "a.html")]) == 0
    page = (tmp_path / "a.html").read_text(encoding="utf-8")
    assert page.startswith("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">")
    assert "<title>Photosynthesis Map</title>" in page and page.rstrip().endswith("</html>")
    assert "/*__DATA__*/" not in page


def test_build_is_byte_identical_across_runs_and_hash_seeds(tmp_path):
    outs = []
    for seed in ("0", "1", "2"):
        out = tmp_path / f"{seed}.html"
        subprocess.run([sys.executable, "-m", "studymap", "build", str(EXAMPLES / "hss-f338"), "-o", str(out)],
                       check=True, capture_output=True, env=dict(os.environ, PYTHONHASHSEED=seed))
        outs.append(out.read_bytes())
    assert outs[0] == outs[1] == outs[2]


def test_course_build_uses_content_folder_and_records_the_stage(tmp_path, capsys):
    course = tmp_path / "C"
    shutil.copytree(EXAMPLES / "photosynthesis", course / "_studymap" / "content")
    assert main(["build", str(course)]) == 0
    out = course / "_studymap" / "index.html"
    assert out.exists()
    st = Manifest.load(course / "_studymap" / "state.json").stages["build"]
    assert st.status == "done" and st.summary["nodes"] == 13 and len(st.inputs) == 64
    assert main(["validate", str(course)]) == 0
    assert "ok · 5 clusters · 13 nodes · 24 facts · 2 sheets · 3 questions" in capsys.readouterr().out


def test_build_without_content_explains_what_is_missing(tmp_path, capsys):
    assert main(["build", str(tmp_path)]) == 1
    assert "no content yet" in capsys.readouterr().err


BAD_MAP = """\
!title Broken
!tag exam | asked in exams | warm
- a fact before any node
%A | Alpha | One | first
@a1 | Alpha one | A1 | 1
- a fact {exam}
- another fact {nope}
> a2 | fine
> ghost | points nowhere
@a1 | Alpha one again | A1b | 5
- dup
%B | Beta | Two | second
@b1 | Beta one | B1 | 2
> b1 | itself
this line means nothing
@a2 | Alpha two | A2 | 2
"""
BAD_SET = """\
!set Practice | desc | shuffle
Q a question before any node
@a1 | exam
Q Pick one
+ right
+ also right
- wrong
@ghost |
Q Pick one
- x
"""
BAD_SHEETS = """\
## group before any sheet
=sheet Pairs | lede | groups
## G | ghost
- a :: b | a1
"""


def test_validate_reports_every_problem_with_file_and_line(tmp_path, capsys):
    d = tmp_path / "content"
    d.mkdir()
    (d / "map.txt").write_text(BAD_MAP)
    (d / "set-1.txt").write_text(BAD_SET)
    (d / "sheets.txt").write_text(BAD_SHEETS)
    assert main(["validate", str(tmp_path), "--content", str(d)]) == 1
    out = capsys.readouterr().out
    d = d.resolve()
    m, s, sh = str(d / "map.txt"), str(d / "set-1.txt"), str(d / "sheets.txt")
    for expected in [
        f"{m}:3: fact before any @node line",
        f"{m}:7: tag {{nope}} is not declared with !tag",
        f"{m}:9: link from a1 to unknown node 'ghost'",
        f"{m}:10: tier '5': use 1, 2 or 3",
        f"{m}:10: duplicate node id 'a1' (first on line 5)",
        f"{m}:14: b1 links to itself",
        f"{m}:15: can't read this line: 'this line means nothing'",
        f"{m}:16: node a2 has no facts",
        f"{s}:2: question line before any @node line",
        f"{s}:6: two correct answers",
        f"{s}:8: unknown node 'ghost'",
        f"{s}:8: 1 options (use 2 to 6)",
        f"{s}:8: no correct option (+)",
        f"{s}:8: repeats the question on line 3",
        f"{sh}:1: group before any =sheet line",
        f"{sh}:3: unknown node 'ghost'",
    ]:
        assert expected in out, expected
    assert main(["build", str(tmp_path), "--content", str(d), "-o", str(tmp_path / "x.html")]) == 1
    assert not (tmp_path / "x.html").exists()


def test_later_commands_say_which_milestone(capsys, tmp_path):
    for cmd, ms in (("verify", "M4"), ("cheatsheet", "M5"), ("serve", "M6")):
        assert main([cmd, str(tmp_path)]) == 2
        assert ms in capsys.readouterr().out
