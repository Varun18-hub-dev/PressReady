"""Time the C++ kernels against the NumPy / pure-Python references.

    python benchmarks/bench_ink.py
"""

import time

import numpy as np

from pressready import ink


def best_of(fn, *args, runs=5):
    best = float("inf")
    for _ in range(runs):
        t = time.perf_counter()
        fn(*args)
        best = min(best, time.perf_counter() - t)
    return best


def main():
    rng = np.random.default_rng(0)
    # A4 at 150 dpi: 1240 x 1754 CMYK pixels
    page = rng.integers(0, 256, size=(1754, 1240, 4), dtype=np.uint8)
    tile = page[:256, :256]

    print(f"backend: {ink.BACKEND}")
    t_cpp = best_of(ink.tac_analyze, page, 300)
    t_np = best_of(ink.tac_analyze_ref, page, 300)
    print(f"TAC, A4 @150 dpi    C++ {t_cpp * 1e3:7.1f} ms   NumPy  {t_np * 1e3:7.1f} ms   x{t_np / t_cpp:.1f}")

    t_cpp = best_of(ink.halftone_fs, page)
    print(f"Halftone, A4 @150   C++ {t_cpp * 1e3:7.1f} ms   (4 separations)")
    t_cpp = best_of(ink.halftone_fs, tile)
    t_py = best_of(ink.halftone_fs_ref, tile, runs=1)
    print(f"Halftone, 256x256   C++ {t_cpp * 1e3:7.1f} ms   Python {t_py * 1e3:7.0f} ms   x{t_py / t_cpp:.0f}")


if __name__ == "__main__":
    main()
