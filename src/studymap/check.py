"""`studymap check`: open the built site in headless Chromium with the network blocked.

Ported from reference/mindmap_check.py and extended: four viewports (desktop and phone, light and dark),
fails on page or console errors, on missing map nodes, on a node click or keyboard selection that shows
no facts, and on horizontal scrolling. Screenshots go to _studymap/check/.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

VIEWPORTS = [("desktop", 1440, 900, "light"), ("desktop-dark", 1440, 900, "dark"),
             ("phone", 390, 844, "light"), ("phone-dark", 390, 844, "dark")]
LOCAL = ("file:", "data:", "blob:", "about:")
NEAREST = """() => { const s = document.getElementById('stage').getBoundingClientRect(); let best = null, bd = 1e9;
  for (const c of document.querySelectorAll('#g-node .node circle')) { const r = c.getBoundingClientRect();
    const d = Math.hypot(r.x + r.width / 2 - s.x - s.width / 2, r.y + r.height / 2 - s.y - s.height / 2);
    if (d < bd) { bd = d; best = [r.x + r.width / 2, r.y + r.height / 2]; } } return best; }"""


@dataclass
class CheckResult:
    browser: str = ""
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    shots: list[Path] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


def launch(p):
    """Playwright's own Chromium if installed, else the system Chrome."""
    from playwright.sync_api import Error
    try:
        return p.chromium.launch(args=["--no-sandbox"]), "Playwright Chromium"
    except Error as e:
        if "Executable doesn't exist" not in str(e):
            raise
    try:
        return p.chromium.launch(channel="chrome", args=["--no-sandbox"]), "system Chrome"
    except Error:
        raise RuntimeError("no Chromium found: run `uv run playwright install chromium`") from None


def check(html: Path, shots: Path) -> CheckResult:
    from playwright.sync_api import sync_playwright
    res = CheckResult()
    shots.mkdir(parents=True, exist_ok=True)
    for old in shots.glob("*.png"):
        old.unlink()
    url = html.resolve().as_uri()
    blocked: Counter = Counter()

    def route(r):
        u = r.request.url
        if u.startswith(LOCAL):
            return r.continue_()
        blocked[urlparse(u).netloc or u[:40]] += 1
        return r.abort()

    with sync_playwright() as p:
        browser, res.browser = launch(p)
        try:
            for name, w, h, scheme in VIEWPORTS:
                errs: list[str] = []
                phone = w < 600
                ctx = browser.new_context(viewport={"width": w, "height": h}, color_scheme=scheme,
                                          is_mobile=phone, has_touch=phone)
                ctx.route("**/*", route)
                pg = ctx.new_page()
                pg.on("pageerror", lambda e: errs.append(f"page error: {e}"))
                pg.on("console", lambda m: errs.append(f"console: {m.text}")
                      if m.type == "error" and "Failed to load resource" not in m.text else None)
                pg.goto(url, wait_until="load")
                pg.wait_for_timeout(600)
                fail = lambda msg: res.failures.append(f"{name}: {msg}")

                expect = pg.evaluate("D.nodes.length - (D.cfg.center ? 1 : 0)")
                drawn = pg.locator("#g-node .node").count()
                if drawn != expect:
                    fail(f"map shows {drawn} nodes, data has {expect}")
                res.shots.append(_shot(pg, shots, f"{name}-1-map"))

                pt = pg.evaluate(NEAREST)
                if pt:
                    pg.mouse.click(*pt)
                    pg.wait_for_timeout(500)
                    nf = pg.locator("#panel .facts li").count()
                    if not nf:
                        fail("clicking a node opened no facts")
                    elif name == "desktop":
                        res.notes.append(f"clicked a node: panel shows {nf} facts")
                    res.shots.append(_shot(pg, shots, f"{name}-2-node"))

                pg.click("#z-fit")
                pg.evaluate("document.querySelector('#g-node .node').focus()")
                pg.keyboard.press("Enter")
                pg.wait_for_timeout(300)
                if not pg.locator("#panel .facts li").count():
                    fail("keyboard Enter on a focused node opened no facts")

                for i, view in enumerate(["atlas", "sheets", "questions"], 3):
                    tab = pg.locator(f'.tab[data-view="{view}"]')
                    if tab.is_visible():
                        tab.click()
                        pg.wait_for_timeout(300)
                        if pg.locator(f"#v-{view}").is_hidden():
                            fail(f"{view} tab didn't open its view")
                        res.shots.append(_shot(pg, shots, f"{name}-{i}-{view}"))

                over = pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")
                if over > 1:
                    fail(f"page scrolls horizontally by {over}px")
                for e in errs:
                    fail(e)
                ctx.close()
        finally:
            browser.close()
    if blocked:
        hosts = ", ".join(f"{h} ×{n}" for h, n in sorted(blocked.items()))
        res.warnings.append(f"blocked network requests: {hosts}. The page still works offline; "
                            "fonts fall back to system fonts until they are inlined (M6)")
    return res


def _shot(pg, d: Path, stem: str) -> Path:
    p = d / f"{stem}.png"
    pg.screenshot(path=str(p))
    return p
