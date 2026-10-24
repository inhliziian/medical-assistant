"""CLI: build the HTML report and REPORT.md from result files.

  uv run python scripts/report.py                       # results/*_full.jsonl -> results/report-checkpoint-1.html + REPORT.md
  uv run python scripts/report.py --files results/a.jsonl results/b.jsonl --out results/x.html
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from medassist.report_html import build_html  # noqa: E402
from medassist.report_md import build_markdown  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", nargs="*", help="result files; default: results/*_full.jsonl")
    ap.add_argument("--out", default=str(ROOT / "results" / "report-checkpoint-1.html"))
    ap.add_argument("--md", default=str(ROOT / "REPORT.md"))
    ap.add_argument("--title", default="Extraction Baseline Report")
    args = ap.parse_args()
    files = [Path(f) for f in args.files] if args.files else sorted((ROOT / "results").glob("*_full.jsonl"))
    if not files:
        raise SystemExit("no result files; run main.py first")
    html_out = build_html(files, Path(args.out), args.title)
    md_out = build_markdown(files, Path(args.md))
    print(f"wrote {html_out.relative_to(ROOT)} and {md_out.relative_to(ROOT)} from {len(files)} result files")


if __name__ == "__main__":
    main()
