"""The Lessons tab's Markdown renderer and loader (render/docs.py)."""
from studymap.render.docs import load_docs, render_doc


def test_blocks_render():
    md = ("# Title\n\n## A section\n\nText with `code`, **bold**, *it* and \\*literal\\*.\n\n"
          "1. one\n   ```c\n   int x;\n   ```\n2. two\n   - nested\n\n> a quote\n\n---\n\n"
          "<details><summary>Answer</summary>\n\n| a | b |\n|---|---|\n| 1 | 2 |\n</details>\n")
    html, toc = render_doc(md, set())
    assert '<h1 id="d-title">Title</h1>' in html
    assert toc == [["a-section", "A section"]]
    assert "<code>code</code>" in html and "<b>bold</b>" in html and "<i>it</i>" in html and "*literal*" in html
    assert '<ol><li>one<pre><code class="language-c">int x;</code></pre></li><li>two<ul><li>nested</li></ul></li></ol>' in html
    assert "<blockquote><p>a quote</p></blockquote>" in html and "<hr>" in html
    assert "<details><summary>Answer</summary><div class=\"tblwrap\"><table" in html


def test_html_is_escaped():
    html, _ = render_doc("a <script>x</script> & `<b>`", set())
    assert "<script>" not in html and "&lt;script&gt;" in html and "<code>&lt;b&gt;</code>" in html


def test_table_cells_keep_pipes_inside_code():
    html, _ = render_doc("| a | b |\n|---|---|\n| ``undefined `f'`` | `x|y` |\n", set())
    assert "<td><code>undefined `f'</code></td><td><code>x|y</code></td>" in html


def test_links_between_documents():
    html, _ = render_doc("[next](02-b.md#sec) [self](#here) [gone](other.md) [web](https://e.org) [**b** `c`](02-b.md)", {"02-b"})
    assert "><b>b</b> <code>c</code></a>" in html
    assert 'href="#docs/02-b" data-doc="02-b" data-frag="sec"' in html
    assert 'data-frag="here"' in html
    assert '<a href="other.md" target="_blank" rel="noopener">gone</a>' in html   # no base: left as written
    assert 'href="https://e.org" target="_blank"' in html


def test_duplicate_headings_get_unique_ids():
    html, toc = render_doc("## Practice\n\n## Practice\n", set())
    assert 'id="d-practice"' in html and 'id="d-practice-2"' in html and len(toc) == 2


def test_load_docs_orders_readme_first(tmp_path):
    (tmp_path / "lessons").mkdir()
    for name, text in [("02-b.md", "# B"), ("README.md", "# Index\n\n[b](02-b.md)"), ("01-a.md", "no heading")]:
        (tmp_path / "lessons" / name).write_text(text, encoding="utf-8")
    docs, files = load_docs(tmp_path)
    assert [d["id"] for d in docs] == ["README", "01-a", "02-b"]
    assert docs[1]["title"] == "01-a" and docs[2]["title"] == "B" and len(files) == 3
    assert 'data-doc="02-b"' in docs[0]["html"]
    assert load_docs(tmp_path / "nowhere") == ([], [])


def test_file_links_are_re_aimed_from_the_page(tmp_path):
    (tmp_path / "lessons").mkdir(); (tmp_path / "papers").mkdir(); (tmp_path / "_studymap").mkdir()
    (tmp_path / "papers" / "2024 midsem.pdf").write_bytes(b"%PDF")
    missing: list[str] = []
    html, _ = render_doc("[paper](../papers/2024%20midsem.pdf#page=3) [gone](../papers/nope.pdf)", set(),
                         base=tmp_path / "lessons", out=tmp_path / "_studymap", missing=missing)
    assert '<a href="../papers/2024%20midsem.pdf#page=3" target="_blank"' in html
    assert '<span class="xref" title="missing: ../papers/nope.pdf">gone</span>' in html
    assert missing == ["../papers/nope.pdf"]
    elsewhere = tmp_path / "out" / "deep"
    elsewhere.mkdir(parents=True)
    html, _ = render_doc("[paper](../papers/2024%20midsem.pdf)", set(), base=tmp_path / "lessons", out=elsewhere)
    assert 'href="../../papers/2024%20midsem.pdf"' in html
