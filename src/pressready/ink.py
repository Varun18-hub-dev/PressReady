"""Pixel kernels: C++ when the extension is built, NumPy/Python reference otherwise.

The reference implementations exist for two reasons: the tests check that the
C++ code gives the same answers, and the benchmark measures how much faster it is.
"""

from __future__ import annotations

import numpy as np

try:
    from . import _inkcore  # type: ignore[attr-defined]

    BACKEND = "c++"
except ImportError:  # pragma: no cover - exercised only without a compiler
    _inkcore = None
    BACKEND = "numpy"


# ---------------------------------------------------------------- reference

def tac_analyze_ref(cmyk: np.ndarray, limit_pct: float = 300.0):
    if cmyk.ndim != 3 or cmyk.shape[2] != 4:
        raise ValueError("expected a (H, W, 4) uint8 CMYK array")
    tac = cmyk.astype(np.float32).sum(axis=2) * np.float32(100.0 / 255.0)
    over = int((tac > limit_pct).sum())
    total = int(tac.size)
    stats = {
        "max_pct": float(tac.max()) if total else 0.0,
        "mean_pct": float(tac.mean()) if total else 0.0,
        "over_pixels": over,
        "total_pixels": total,
        "over_fraction": over / total if total else 0.0,
    }
    return stats, tac


def halftone_fs_ref(img: np.ndarray) -> np.ndarray:
    """Pure-Python Floyd-Steinberg, serpentine; mirrors cpp/inkcore.cpp exactly."""
    squeeze = img.ndim == 2
    src = img[..., None] if squeeze else img
    h, w, c = src.shape
    out = np.empty_like(src)
    for ch in range(c):
        cur = [0.0] * (w + 2)
        for y in range(h):
            nxt = [0.0] * (w + 2)
            ltr = y % 2 == 0
            d = 1 if ltr else -1
            for i in range(w):
                x = i if ltr else w - 1 - i
                e = x + 1
                v = float(src[y, x, ch]) + cur[e]
                q = 255.0 if v >= 128.0 else 0.0
                out[y, x, ch] = int(q)
                err = v - q
                cur[e + d] += err * 7 / 16
                nxt[e - d] += err * 3 / 16
                nxt[e] += err * 5 / 16
                nxt[e + d] += err * 1 / 16
            cur = nxt
    return out[..., 0] if squeeze else out


# ------------------------------------------------------------------ public

def tac_analyze(cmyk: np.ndarray, limit_pct: float = 300.0):
    """Return (stats, tac_map) for a (H, W, 4) uint8 CMYK raster."""
    if _inkcore is not None:
        return _inkcore.tac_analyze(np.ascontiguousarray(cmyk, dtype=np.uint8), float(limit_pct))
    return tac_analyze_ref(cmyk, limit_pct)


def halftone_fs(img: np.ndarray) -> np.ndarray:
    """Floyd-Steinberg error diffusion on each channel; returns 0/255 uint8."""
    if _inkcore is not None:
        return _inkcore.halftone_fs(np.ascontiguousarray(img, dtype=np.uint8))
    return halftone_fs_ref(img)
