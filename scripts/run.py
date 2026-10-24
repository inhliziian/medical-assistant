"""CLI: run documents through configurations.  See medassist.runner.run().

  uv run python scripts/run.py --configs haiku_low,qwen_t0 --prompt v1 --docs golden
  uv run python scripts/run.py --configs haiku_low --prompt v1 --docs all --tag full
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from medassist.runner import run  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", required=True, help="comma-separated names from config/runs.toml")
    ap.add_argument("--prompt", default="v1")
    ap.add_argument("--docs", default="golden", help="all | golden | comma-separated ids")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    run([c.strip() for c in args.configs.split(",")], args.prompt, args.docs, args.tag)


if __name__ == "__main__":
    main()
