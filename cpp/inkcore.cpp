// inkcore: the pixel-level work of the preflight engine, in C++.
//
//   tac_analyze     Total Area Coverage (TAC) of a CMYK raster: per-pixel ink sum
//                   in percent (0-400) plus summary stats against a press limit.
//   halftone_fs     Floyd-Steinberg error diffusion (serpentine scan), the classic
//                   way a RIP turns continuous-tone channels into 1-bit dots.
//
// Both functions take NumPy arrays without copying and release the GIL while
// they run, so Python threads can preflight several pages in parallel.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include <algorithm>
#include <cstdint>
#include <stdexcept>
#include <vector>

namespace py = pybind11;

using u8_array = py::array_t<std::uint8_t, py::array::c_style | py::array::forcecast>;

namespace {

struct TacStats {
    double max_pct = 0.0;
    double mean_pct = 0.0;
    std::int64_t over_pixels = 0;
    std::int64_t total_pixels = 0;
};

// Ink coverage of one pixel in percent: (C + M + Y + K) / 255 * 100.
inline float pixel_tac(const std::uint8_t* px) {
    const int sum = px[0] + px[1] + px[2] + px[3];
    return static_cast<float>(sum) * (100.0f / 255.0f);
}

}  // namespace

// Returns (stats dict, float32 TAC map of shape (H, W)).
py::tuple tac_analyze(u8_array cmyk, double limit_pct) {
    if (cmyk.ndim() != 3 || cmyk.shape(2) != 4) {
        throw std::invalid_argument("tac_analyze expects a (H, W, 4) uint8 CMYK array");
    }
    const auto h = cmyk.shape(0);
    const auto w = cmyk.shape(1);

    py::array_t<float> tac_map({h, w});
    const std::uint8_t* src = cmyk.data();
    float* dst = tac_map.mutable_data();

    TacStats s;
    s.total_pixels = static_cast<std::int64_t>(h) * w;
    double sum = 0.0;
    float max_v = 0.0f;
    std::int64_t over = 0;
    const float limit = static_cast<float>(limit_pct);

    {
        py::gil_scoped_release release;
        for (std::int64_t i = 0; i < s.total_pixels; ++i) {
            const float t = pixel_tac(src + 4 * i);
            dst[i] = t;
            sum += t;
            max_v = std::max(max_v, t);
            over += (t > limit) ? 1 : 0;
        }
    }

    s.max_pct = max_v;
    s.mean_pct = s.total_pixels ? sum / static_cast<double>(s.total_pixels) : 0.0;
    s.over_pixels = over;

    py::dict stats;
    stats["max_pct"] = s.max_pct;
    stats["mean_pct"] = s.mean_pct;
    stats["over_pixels"] = s.over_pixels;
    stats["total_pixels"] = s.total_pixels;
    stats["over_fraction"] =
        s.total_pixels ? static_cast<double>(s.over_pixels) / s.total_pixels : 0.0;
    return py::make_tuple(stats, tac_map);
}

// Floyd-Steinberg error diffusion on every channel of an (H, W) or (H, W, C)
// uint8 array. Output has the same shape with values 0 or 255.
// Serpentine scanning (alternate row direction) avoids the diagonal "worm"
// artifacts of a plain left-to-right scan.
py::array_t<std::uint8_t> halftone_fs(u8_array img) {
    if (img.ndim() != 2 && img.ndim() != 3) {
        throw std::invalid_argument("halftone_fs expects a (H, W) or (H, W, C) uint8 array");
    }
    const auto h = img.shape(0);
    const auto w = img.shape(1);
    const auto c = img.ndim() == 3 ? img.shape(2) : 1;

    std::vector<py::ssize_t> shape(img.shape(), img.shape() + img.ndim());
    py::array_t<std::uint8_t> out(shape);
    const std::uint8_t* src = img.data();
    std::uint8_t* dst = out.mutable_data();

    {
        py::gil_scoped_release release;
        // Two rows of accumulated error per channel: current and next.
        std::vector<float> cur(static_cast<std::size_t>(w) + 2), nxt(static_cast<std::size_t>(w) + 2);

        for (py::ssize_t ch = 0; ch < c; ++ch) {
            std::fill(cur.begin(), cur.end(), 0.0f);
            for (py::ssize_t y = 0; y < h; ++y) {
                std::fill(nxt.begin(), nxt.end(), 0.0f);
                const bool ltr = (y % 2 == 0);
                const int dir = ltr ? 1 : -1;
                for (py::ssize_t i = 0; i < w; ++i) {
                    const py::ssize_t x = ltr ? i : (w - 1 - i);
                    const std::size_t idx = (static_cast<std::size_t>(y) * w + x) * c + ch;
                    const std::size_t e = static_cast<std::size_t>(x) + 1;  // +1 pad

                    const float v = static_cast<float>(src[idx]) + cur[e];
                    const float q = v >= 128.0f ? 255.0f : 0.0f;
                    dst[idx] = static_cast<std::uint8_t>(q);
                    const float err = v - q;

                    cur[e + dir] += err * (7.0f / 16.0f);
                    nxt[e - dir] += err * (3.0f / 16.0f);
                    nxt[e]       += err * (5.0f / 16.0f);
                    nxt[e + dir] += err * (1.0f / 16.0f);
                }
                std::swap(cur, nxt);
            }
        }
    }
    return out;
}

PYBIND11_MODULE(_inkcore, m) {
    m.doc() = "C++ pixel kernels for PressReady (TAC analysis, error-diffusion halftoning)";
    m.def("tac_analyze", &tac_analyze, py::arg("cmyk"), py::arg("limit_pct") = 300.0,
          "Total Area Coverage of a (H, W, 4) uint8 CMYK raster. Returns (stats, tac_map).");
    m.def("halftone_fs", &halftone_fs, py::arg("img"),
          "Floyd-Steinberg error diffusion (serpentine). Returns 0/255 array of same shape.");
}
