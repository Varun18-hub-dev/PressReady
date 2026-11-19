import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pressready.web import app  # noqa: E402

client = TestClient(app)


def test_index_and_health():
    assert "PressReady" in client.get("/").text
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["engine"] in ("c++", "numpy")


def test_upload_bad_job(bad_pdf):
    with open(bad_pdf, "rb") as f:
        r = client.post("/api/preflight", files={"file": ("bad.pdf", f, "application/pdf")})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "FAIL" and data["file"] == "bad.pdf"
    assert len(data["previews"]) == data["pages"] == 2
    assert data["previews"][0]["ink_png"].startswith("data:image/png;base64,")


def test_settings_change_the_verdict():
    strict = client.post("/api/sample/bad_job").json()
    lenient = client.post("/api/sample/bad_job", data={"tac_limit": 400, "bleed_mm": 0.5,
                                                       "min_dpi": 30, "error_dpi": 30}).json()
    assert any(i["check"] == "ink-coverage" for i in strict["issues"])
    assert not any(i["check"] in ("ink-coverage", "image-resolution") for i in lenient["issues"])


def test_good_sample_passes():
    assert client.post("/api/sample/good_job").json()["status"] == "PASS"


def test_rejects_non_pdf_and_bad_settings():
    r = client.post("/api/preflight", files={"file": ("x.pdf", b"hello", "application/pdf")})
    assert r.status_code == 400
    assert client.post("/api/sample/good_job", data={"tac_limit": 900}).status_code == 422
    assert client.post("/api/sample/nope").status_code == 404
