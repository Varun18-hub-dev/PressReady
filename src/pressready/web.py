"""Web UI: drop a PDF in the browser, get the preflight report.

    pip install .[web]
    pressready-web                 # http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import tempfile
import time
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from . import __version__, ink, samples
from .checks import Profile, Report, preflight
from .report import _png, cmyk_to_rgb, screened_preview, tac_heatmap

MAX_UPLOAD_MB = 50
STATIC = Path(__file__).parent / "static"

app = FastAPI(title="PressReady", version=__version__)


def _profile(tac_limit: float, bleed_mm: float, min_dpi: float, error_dpi: float) -> Profile:
    if not (100 <= tac_limit <= 400 and 0 <= bleed_mm <= 20 and 0 < error_dpi <= min_dpi <= 2400):
        raise HTTPException(422, "Settings out of range.")
    return Profile(tac_limit_pct=tac_limit, bleed_mm=bleed_mm, min_dpi_warn=min_dpi, min_dpi_error=error_dpi)


def _payload(report: Report, seconds: float) -> dict:
    data = report.to_dict()
    limit = report.profile.tac_limit_pct
    data["elapsed_ms"] = round(seconds * 1000)
    data["previews"] = [
        {
            "page": p.page,
            "page_png": _png(cmyk_to_rgb(p.cmyk)),
            "ink_png": _png(tac_heatmap(p.tac_map, limit)),
            "screen_png": _png(screened_preview(p.cmyk)),
        }
        for p in report.ink
    ]
    return data


def _run(path: Path, name: str, profile: Profile) -> dict:
    start = time.perf_counter()
    try:
        report = preflight(path, profile)
    except Exception as exc:
        raise HTTPException(400, f"Could not read this file as a PDF ({exc}).") from exc
    report.file = name
    return _payload(report, time.perf_counter() - start)


@lru_cache(maxsize=1)
def _sample_dir() -> Path:
    out = Path(tempfile.mkdtemp(prefix="pressready-samples-"))
    samples.make_good(out / "good_job.pdf")
    samples.make_bad(out / "bad_job.pdf")
    return out


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "engine": ink.BACKEND}


@app.post("/api/preflight")
def preflight_upload(
    file: UploadFile = File(...),
    tac_limit: float = Form(300),
    bleed_mm: float = Form(3),
    min_dpi: float = Form(300),
    error_dpi: float = Form(150),
) -> dict:
    profile = _profile(tac_limit, bleed_mm, min_dpi, error_dpi)
    data = file.file.read(MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"File is larger than {MAX_UPLOAD_MB} MB.")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "That file is not a PDF.")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "upload.pdf"
        path.write_bytes(data)
        return _run(path, file.filename or "upload.pdf", profile)


@app.post("/api/sample/{name}")
def preflight_sample(
    name: str,
    tac_limit: float = Form(300),
    bleed_mm: float = Form(3),
    min_dpi: float = Form(300),
    error_dpi: float = Form(150),
) -> dict:
    if name not in ("good_job", "bad_job"):
        raise HTTPException(404, "Unknown sample.")
    profile = _profile(tac_limit, bleed_mm, min_dpi, error_dpi)
    return _run(_sample_dir() / f"{name}.pdf", f"{name}.pdf", profile)


def main() -> None:
    parser = argparse.ArgumentParser(prog="pressready-web", description="Run the PressReady web UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    import uvicorn

    print(f"PressReady {__version__} · engine {ink.BACKEND} · http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
