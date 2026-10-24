#!/usr/bin/env python3
"""One-command entry point: run every configuration × prompt version × document, then build the reports.

  python main.py                 # prompt v1, all configs, all documents (≈15 min, mostly the local model) -> REPORT.md + results/report-checkpoint-1.html
  python main.py --quick         # golden documents only (≈5 min)
  python main.py --prompts v1,v2 # also run prompt v2
  python main.py --skip-run      # rebuild the reports from existing results/*_full.json
  python main.py --configs haiku_low,qwen_t0 --prompts v1 --docs 004,034
Requires: .env with ANTHROPIC_API_KEY, Ollama running with the model named in config/runs.toml.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from medassist.config import load_configs  # noqa: E402  (loads .env)


def preflight(configs: list[str]) -> None:
    cfgs = load_configs()
    kinds = {cfgs[c].kind for c in configs}
    problems = []
    if "anthropic" in kinds and not os.environ.get("ANTHROPIC_API_KEY"):
        problems.append("ANTHROPIC_API_KEY is not set: copy .env.example to .env and add your key")
    if "ollama" in kinds:
        import httpx
        base = next(cfgs[c].base_url for c in configs if cfgs[c].kind == "ollama") or "http://localhost:11434"
        model = next(cfgs[c].model for c in configs if cfgs[c].kind == "ollama")
        try:
            tags = httpx.get(f"{base}/api/tags", timeout=5).json().get("models", [])
            names = {t.get("name") for t in tags} | {t.get("model") for t in tags}
            if model not in names and f"{model}:latest" not in names:
                problems.append(f"Ollama is running but model {model!r} is not pulled: ollama pull {model}")
        except Exception as e:
            problems.append(f"Ollama not reachable at {base} ({type(e).__name__}): start it with `ollama serve`")
    if problems:
        print("Preflight failed:\n  - " + "\n  - ".join(problems), file=sys.stderr)
        sys.exit(2)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--configs", help="comma-separated; default: every config in config/runs.toml")
    ap.add_argument("--prompts", default="v1", help="comma-separated prompt versions, e.g. v1,v2 (default: v1)")
    ap.add_argument("--docs", default="all", help="all | golden | comma-separated ids")
    ap.add_argument("--quick", action="store_true", help="golden documents only")
    ap.add_argument("--skip-run", action="store_true", help="only rebuild reports from results/*_full.json")
    ap.add_argument("--quiet", action="store_true", help="no per-document progress lines")
    args = ap.parse_args()

    from medassist.report_html import build_html
    from medassist.report_md import build_markdown

    results_dir = ROOT / "results"
    if args.skip_run:
        files = sorted(results_dir.glob("*_full.json"))
        if not files:
            sys.exit("no results/*_full.json to report on")
    else:
        from medassist.runner import run
        configs = [c.strip() for c in args.configs.split(",")] if args.configs else list(load_configs())
        prompts = [p.strip() for p in args.prompts.split(",")]
        docs = "golden" if args.quick else args.docs
        preflight(configs)
        tag = "full" if docs == "all" else ("golden" if docs == "golden" else "subset")
        files = []
        for prompt in prompts:
            files += run(configs, prompt, docs, tag=tag, quiet=args.quiet)

    if args.skip_run or tag == "full":
        html = build_html(files, ROOT / "results" / "report-checkpoint-1.html")
        md = build_markdown(files, ROOT / "REPORT.md")
        print(f"\nReports: {md.relative_to(ROOT)} and {html.relative_to(ROOT)}")
    else:
        # partial runs must not overwrite the main deliverables
        html = build_html(files, ROOT / "results" / "last-partial-run.html", "Partial run")
        print(f"\nPartial run: report written to {html.relative_to(ROOT)}; REPORT.md left unchanged.")
    import subprocess
    print(subprocess.run([sys.executable, str(ROOT / "scripts/score.py"), *map(str, files)], capture_output=True, text=True).stdout)


if __name__ == "__main__":
    main()
