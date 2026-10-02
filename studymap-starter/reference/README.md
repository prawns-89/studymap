# Reference kit

Working, tested version of the map + question site (see BRIEF.md section 10).

Build an example:

    pip install numpy
    python3 mindmap_build.py examples/photosynthesis mindmap_template.html out.html
    python3 mindmap_build.py examples/hss-f338 mindmap_template.html hss.html

Smoke test (needs Playwright + Chromium; optional real label font via `npm i @fontsource-variable/anek-latin`):

    python3 mindmap_check.py out.html shots

- mindmap_build.py: parser, validator, deterministic layout, JSON injection
- mindmap_template.html: entire front end (CSS + JS), data injected at /*__DATA__*/null
- mindmap_check.py: headless check: page errors, node click, screenshots desktop/phone, light/dark
- examples/: content in the line-based DSL (map.txt, sheets.txt, set-*.txt)
- examples/hss-f338.html: the built page for the full course example
