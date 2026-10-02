"""`studymap ingest` on a synthetic course: extraction, provenance, heuristics, caching, resuming."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from studymap import ingest as ingest_mod
from studymap.ingest import ingest
from studymap.ingest.common import clean_text
from studymap.ingest.dedupe import find_duplicates
from studymap.ingest.text import asm_flavour
from studymap.ingest.walk import make_sids
from studymap.manifest import Manifest

from .conftest import MIPS, X86

quiet = lambda s: None


def corpus_of(course: Path) -> Path:
    return course / "_studymap" / "corpus"


def index(course: Path) -> dict:
    return json.loads((corpus_of(course) / "index.json").read_text())


def record(course: Path, rel: str) -> dict:
    src = next(s for s in index(course)["sources"] if s["path"] == rel)
    return json.loads((corpus_of(course) / "sources" / f"{src['sid']}.json").read_text())


def view(course: Path, rel: str) -> str:
    src = next(s for s in index(course)["sources"] if s["path"] == rel)
    return (corpus_of(course) / src["text"]).read_text()


def snapshot(course: Path) -> dict[str, bytes]:
    root = course / "_studymap"
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*"))
            if p.is_file() and p.name != "state.json"}


@pytest.fixture
def ingested(course):
    res = ingest(course, log=quiet)
    return course, res


# --------------------------------------------------------------------------- what gets read

def test_finds_and_classifies_every_source(ingested):
    course, res = ingested
    assert not res.failed
    got = {s["path"]: (s["kind"], s["type"], s.get("lang", "")) for s in index(course)["sources"]}
    assert got == {
        "labs/lab1/Makefile": ("labs", "code", "makefile"),
        "labs/lab1/boot.S": ("labs", "code", "x86asm"),
        "labs/lab1/datapath.png": ("labs", "image", ""),
        "labs/lab1/diagram.png": ("labs", "image", ""),
        "labs/lab1/main.c": ("labs", "code", "c"),
        "labs/lab1/sum.asm": ("labs", "code", "mipsasm"),
        "notes/deadlock.docx": ("notes", "docx", ""),
        "notes/summary.md": ("notes", "text", ""),
        "papers/2023-compre-sol.pdf": ("papers", "pdf", ""),
        "papers/2024-midsem-key.pdf": ("papers", "pdf", ""),
        "papers/2024-midsem.pdf": ("papers", "pdf", ""),
        "papers/sample-questions.pdf": ("papers", "pdf", ""),
        "slides/07-sched.pdf": ("slides", "pdf", ""),
        "slides/08-paging.pptx": ("slides", "pptx", ""),
        "tutorials/t1.txt": ("notes", "text", ""),          # unknown folder -> notes
    }


def test_skipped_files_are_listed_with_a_reason(ingested):
    course, _ = ingested
    skipped = {s["path"]: s["reason"] for s in index(course)["skipped"]}
    assert skipped["labs/lab1/build/"] == "ignored by course.yaml"
    assert "archive" in skipped["extra/old.zip"]
    assert "legacy" in skipped["extra/deck.ppt"]
    assert "unsupported" in skipped["labs/lab1/main.o"]
    assert not any(p.startswith(".git") for p in skipped)          # hidden folders are silently left out


def test_pdf_pages_have_provenance_and_clean_text(ingested):
    course, _ = ingested
    units = record(course, "slides/07-sched.pdf")["units"]
    assert [u["ref"] for u in units] == [f"slides/07-sched.pdf#p{i}" for i in range(1, 7)]
    assert units[0]["text"].count("CPU Scheduling") == 1                # shadow text kept once
    assert all("Testing Systems" not in u["text"] for u in units)        # running footer dropped
    assert all(u["text"].split("\n")[-1] != str(u["n"]) for u in units)  # page number dropped
    assert "(0 + 5 + 12) / 3 = 5.67 ms" in units[5]["text"]             # body numbers kept
    assert units[1]["title"] == "Round robin"


def test_figures_are_rendered_but_template_logos_are_not_figures(ingested):
    course, _ = ingested
    units = record(course, "slides/07-sched.pdf")["units"]
    flags = {u["n"]: u["flags"] for u in units}
    assert "figure" in flags[4] and "figure" in flags[5]               # vector drawing, big picture
    assert "figure" not in flags[2] and "figure" not in flags[6]       # only the repeated logo
    assert not units[1]["figures"] and not units[5]["figures"]          # text pages aren't rendered
    fig = units[3]["figures"][0]
    assert fig["why"] == "figure" and (corpus_of(course) / fig["path"]).exists() and fig["w"] >= 1000


def test_scanned_paper_is_image_only_and_every_paper_page_is_rendered(ingested):
    course, _ = ingested
    rec = record(course, "papers/2024-midsem.pdf")
    assert [u["flags"] for u in rec["units"]] == [["image-only"], ["image-only"]]
    assert all(u["figures"][0]["why"] == "paper" for u in rec["units"])
    assert any("no text layer" in w for w in rec["warnings"])
    key = record(course, "papers/2024-midsem-key.pdf")
    assert key["units"][0]["figures"][0]["why"] == "paper"
    assert {"56", "156"} <= set(key["units"][0]["text"].split())


def test_answer_keys_are_matched_to_papers_by_name(ingested):
    course, res = ingested
    papers = {p["path"]: p for p in index(course)["papers"]}
    assert papers["papers/2024-midsem.pdf"]["key"] == "papers/2024-midsem-key.pdf"
    assert papers["papers/2024-midsem-key.pdf"]["key_for"] == "papers/2024-midsem.pdf"
    assert papers["papers/sample-questions.pdf"]["year"] is None
    assert any("2023-compre-sol.pdf: answer key with no matching paper" in w for w in res.warnings)
    assert "answer key: papers/2024-midsem-key.pdf" in view(course, "papers/2024-midsem.pdf")


def test_incremental_slide_builds_are_deduplicated(ingested):
    course, res = ingested
    dups = json.loads((corpus_of(course) / "dedupe.json").read_text())
    assert dups == {"slides/07-sched.pdf#p2": "slides/07-sched.pdf#p3"}
    v = view(course, "slides/07-sched.pdf")
    assert "## p2 · near-duplicate of slides/07-sched.pdf#p3 (omitted)" in v
    assert res.stats["duplicates"] == 1


def test_pptx_slides_notes_tables_and_pictures(ingested):
    course, _ = ingested
    rec = record(course, "slides/08-paging.pptx")
    u1, u2, u3 = rec["units"]
    assert u1["ref"] == "slides/08-paging.pptx#s1" and u1["title"] == "Paging 1"         # first line only
    assert u1["text"].startswith("Paging 1\nVirtual memory, part 1\n")
    assert "  The TLB caches recent translations." in u1["text"]        # level-1 bullet indented
    assert "| Bits | Meaning |" in u2["text"] and u2["notes"] == "Stress that the TLB is a cache."
    assert not u1["figures"]                                            # the logo on every slide is skipped
    assert len(u3["figures"]) == 1 and u3["figures"][0]["why"] == "embedded"


def test_docx_sections_lists_tables_images(ingested):
    course, _ = ingested
    units = record(course, "notes/deadlock.docx")["units"]
    assert [u["title"] for u in units] == ["Deadlock", "Banker's algorithm"]
    assert units[0]["ref"] == "notes/deadlock.docx#sec1"
    assert "- Mutual exclusion" in units[0]["text"]
    assert "| P0 | 7 4 3 |" in units[1]["text"] and len(units[1]["figures"]) == 1


def test_transparent_images_are_composited_onto_white(ingested):
    import pymupdf
    course, _ = ingested
    fig = record(course, "labs/lab1/datapath.png")["units"][0]["figures"][0]
    pix = pymupdf.Pixmap(str(corpus_of(course) / fig["path"]))
    assert (fig["w"], fig["h"]) == (300, 200)
    assert min(pix.pixel(250, 150)) > 240 and max(pix.pixel(60, 60)) < 15   # background white, box black


def test_markdown_splits_at_headings_but_not_inside_code(ingested):
    course, _ = ingested
    units = record(course, "notes/summary.md")["units"]
    assert [u["title"] for u in units] == ["Scheduling", "Paging"]
    assert units[0]["ref"] == "notes/summary.md#L1-9" and "# not a heading" in units[0]["text"]


def test_code_is_verbatim_and_fenced_with_its_language(ingested):
    course, _ = ingested
    u = record(course, "labs/lab1/sum.asm")["units"][0]
    assert u["text"] + "\n" == MIPS and u["lang"] == "mipsasm" and u["ref"] == "labs/lab1/sum.asm#L1-9"
    v = view(course, "labs/lab1/sum.asm")
    assert "```mipsasm\n# sum 1..10\n" in v
    assert record(course, "labs/lab1/main.c")["units"][0]["text"].endswith("return 0;\n}")


# --------------------------------------------------------------------------- caching and resuming

def test_second_run_reprocesses_nothing_and_changes_nothing(course):
    ingest(course, log=quiet)
    before = snapshot(course)
    res = ingest(course, log=quiet)
    assert res.extracted == [] and len(res.cached) == 15 and res.views_written == 0
    assert snapshot(course) == before
    st = Manifest.load(course / "_studymap" / "state.json")
    assert st.stages["ingest"].status == "done" and len(st.sources) == 15


def test_changed_added_and_removed_files_only(course):
    ingest(course, log=quiet)
    (course / "labs" / "lab1" / "main.c").write_text("int main(void) { return 1; }\n")
    (course / "labs" / "lab1" / "new.py").write_text("print('new')\n")
    (course / "tutorials" / "t1.txt").unlink()
    old_sid = "tutorials-t1-txt"
    assert (corpus_of(course) / "sources" / f"{old_sid}.json").exists()
    res = ingest(course, log=quiet)
    assert res.extracted == ["labs/lab1/main.c", "labs/lab1/new.py"]
    assert res.removed == ["tutorials/t1.txt"]
    assert not (corpus_of(course) / "sources" / f"{old_sid}.json").exists()
    assert not (corpus_of(course) / "text" / f"{old_sid}.md").exists()
    assert record(course, "labs/lab1/main.c")["units"][0]["text"] == "int main(void) { return 1; }"


def test_touched_but_identical_file_is_not_reextracted(course):
    ingest(course, log=quiet)
    p = course / "slides" / "07-sched.pdf"
    os.utime(p, ns=(p.stat().st_atime_ns, p.stat().st_mtime_ns + 10**9))
    res = ingest(course, log=quiet)
    assert res.extracted == []


def test_extractor_version_bump_reextracts_that_type_only(course, monkeypatch):
    ingest(course, log=quiet)
    monkeypatch.setitem(ingest_mod.EXTRACTOR, "code", ingest_mod.EXTRACTOR["code"] + 1)
    res = ingest(course, log=quiet)
    assert res.extracted == ["labs/lab1/Makefile", "labs/lab1/boot.S", "labs/lab1/main.c", "labs/lab1/sum.asm"]


def test_interrupted_run_resumes_where_it_stopped(course, monkeypatch):
    real, calls = ingest_mod.run_job, []

    def flaky(job):
        calls.append(job["rel"])
        if len(calls) == 5:
            raise KeyboardInterrupt
        return real(job)

    monkeypatch.setattr(ingest_mod, "run_job", flaky)
    with pytest.raises(KeyboardInterrupt):
        ingest(course, jobs=1, log=quiet)
    st = Manifest.load(course / "_studymap" / "state.json")
    assert st.stages["ingest"].status == "running" and len(st.sources) == 4
    monkeypatch.setattr(ingest_mod, "run_job", real)
    res = ingest(course, jobs=1, log=quiet)
    assert res.resumed and len(res.cached) == 4 and len(res.extracted) == 11


def test_a_broken_file_fails_alone_and_is_retried(course):
    (course / "slides" / "broken.pdf").write_bytes(b"%PDF-1.4 this is not really a pdf")
    res = ingest(course, log=quiet)
    assert [r for r, _ in res.failed] == ["slides/broken.pdf"]
    assert len(index(course)["sources"]) == 15 and index(course)["failed"][0]["path"] == "slides/broken.pdf"
    assert Manifest.load(course / "_studymap" / "state.json").stages["ingest"].status == "failed"
    res = ingest(course, log=quiet)
    assert res.extracted == [] and [r for r, _ in res.failed] == ["slides/broken.pdf"]


def test_same_course_gives_identical_corpus_in_a_fresh_process(course_template, tmp_path):
    """Determinism across processes and hash seeds (set iteration order must not leak into output)."""
    outs = []
    for seed in ("1", "2"):
        dst = tmp_path / f"run{seed}" / "CS-F999"
        shutil.copytree(course_template, dst)
        env = dict(os.environ, PYTHONHASHSEED=seed)
        subprocess.run([sys.executable, "-m", "studymap", "ingest", str(dst), "-q"], check=True, env=env,
                       capture_output=True)
        outs.append(snapshot(dst))
    assert len(outs[0]) > 30 and outs[0] == outs[1]


# --------------------------------------------------------------------------- helpers

def test_clean_text():
    s = "ﬁle  system" + chr(0xF0B7) + " item\n\n\n\n   padded     line   \r\nend"
    assert clean_text(s) == "file  system• item\n\npadded  line\nend"   # padding runs shrink to two spaces


def test_control_bytes_from_unmapped_glyphs_become_replacement_chars():
    assert clean_text("PC " + chr(0) + " PC[31:28]" + chr(0x1F)) == "PC " + chr(0xFFFD) + " PC[31:28]" + chr(0xFFFD)
    assert clean_text("a" + chr(0x0C) + "b" + chr(0x0B) + "c" + chr(9) + "d") == "a\nb\nc" + chr(9) + "d"


def test_asm_flavour():
    assert asm_flavour(MIPS) == "mipsasm"
    assert asm_flavour(X86) == "x86asm"
    assert asm_flavour("; nothing\n") == "plaintext"


def test_dedupe_keeps_the_most_complete_and_never_touches_papers():
    a = "the quick brown fox jumps over the lazy dog near the river bank today"
    b = a + " and then it runs far away into the forest"
    units = [("s.pdf#p1", "slides", a), ("s.pdf#p2", "slides", b), ("s.pdf#p3", "slides", b),
             ("p.pdf#p1", "papers", a), ("p.pdf#p2", "papers", b)]
    assert find_duplicates(units) == {"s.pdf#p1": "s.pdf#p2", "s.pdf#p3": "s.pdf#p2"}


def test_sids_are_stable_and_collision_free():
    s = make_sids(["slides/a b.pdf", "slides/a-b.pdf", "notes/x.md"])
    assert s["notes/x.md"] == "notes-x-md"
    assert s["slides/a b.pdf"] != s["slides/a-b.pdf"] and s["slides/a b.pdf"].startswith("slides-a-b-pdf-")
