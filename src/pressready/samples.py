"""Two sample print jobs: one print-ready, one with the classic prepress mistakes.

Used by the tests, the web UI's "try a sample" buttons and examples/make_samples.py.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pymupdf

MM = 72 / 25.4
A4 = (210 * MM, 297 * MM)


def _photo(px: int, channels: int) -> np.ndarray:
    """A smooth synthetic 'photo': radial gradient plus soft rings."""
    y, x = np.mgrid[0:px, 0:px] / px
    r = np.hypot(x - 0.5, y - 0.5)
    base = 0.5 + 0.5 * np.cos(r * 18)
    chans = [base * (0.6 + 0.4 * x), base * (0.4 + 0.6 * y), (1 - base) * 0.8, r * 0.6][:channels]
    return (np.clip(np.stack(chans, axis=-1), 0, 1) * 255).astype(np.uint8)


def _image(page: pymupdf.Page, rect: pymupdf.Rect, px: int, cmyk: bool) -> None:
    cs, n = (pymupdf.csCMYK, 4) if cmyk else (pymupdf.csRGB, 3)
    pix = pymupdf.Pixmap(cs, px, px, _photo(px, n).tobytes(), 0)
    page.insert_image(rect, pixmap=pix)


def _page_with_bleed(doc: pymupdf.Document, bleed_mm: float) -> pymupdf.Page:
    b = bleed_mm * MM
    page = doc.new_page(width=A4[0] + 2 * b, height=A4[1] + 2 * b)
    page.set_trimbox(pymupdf.Rect(b, b, b + A4[0], b + A4[1]))
    page.set_bleedbox(page.mediabox)
    return page


def _embedded_text(page: pymupdf.Page, pos, text: str, size: float, color) -> None:
    tw = pymupdf.TextWriter(page.rect, color=color)
    tw.append(pos, text, font=pymupdf.Font("cjk"), fontsize=size)  # embedded TrueType
    tw.write_text(page)


def make_good(path: Path) -> Path:
    doc = pymupdf.open()
    page = _page_with_bleed(doc, bleed_mm=3)
    b = 3 * MM
    page.draw_rect(page.mediabox, fill=(0.04, 0.0, 0.08, 0.0), color=None)   # background runs into bleed
    page.draw_rect(pymupdf.Rect(0, 0, page.rect.width, b + 60 * MM), fill=(0.9, 0.4, 0.0, 0.1), color=None)
    _embedded_text(page, (b + 20 * MM, b + 35 * MM), "Spring Catalogue", 34, (0, 0, 0, 0))
    _image(page, pymupdf.Rect(b + 20 * MM, b + 80 * MM, b + 120 * MM, b + 180 * MM), px=1200, cmyk=True)
    _embedded_text(page, (b + 20 * MM, b + 200 * MM), "Rich black heading, 260% ink", 18, (0.6, 0.5, 0.5, 1.0))
    _embedded_text(page, (b + 20 * MM, b + 212 * MM), "Body text in pure black.", 11, (0, 0, 0, 1))
    doc.subset_fonts()
    doc.save(path, garbage=3, deflate=True)
    return path


def make_bad(path: Path) -> Path:
    doc = pymupdf.open()

    # Page 1: no TrimBox, low-res RGB images, non-embedded font, 400% ink block.
    p1 = doc.new_page(width=A4[0], height=A4[1])
    p1.insert_text((20 * MM, 30 * MM), "Summer Sale", fontname="helv", fontsize=34)   # Helvetica, not embedded
    _image(p1, pymupdf.Rect(20 * MM, 45 * MM, 100 * MM, 125 * MM), px=120, cmyk=False)   # ~38 dpi, RGB
    _image(p1, pymupdf.Rect(110 * MM, 45 * MM, 140 * MM, 75 * MM), px=200, cmyk=False)   # ~169 dpi, RGB
    p1.draw_rect(pymupdf.Rect(20 * MM, 140 * MM, 190 * MM, 270 * MM), fill=(1, 1, 1, 1), color=None)  # 400%

    # Page 2: TrimBox present but only 1 mm of bleed.
    p2 = _page_with_bleed(doc, bleed_mm=1)
    p2.draw_rect(p2.mediabox, fill=(0.0, 0.2, 0.9, 0.0), color=None)
    _embedded_text(p2, (25 * MM, 40 * MM), "Back cover", 28, (0, 0, 0, 1))

    doc.subset_fonts()
    doc.save(path, garbage=3, deflate=True)
    return path
