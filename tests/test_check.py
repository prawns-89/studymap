"""`studymap check` in a real headless browser, with the network blocked."""
import pytest

from studymap.cli import main

from .conftest import EXAMPLES, write_analysis

pytestmark = pytest.mark.browser


def _browser_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        from studymap.check import launch
        with sync_playwright() as p:
            b, _ = launch(p)
            b.close()
        return True
    except Exception:
        return False


needs_browser = pytest.mark.skipif(not _browser_available(), reason="no Chromium or Chrome for Playwright")


@needs_browser
def test_check_passes_offline_on_every_viewport(tmp_path, capsys):
    html = tmp_path / "index.html"
    assert main(["build", str(EXAMPLES / "photosynthesis"), "-o", str(html)]) == 0
    shots = tmp_path / "shots"
    assert main(["check", str(tmp_path), "--html", str(html), "--shots", str(shots)]) == 0
    out = capsys.readouterr().out
    assert "check passed" in out and "network blocked" in out
    names = {p.name for p in shots.glob("*.png")}
    for vp in ("desktop", "desktop-dark", "phone", "phone-dark"):
        assert {f"{vp}-1-map.png", f"{vp}-2-node.png", f"{vp}-3-atlas.png",
                f"{vp}-4-sheets.png", f"{vp}-5-questions.png"} <= names


@needs_browser
def test_check_fails_on_a_script_error(tmp_path, capsys):
    html = tmp_path / "index.html"
    assert main(["build", str(EXAMPLES / "photosynthesis"), "-o", str(html)]) == 0
    page = html.read_text(encoding="utf-8").replace("</body>", "<script>throw new Error('boom')</script></body>")
    html.write_text(page, encoding="utf-8")
    assert main(["check", str(tmp_path), "--html", str(html), "--shots", str(tmp_path / "s")]) == 1
    assert "boom" in capsys.readouterr().out


@needs_browser
def test_check_exercises_the_plan_tab(ingested_course, capsys):
    write_analysis(ingested_course)
    assert main(["build", str(ingested_course)]) == 0
    assert main(["check", str(ingested_course)]) == 0
    out = capsys.readouterr().out
    assert "plan: 5 topic bars, 1 exams" in out and "check passed" in out
    shots = {p.name for p in (ingested_course / "_studymap" / "check").glob("*.png")}
    assert {"desktop-0-plan.png", "phone-dark-0-plan.png"} <= shots and not any("map" in s for s in shots)
