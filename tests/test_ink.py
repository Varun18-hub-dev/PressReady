"""The C++ kernels must agree with the reference implementations."""

import numpy as np
import pytest

from pressready import ink

needs_cpp = pytest.mark.skipif(ink.BACKEND != "c++", reason="C++ extension not built")
rng = np.random.default_rng(7)


@needs_cpp
def test_tac_matches_reference():
    cmyk = rng.integers(0, 256, size=(97, 131, 4), dtype=np.uint8)
    stats, tac = ink.tac_analyze(cmyk, 250)
    ref_stats, ref_tac = ink.tac_analyze_ref(cmyk, 250)
    np.testing.assert_allclose(tac, ref_tac, rtol=1e-6)
    assert stats["over_pixels"] == ref_stats["over_pixels"]
    assert stats["max_pct"] == pytest.approx(ref_stats["max_pct"])
    assert stats["mean_pct"] == pytest.approx(ref_stats["mean_pct"], rel=1e-6)


def test_tac_known_values():
    cmyk = np.zeros((2, 2, 4), np.uint8)
    cmyk[0, 0] = 255                      # 400 %: registration-style rich black
    cmyk[0, 1] = (255, 0, 0, 0)          # 100 %
    stats, tac = ink.tac_analyze(cmyk, 300)
    assert tac[0, 0] == pytest.approx(400)
    assert tac[0, 1] == pytest.approx(100)
    assert stats["over_pixels"] == 1
    assert stats["over_fraction"] == pytest.approx(0.25)


def test_tac_rejects_wrong_shape():
    with pytest.raises((ValueError, Exception)):
        ink.tac_analyze(np.zeros((4, 4, 3), np.uint8))


@needs_cpp
@pytest.mark.parametrize("shape", [(40, 53), (31, 29, 4)])
def test_halftone_matches_reference(shape):
    img = rng.integers(0, 256, size=shape, dtype=np.uint8)
    np.testing.assert_array_equal(ink.halftone_fs(img), ink.halftone_fs_ref(img))


@pytest.mark.parametrize("level", [0, 32, 128, 200, 255])
def test_halftone_preserves_tone(level):
    """Error diffusion should keep average density: a 50% grey prints ~50% dots."""
    out = ink.halftone_fs(np.full((128, 128), level, np.uint8))
    assert set(np.unique(out)) <= {0, 255}
    assert out.mean() == pytest.approx(level, abs=2.0)
