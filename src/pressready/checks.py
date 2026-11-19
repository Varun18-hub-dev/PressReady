"""Preflight checks for print-ready PDFs.

Each check looks at one thing a prepress operator (or a RIP) would reject a job for:

    bleed      Is there a TrimBox, and does artwork extend far enough past it?
    images     Is every placed image at a high enough *effective* resolution?
    color      Are images RGB (needs conversion, color may shift) instead of CMYK/gray?
    fonts      Is every font embedded, so the press doesn't substitute one?
    ink        Does any area exceed the press's Total Area Coverage limit?
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

import numpy as np
import pymupdf

from . import ink

PT_PER_MM = 72 / 25.4
BLEED_TOLERANCE_MM = 0.05


class Severity(str, Enum):
    ERROR = "error"   # will print wrong; job should be held
    WARN = "warn"     # may print wrong; operator should look
    INFO = "info"


@dataclass(frozen=True)
class Profile:
    """Thresholds for a press condition. Defaults suit sheet-fed offset/digital on coated stock."""

    name: str = "commercial-coated"
    bleed_mm: float = 3.0
    min_dpi_error: float = 150.0
    min_dpi_warn: float = 300.0
    tac_limit_pct: float = 300.0
    tac_error_fraction: float = 0.01   # >1% of the page over the limit is an error
    raster_dpi: int = 72               # resolution used for ink analysis
    rgb_images: Severity = Severity.WARN


@dataclass
class Issue:
    severity: Severity
    check: str
    page: int | None   # 1-based; None for document-level issues
    message: str
    detail: dict = field(default_factory=dict)


@dataclass
class PageInk:
    page: int
    max_pct: float
    mean_pct: float
    over_fraction: float
    tac_map: np.ndarray = field(repr=False)
    cmyk: np.ndarray = field(repr=False)


@dataclass
class Report:
    file: str
    pages: int
    profile: Profile
    backend: str
    issues: list[Issue] = field(default_factory=list)
    ink: list[PageInk] = field(default_factory=list, repr=False)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == Severity.WARN]

    @property
    def status(self) -> str:
        if self.errors:
            return "FAIL"
        return "WARN" if self.warnings else "PASS"

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "status": self.status,
            "pages": self.pages,
            "backend": self.backend,
            "profile": {k: (v.value if isinstance(v, Enum) else v) for k, v in asdict(self.profile).items()},
            "summary": {"errors": len(self.errors), "warnings": len(self.warnings)},
            "issues": [{**asdict(i), "severity": i.severity.value} for i in self.issues],
            "ink": [
                {"page": p.page, "max_pct": round(p.max_pct, 1), "mean_pct": round(p.mean_pct, 1),
                 "over_fraction": round(p.over_fraction, 4)}
                for p in self.ink
            ],
        }


# ------------------------------------------------------------------ checks

def _has_key(doc: pymupdf.Document, xref: int, key: str) -> bool:
    return doc.xref_get_key(xref, key)[0] != "null"


def check_bleed(doc: pymupdf.Document, page: pymupdf.Page, profile: Profile) -> list[Issue]:
    pno = page.number + 1
    if not _has_key(doc, page.xref, "TrimBox"):
        return [Issue(Severity.WARN, "bleed", pno,
                      "No TrimBox: the finished size is undefined, so bleed cannot be verified.")]

    trim = page.trimbox
    # Artwork can only print up to the BleedBox (or MediaBox if there is none).
    outer = page.bleedbox if _has_key(doc, page.xref, "BleedBox") else page.mediabox
    margins_pt = {
        "left": trim.x0 - outer.x0,
        "top": trim.y0 - outer.y0,
        "right": outer.x1 - trim.x1,
        "bottom": outer.y1 - trim.y1,
    }
    min_mm = min(margins_pt.values()) / PT_PER_MM
    # PDF writers round box coordinates (3 mm often comes back as 2.998 mm),
    # so allow a tolerance far below anything a guillotine could cut.
    if min_mm + BLEED_TOLERANCE_MM < profile.bleed_mm:
        return [Issue(Severity.ERROR, "bleed", pno,
                      f"Bleed is {min_mm:.1f} mm; press needs {profile.bleed_mm:.1f} mm.",
                      {k: round(v / PT_PER_MM, 2) for k, v in margins_pt.items()})]
    return []


def check_images(doc: pymupdf.Document, page: pymupdf.Page, profile: Profile) -> list[Issue]:
    pno = page.number + 1
    issues: list[Issue] = []
    for info in page.get_image_info(xrefs=True):
        a, b, c, d, _, _ = info["transform"]
        # Placed size in points, from the image's transform (handles scaling and rotation).
        w_pt, h_pt = math.hypot(a, b), math.hypot(c, d)
        if w_pt < 1 or h_pt < 1:
            continue
        dpi = min(info["width"] / (w_pt / 72), info["height"] / (h_pt / 72))
        detail = {"xref": info["xref"], "pixels": [info["width"], info["height"]],
                  "placed_mm": [round(w_pt / PT_PER_MM, 1), round(h_pt / PT_PER_MM, 1)],
                  "effective_dpi": round(dpi)}

        if dpi < profile.min_dpi_error:
            issues.append(Issue(Severity.ERROR, "image-resolution", pno,
                                f"Image at {dpi:.0f} dpi effective (minimum {profile.min_dpi_error:.0f}).", detail))
        elif dpi < profile.min_dpi_warn:
            issues.append(Issue(Severity.WARN, "image-resolution", pno,
                                f"Image at {dpi:.0f} dpi effective (recommended {profile.min_dpi_warn:.0f}).", detail))

        if info["colorspace"] == 3:
            issues.append(Issue(profile.rgb_images, "image-colorspace", pno,
                                "RGB image: it will be converted to CMYK at print time and colors may shift.",
                                {**detail, "colorspace": info.get("cs-name", "RGB")}))
    return issues


def check_fonts(doc: pymupdf.Document, page: pymupdf.Page, seen: set[int]) -> list[Issue]:
    pno = page.number + 1
    issues = []
    for xref, ext, ftype, basefont, *_ in doc.get_page_fonts(page.number):
        if xref in seen or ftype == "Type3":   # Type3 glyphs are drawn in the PDF itself
            continue
        seen.add(xref)
        if ext == "n/a":
            issues.append(Issue(Severity.ERROR, "fonts", pno,
                                f"Font '{basefont}' is not embedded; the press will substitute another font.",
                                {"font": basefont, "type": ftype}))
    return issues


def check_ink(page: pymupdf.Page, profile: Profile) -> tuple[list[Issue], PageInk]:
    pno = page.number + 1
    pix = page.get_pixmap(dpi=profile.raster_dpi, colorspace=pymupdf.csCMYK, alpha=False)
    cmyk = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, 4)
    stats, tac_map = ink.tac_analyze(cmyk, profile.tac_limit_pct)

    page_ink = PageInk(pno, stats["max_pct"], stats["mean_pct"], stats["over_fraction"], tac_map, cmyk)
    issues = []
    if stats["over_pixels"]:
        frac = stats["over_fraction"]
        sev = Severity.ERROR if frac > profile.tac_error_fraction else Severity.WARN
        issues.append(Issue(sev, "ink-coverage", pno,
                            f"Ink coverage reaches {stats['max_pct']:.0f}% (limit {profile.tac_limit_pct:.0f}%) "
                            f"on {frac:.1%} of the page.",
                            {"max_pct": round(stats["max_pct"], 1), "over_fraction": round(frac, 4)}))
    return issues, page_ink


# ------------------------------------------------------------------ driver

def preflight(path: str | Path, profile: Profile | None = None) -> Report:
    profile = profile or Profile()
    path = Path(path)
    with pymupdf.open(path) as doc:
        report = Report(file=path.name, pages=doc.page_count, profile=profile, backend=ink.BACKEND)
        seen_fonts: set[int] = set()
        for page in doc:
            report.issues += check_bleed(doc, page, profile)
            report.issues += check_images(doc, page, profile)
            report.issues += check_fonts(doc, page, seen_fonts)
            ink_issues, page_ink = check_ink(page, profile)
            report.issues += ink_issues
            report.ink.append(page_ink)
    order = {Severity.ERROR: 0, Severity.WARN: 1, Severity.INFO: 2}
    report.issues.sort(key=lambda i: (order[i.severity], i.page or 0, i.check))
    return report
