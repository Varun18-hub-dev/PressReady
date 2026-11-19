"""Render a preflight Report as JSON or as one self-contained HTML page."""

from __future__ import annotations

import base64
import html
import json

import numpy as np
import pymupdf

from . import ink
from .checks import PageInk, Report


def to_json(report: Report) -> str:
    return json.dumps(report.to_dict(), indent=2)


# ------------------------------------------------------------------ images

def _png(rgb: np.ndarray) -> str:
    h, w, _ = rgb.shape
    pix = pymupdf.Pixmap(pymupdf.csRGB, w, h, np.ascontiguousarray(rgb, dtype=np.uint8).tobytes(), 0)
    return "data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode()


def cmyk_to_rgb(cmyk: np.ndarray) -> np.ndarray:
    """Naive device conversion, for on-screen previews only."""
    c, m, y, k = (cmyk[..., i].astype(np.float32) / 255 for i in range(4))
    rgb = np.stack([(1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k)], axis=-1)
    return (rgb * 255).round().astype(np.uint8)


def tac_heatmap(tac: np.ndarray, limit: float) -> np.ndarray:
    """Grey ramp for coverage under the limit, solid red where it is exceeded."""
    shade = (255 - np.clip(tac / limit, 0, 1) * 160).astype(np.uint8)
    rgb = np.repeat(shade[..., None], 3, axis=2)
    rgb[tac > limit] = (220, 38, 38)
    return rgb


def screened_preview(cmyk: np.ndarray) -> np.ndarray:
    """What a 1-bit RIP output would look like: each separation error-diffused."""
    return cmyk_to_rgb(ink.halftone_fs(cmyk))


# ------------------------------------------------------------------ html

_CSS = """
body{font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;margin:0;background:#f6f7f9;color:#1f2328}
main{max-width:1100px;margin:0 auto;padding:32px 24px}
h1{font-size:22px;margin:0 0 4px}.sub{color:#59636e;margin:0 0 24px}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-weight:600;font-size:13px}
.PASS{background:#dafbe1;color:#116329}.WARN{background:#fff8c5;color:#7d4e00}.FAIL{background:#ffebe9;color:#a40e26}
.card{background:#fff;border:1px solid #d1d9e0;border-radius:10px;padding:20px;margin-bottom:20px}
table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:8px;border-top:1px solid #eaeef2;vertical-align:top}
th{border-top:0;color:#59636e;font-weight:600;font-size:13px}
.error{color:#a40e26;font-weight:600}.warn{color:#7d4e00;font-weight:600}
.pages{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
figure{margin:0}figure img{width:100%;border:1px solid #d1d9e0;border-radius:6px;image-rendering:pixelated}
figcaption{font-size:12px;color:#59636e;margin-top:4px}
code{font-size:12px;color:#59636e}
"""


def _page_block(p: PageInk, limit: float) -> str:
    return f"""
<div class="card"><h3 style="margin-top:0">Page {p.page}
  <span style="font-weight:400;color:#59636e">· max ink {p.max_pct:.0f}% · mean {p.mean_pct:.0f}%
  · {p.over_fraction:.1%} over limit</span></h3>
<div class="pages">
  <figure><img alt="page preview" src="{_png(cmyk_to_rgb(p.cmyk))}"><figcaption>Page (CMYK raster)</figcaption></figure>
  <figure><img alt="ink heatmap" src="{_png(tac_heatmap(p.tac_map, limit))}"><figcaption>Ink coverage · red = over {limit:.0f}%</figcaption></figure>
  <figure><img alt="screened preview" src="{_png(screened_preview(p.cmyk))}"><figcaption>Screened preview (Floyd–Steinberg, per separation)</figcaption></figure>
</div></div>"""


def to_html(report: Report) -> str:
    d = report.to_dict()
    rows = "".join(
        f"<tr><td class='{i['severity']}'>{i['severity'].upper()}</td><td>{i['page'] or '–'}</td>"
        f"<td>{html.escape(i['check'])}</td><td>{html.escape(i['message'])}"
        f"{'<br><code>' + html.escape(json.dumps(i['detail'])) + '</code>' if i['detail'] else ''}</td></tr>"
        for i in d["issues"]
    ) or "<tr><td colspan=4>No issues found.</td></tr>"
    prof = report.profile
    pages = "".join(_page_block(p, prof.tac_limit_pct) for p in report.ink)
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Preflight · {html.escape(report.file)}</title><style>{_CSS}</style></head><body><main>
<h1>{html.escape(report.file)} <span class="badge {report.status}">{report.status}</span></h1>
<p class="sub">{report.pages} page(s) · {len(report.errors)} error(s), {len(report.warnings)} warning(s) ·
profile <b>{html.escape(prof.name)}</b> (bleed {prof.bleed_mm} mm, images ≥{prof.min_dpi_warn:.0f} dpi,
ink ≤{prof.tac_limit_pct:.0f}%) · pixel engine: {report.backend}</p>
<div class="card"><table><tr><th>Severity</th><th>Page</th><th>Check</th><th>Finding</th></tr>{rows}</table></div>
{pages}
</main></body></html>"""
