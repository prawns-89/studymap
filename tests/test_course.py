"""The folder contract: course.yaml, folder kinds, ignore patterns, paper names."""
from pathlib import Path

import pytest

from studymap.course import CourseError, is_ignored, kind_of, load_config, parse_paper_name

BRIEF_YAML = """\
name: Operating Systems
code: CS F372
exams:
  - name: midsem
    weight: 30
    format: "90 min, closed book, 5 long questions"
  - name: compre
    weight: 40
    format: "3 h, part A short answers, part B long"
cheatsheet: { pages: 8, paper: A4, columns: 4, allowed: true }
labs_viva: true                 # generate viva question banks for labs
focus: ["scheduling", "synchronization"]   # topics I want extra depth on
ignore: ["slides/00-intro.pdf"]
notes_for_claude: "Midsem covers decks 1-12 only."
"""


def test_brief_example_yaml_parses(tmp_path):
    (tmp_path / "course.yaml").write_text(BRIEF_YAML)
    c = load_config(tmp_path)
    assert c.code == "CS F372" and [e.name for e in c.exams] == ["midsem", "compre"]
    assert c.cheatsheet.pages == 8 and c.labs_viva and c.focus == ["scheduling", "synchronization"]


def test_every_field_is_optional(tmp_path):
    c = load_config(tmp_path)
    assert c.name == "" and c.exams == [] and c.cheatsheet.pages == 8 and c.cheatsheet.columns == 4
    (tmp_path / "course.yaml").write_text("")
    assert load_config(tmp_path).ignore == []


def test_unknown_field_and_bad_values_are_reported(tmp_path):
    (tmp_path / "course.yaml").write_text("nme: OS\ncheatsheet: {pages: 0}\n")
    with pytest.raises(CourseError) as e:
        load_config(tmp_path)
    assert "nme" in str(e.value) and "cheatsheet.pages" in str(e.value)


def test_yaml_syntax_error_has_a_line_number(tmp_path):
    (tmp_path / "course.yaml").write_text("name: OS\nexams: [\n  - midsem\n")
    with pytest.raises(CourseError, match=r"course\.yaml:\d+"):
        load_config(tmp_path)


@pytest.mark.parametrize("rel, kind", [
    ("slides/a.pdf", "slides"), ("Slides/a.pdf", "slides"), ("papers/2024-midsem.pdf", "papers"),
    ("labs/l1/x.c", "labs"), ("extra/t.pdf", "extra"), ("textbook/ch1.pdf", "notes"), ("readme.md", "notes"),
])
def test_unknown_folders_and_root_files_are_notes(rel, kind):
    assert kind_of(rel) == kind


def test_ignore_matches_files_folders_and_globs():
    pats = ["slides/00-intro.pdf", "labs/*/pintos/src/tests", "**/build"]
    assert is_ignored("slides/00-intro.pdf", pats)
    assert is_ignored("labs/Sched/pintos/src/tests/threads/a.c", pats)
    assert is_ignored("labs/x/build/out.c", pats)
    assert not is_ignored("slides/01-os.pdf", pats)
    assert not is_ignored("labs/Sched/pintos/src/threads/thread.c", pats)


@pytest.mark.parametrize("stem, base, key, year, exam, variant", [
    ("2024-midsem", "2024-midsem", False, 2024, "midsem", ""),
    ("2024-midsem-key", "2024-midsem", True, 2024, "midsem", ""),
    ("2024-midsem-solutions", "2024-midsem", True, 2024, "midsem", ""),
    ("2023-compre-sol", "2023-compre", True, 2023, "compre", ""),
    ("2024-midsem-makeup", "2024-midsem-makeup", False, 2024, "midsem", "makeup"),
    ("2024-Midsem-B-Key", "2024-midsem-b", True, 2024, "midsem", "b"),
    ("sample-questions", "sample-questions", False, None, "sample-questions", ""),
])
def test_paper_names(stem, base, key, year, exam, variant):
    p = parse_paper_name(stem)
    assert (p.base, p.is_key, p.year, p.exam, p.variant) == (base, key, year, exam, variant)
