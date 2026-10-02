"""Text clean-up and image saving shared by the extractors."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pymupdf

LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"}
_LIG = re.compile("|".join(LIGATURES))
_PUA = re.compile(f"[{chr(0xE000)}-{chr(0xF8FF)}]")      # symbol-font bullets come out as private-use characters
_NBSP, _ZWSP = chr(0xA0), chr(0x200B)
_CTRL = re.compile(r"[\x00-\x08\x0e-\x1f\x7f]")   # unmapped glyphs come out as control bytes
_SPACES = re.compile(f"[ \t{_NBSP}{chr(0x2000)}-{chr(0x200A)}{chr(0x202F)}]{{2,}}")   # runs of layout padding
JPEG_QUALITY = 85


def clean_text(s: str) -> str:
    """Normalise extracted prose: NFC, ligatures, bullets, layout padding, blank-line runs."""
    s = unicodedata.normalize("NFC", s.replace("\r\n", "\n").replace("\r", "\n").replace("\v", "\n"))
    s = _LIG.sub(lambda m: LIGATURES[m.group(0)], s)
    s = _CTRL.sub(chr(0xFFFD), _PUA.sub("•", s)).replace(_NBSP, " ").replace(_ZWSP, "").replace("\x0c", "\n")
    lines = [_SPACES.sub("  ", ln).strip() for ln in s.split("\n")]
    out, blank = [], 0
    for ln in lines:
        blank = blank + 1 if not ln else 0
        if blank <= 1:
            out.append(ln)
    return "\n".join(out).strip()


def first_line(text: str, limit: int = 120) -> str:
    for ln in text.split("\n"):
        ln = ln.strip(" •●○▪■-–—*#\t")
        if len(ln) >= 2:
            return ln[:limit]
    return ""


def char_count(text: str) -> int:
    return len(" ".join(text.split()))


def save_pixmap(pix: pymupdf.Pixmap, dest: Path, max_side: int = 1600) -> tuple[int, int]:
    """Save an opaque pixmap as JPEG (small, fine for reading), halving it until the long side fits."""
    if pix.colorspace is None or pix.colorspace.n not in (1, 3):
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)      # CMYK and friends -> RGB
    while max(pix.width, pix.height) > max_side * 1.5:
        pix.shrink(1)
    dest.parent.mkdir(parents=True, exist_ok=True)
    pix.save(str(dest), jpg_quality=JPEG_QUALITY)
    return pix.width, pix.height


def save_image_bytes(blob: bytes, dest: Path, max_side: int = 1600) -> tuple[int, int] | None:
    """Re-encode an embedded or standalone image; None if pymupdf can't decode it (e.g. WMF/EMF).
    Images with transparency are rendered onto white, so draw.io-style diagrams don't turn black."""
    try:
        src = pymupdf.Pixmap(blob)
    except Exception:
        return None
    if src.width < 24 or src.height < 24:
        return None
    if not src.alpha:
        return save_pixmap(src, dest, max_side)
    page = pymupdf.open(stream=blob)[0]
    zoom = src.width / (page.rect.width or src.width)
    return save_pixmap(page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False), dest, max_side)
