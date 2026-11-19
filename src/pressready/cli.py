"""Command line: `pressready job.pdf --html report.html`.

Exit codes follow hot-folder conventions so a print workflow can route jobs:
0 = pass, 1 = warnings (operator review), 2 = errors (hold the job), 3 = could not read file.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import report as render
from .checks import Profile, Severity, preflight

_COLORS = {Severity.ERROR: "\033[31m", Severity.WARN: "\033[33m", Severity.INFO: "\033[36m"}


def build_parser() -> argparse.ArgumentParser:
    d = Profile()
    p = argparse.ArgumentParser(prog="pressready", description="Preflight a PDF for print.")
    p.add_argument("pdf", type=Path)
    p.add_argument("--json", type=Path, help="write the report as JSON")
    p.add_argument("--html", type=Path, help="write a visual HTML report")
    p.add_argument("--bleed-mm", type=float, default=d.bleed_mm)
    p.add_argument("--min-dpi", type=float, default=d.min_dpi_warn, help="recommended image resolution")
    p.add_argument("--error-dpi", type=float, default=d.min_dpi_error, help="hard minimum image resolution")
    p.add_argument("--tac-limit", type=float, default=d.tac_limit_pct, help="max total ink, percent")
    p.add_argument("--raster-dpi", type=int, default=d.raster_dpi, help="resolution for ink analysis")
    p.add_argument("--no-color", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    profile = Profile(bleed_mm=args.bleed_mm, min_dpi_warn=args.min_dpi, min_dpi_error=args.error_dpi,
                      tac_limit_pct=args.tac_limit, raster_dpi=args.raster_dpi)
    try:
        rep = preflight(args.pdf, profile)
    except Exception as exc:  # unreadable or not a PDF
        print(f"pressready: cannot read {args.pdf}: {exc}", file=sys.stderr)
        return 3

    color = sys.stdout.isatty() and not args.no_color
    for issue in rep.issues:
        tag = issue.severity.value.upper().ljust(5)
        if color:
            tag = f"{_COLORS[issue.severity]}{tag}\033[0m"
        where = f"p{issue.page}" if issue.page else "doc"
        print(f"{tag} {where:<4} {issue.check:<17} {issue.message}")
    print(f"{rep.status}: {rep.file} — {len(rep.errors)} error(s), {len(rep.warnings)} warning(s) "
          f"[{rep.pages} page(s), engine {rep.backend}]")

    if args.json:
        args.json.write_text(render.to_json(rep), encoding="utf-8")
    if args.html:
        args.html.write_text(render.to_html(rep), encoding="utf-8")
    return {"PASS": 0, "WARN": 1, "FAIL": 2}[rep.status]


if __name__ == "__main__":
    sys.exit(main())
