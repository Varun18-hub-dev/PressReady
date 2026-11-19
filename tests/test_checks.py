import json

from pressready import Profile, preflight
from pressready.checks import Severity
from pressready.cli import main
from pressready.report import to_html, to_json


def _found(report, check, page, severity):
    return any(i.check == check and i.page == page and i.severity == severity for i in report.issues)


def test_good_job_passes(good_pdf):
    rep = preflight(good_pdf)
    assert rep.status == "PASS", [i.message for i in rep.issues]
    assert rep.ink[0].max_pct < 300


def test_bad_job_catches_every_problem(bad_pdf):
    rep = preflight(bad_pdf)
    assert rep.status == "FAIL"
    assert _found(rep, "fonts", 1, Severity.ERROR)              # Helvetica not embedded
    assert _found(rep, "image-resolution", 1, Severity.ERROR)   # 38 dpi
    assert _found(rep, "image-resolution", 1, Severity.WARN)    # 169 dpi
    assert _found(rep, "image-colorspace", 1, Severity.WARN)    # RGB
    assert _found(rep, "ink-coverage", 1, Severity.ERROR)       # 400% block
    assert _found(rep, "bleed", 1, Severity.WARN)               # no TrimBox
    assert _found(rep, "bleed", 2, Severity.ERROR)              # only 1 mm


def test_effective_dpi_is_measured_from_placement(bad_pdf):
    rep = preflight(bad_pdf)
    dpis = sorted(i.detail["effective_dpi"] for i in rep.issues if i.check == "image-resolution")
    # 120 px over 80 mm and 200 px over 30 mm
    assert dpis == [38, 169]


def test_profile_thresholds_are_respected(bad_pdf):
    lenient = Profile(tac_limit_pct=400, bleed_mm=1.0, min_dpi_error=30, min_dpi_warn=30)
    rep = preflight(bad_pdf, lenient)
    checks = {i.check for i in rep.issues}
    assert "ink-coverage" not in checks
    assert "image-resolution" not in checks
    assert not _found(rep, "bleed", 2, Severity.ERROR)


def test_reports_render(bad_pdf):
    rep = preflight(bad_pdf)
    data = json.loads(to_json(rep))
    assert data["status"] == "FAIL" and data["summary"]["errors"] == len(rep.errors)
    page = to_html(rep)
    assert page.startswith("<!DOCTYPE html>") and page.count("data:image/png") == 3 * rep.pages


def test_cli_exit_codes(good_pdf, bad_pdf, tmp_path):
    assert main([str(good_pdf), "--no-color"]) == 0
    assert main([str(bad_pdf), "--no-color", "--html", str(tmp_path / "r.html")]) == 2
    assert (tmp_path / "r.html").exists()
    not_pdf = tmp_path / "x.pdf"
    not_pdf.write_text("not a pdf")
    assert main([str(not_pdf)]) == 3
