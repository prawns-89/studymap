"""PDF: text per page with provenance, plus page renders where the picture carries the content."""
from __future__ import annotations

import re
import statistics
from collections import Counter
from pathlib import Path

import pymupdf

from .common import char_count, clean_text, first_line, save_pixmap
from .records import Figure, Unit

LOW_TEXT = 100        # characters: below this a page is read visually (diagram, title-only slide)
IMAGE_ONLY_TEXT = 25  # characters: below this, with most of the page an image, the page is a scan or a picture
IMAGE_ONLY_AREA = 0.5
FIGURE_AREA = 0.10    # share of the page covered by images that aren't repeated template decoration
RENDER_SIDE = {"paper": 1700, "image-only": 1700}   # long side in px; everything else 1400
SAME_SPOT = 3.0       # pt: a line repeated this close to an earlier copy is a shadow/outline effect


def _page_blocks(page) -> list[list[tuple[str, tuple]]]:
    """Lines in content-stream order (keeps columns intact), grouped by block, each with a position key.
    Text drawn twice at the same spot (shadow and outline effects) is kept once."""
    d = page.get_text("dict", flags=pymupdf.TEXTFLAGS_TEXT)
    seen, blocks = [], []
    for b in d["blocks"]:
        if b.get("type") != 0:
            continue
        lines = []
        for ln in b["lines"]:
            t = "".join(s["text"] for s in ln["spans"]).strip()
            if not t:
                continue
            x0, y0 = ln["bbox"][:2]
            if any(t == st and abs(x0 - sx) < SAME_SPOT and abs(y0 - sy) < SAME_SPOT for st, sx, sy in seen):
                continue
            seen.append((t, x0, y0))
            lines.append((t, (re.sub(r"\d+", "#", t), round(x0 / 12), round(y0 / 12))))
        if lines:
            blocks.append(lines)
    return blocks


def _boilerplate(pages: list[list[list[tuple[str, tuple]]]]) -> set[tuple]:
    """Running headers, footers and page numbers: the same text (digits ignored) at the same spot
    on at least half the pages. Position matters, so a number inside a table is never dropped."""
    if len(pages) < 4:
        return set()
    c = Counter()
    for blocks in pages:
        c.update({key for blk in blocks for _, key in blk})
    return {k for k, v in c.items() if v >= len(pages) * 0.5}


def extract_pdf(path: Path, rel: str, kind: str, img_dir: Path, img_rel: str):
    warnings: list[str] = []
    doc = pymupdf.open(path)          # a corrupt file raises: reported as failed, retried next run
    if doc.needs_pass and not doc.authenticate(""):
        return [], {"pages": 0}, ["password-protected: can't read it"]
    n = doc.page_count
    pages, infos, draws = [], [], []
    seen = Counter()
    for page in doc:
        try:
            info = page.get_image_info(hashes=True)
        except Exception:
            info = []
        try:
            dr = len(page.get_cdrawings())
        except Exception:
            dr = 0
        infos.append(info)
        draws.append(dr)
        seen.update({i["digest"] for i in info if i.get("digest")})
        pages.append(_page_blocks(page))
    # template decoration: the same image on at least half the pages (logos, footer strips, backgrounds)
    deco = {d for d, c in seen.items() if n >= 3 and c >= n * 0.5}
    med = statistics.median(draws) if draws else 0
    boiler = _boilerplate(pages)
    units = []
    for i, page in enumerate(doc):
        text = clean_text("\n\n".join("\n".join(t for t, key in blk if key not in boiler) for blk in pages[i]))
        chars = char_count(text)
        prect = page.rect
        parea = abs(prect) or 1.0
        all_area = min(1.0, sum(abs(pymupdf.Rect(im["bbox"]) & prect) for im in infos[i]) / parea)
        fig_area = min(1.0, sum(abs(pymupdf.Rect(im["bbox"]) & prect)
                                for im in infos[i] if im.get("digest") not in deco) / parea)
        flags = []
        if chars < IMAGE_ONLY_TEXT and all_area >= IMAGE_ONLY_AREA:
            flags.append("image-only")
        elif chars < LOW_TEXT:
            flags.append("low-text")
        if "image-only" not in flags and (fig_area >= FIGURE_AREA or draws[i] >= max(25, 2 * med + 10)):
            flags.append("figure")
        why = ("paper" if kind == "papers" else "image-only" if "image-only" in flags
               else "figure" if "figure" in flags else "low-text" if "low-text" in flags else "")
        figs = []
        if why:
            try:
                zoom = RENDER_SIDE.get(why, 1400) / max(prect.width, prect.height, 1)
                pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
                name = f"p{i + 1:03d}.jpg"
                w, h = save_pixmap(pix, img_dir / name, max_side=2000)
                figs.append(Figure(path=f"{img_rel}/{name}", why=why, w=w, h=h))
            except Exception as e:
                warnings.append(f"p{i + 1}: render failed: {e}")
        units.append(Unit(ref=f"{rel}#p{i + 1}", n=i + 1, title=first_line(text) if kind == "slides" else "",
                          text=text, chars=chars, flags=flags, figures=figs))
    meta = {"pages": n, "title": (doc.metadata or {}).get("title", "") or "",
            "image_only_pages": sum("image-only" in u.flags for u in units)}
    if n and meta["image_only_pages"] == n:
        warnings.append("no text layer on any page (scanned?): read the page images")
    return units, meta, warnings
