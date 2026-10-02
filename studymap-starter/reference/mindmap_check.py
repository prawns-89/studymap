#!/usr/bin/env python3
"""Smoke-test a built mind map in headless Chromium: page errors, a node click, and screenshots.

Usage:  python3 mindmap_check.py OUT_HTML [SHOTS_DIR]
For true-to-life label widths run `npm i @fontsource-variable/anek-latin` in this folder first;
without it the page falls back to a system font, so labels look wider than they will live.
"""
import os, sys
from playwright.sync_api import sync_playwright

src = os.path.abspath(sys.argv[1])
shots = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else "shots")
os.makedirs(shots, exist_ok=True)
page = os.path.join(shots, "_page.html")  # the publisher wraps the page in a document skeleton; do the same
with open(page, "w", encoding="utf-8") as f:
    f.write('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, '
            'initial-scale=1"></head><body>' + open(src, encoding="utf-8").read() + "</body></html>")
FONT = "node_modules/@fontsource-variable/anek-latin/files/anek-latin-{}-standard-normal.woff2"
woff = {s: FONT.format(s) for s in ("latin", "latin-ext") if os.path.exists(FONT.format(s))}


def face(sub, rng):
    return ('@font-face{font-family:"Anek Latin";font-weight:100 800;font-stretch:75% 125%;'
            f'src:url(https://fonts.gstatic.com/local/{sub}.woff2) format("woff2");unicode-range:{rng}}}')


CSS = face("latin", "U+0000-00FF,U+2000-206F,U+20AC,U+2122,U+2190-2193,U+2212") + face("latin-ext", "U+0100-02FF,U+1E00-1EFF")
NEAREST = """() => { const s = document.getElementById('stage').getBoundingClientRect(); let best = null, bd = 1e9;
  for (const c of document.querySelectorAll('#g-node .node circle')) { const r = c.getBoundingClientRect();
    const d = Math.hypot(r.x + r.width / 2 - s.x - s.width / 2, r.y + r.height / 2 - s.y - s.height / 2);
    if (d < bd) { bd = d; best = [r.x + r.width / 2, r.y + r.height / 2]; } } return best; }"""
errors = []


def fonts(route):
    url = route.request.url
    if woff and "fonts.googleapis.com" in url:
        return route.fulfill(status=200, content_type="text/css", body=CSS)
    sub = url.rsplit("/", 1)[-1][:-6]
    if "/local/" in url and sub in woff:
        return route.fulfill(status=200, content_type="font/woff2", body=open(woff[sub], "rb").read())
    return route.abort()


with sync_playwright() as p:
    browser = p.chromium.launch(args=["--no-sandbox"])
    for name, w, h, scheme in [("desktop", 1440, 900, "light"), ("desktop-dark", 1440, 900, "dark"), ("phone", 390, 844, "light")]:
        ctx = browser.new_context(viewport={"width": w, "height": h}, color_scheme=scheme)
        pg = ctx.new_page()
        pg.on("pageerror", lambda e, n=name: errors.append(f"{n}: {e}"))
        pg.on("console", lambda m, n=name: errors.append(f"{n}: {m.text}")
              if m.type == "error" and "Failed to load resource" not in m.text else None)
        pg.route("**/fonts.googleapis.com/**", fonts)
        pg.route("**/fonts.gstatic.com/**", fonts)
        pg.goto("file://" + page)
        pg.wait_for_timeout(700)
        pg.screenshot(path=f"{shots}/{name}-1-map.png")
        pt = pg.evaluate(NEAREST)
        if pt:
            pg.mouse.click(*pt)
            pg.wait_for_timeout(600)
            print(f"{name}: clicked a node, panel shows {pg.locator('#panel .facts li').count()} facts")
            pg.screenshot(path=f"{shots}/{name}-2-node.png")
        for i, view in enumerate(["atlas", "sheets", "questions"], 3):
            tab = pg.locator(f'.tab[data-view="{view}"]')
            if tab.is_visible():
                tab.click()
                pg.wait_for_timeout(300)
                pg.screenshot(path=f"{shots}/{name}-{i}-{view}.png")
        ctx.close()
    browser.close()
print("fonts:", "Anek Latin from node_modules" if woff else "fallback (install @fontsource-variable/anek-latin for real widths)")
print("page errors:", "none" if not errors else "\n  " + "\n  ".join(errors))
print("screenshots in", shots)
