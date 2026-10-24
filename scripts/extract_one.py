"""Run one document through one configuration and print the result.

Usage: uv run python scripts/extract_one.py --config haiku_low --doc 004 [--prompt v1] [--quiet]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from medassist.config import get, load_configs
from medassist.prompts import Prompt

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=False, help="name from config/runs.toml")
    ap.add_argument("--doc", default="004", help="document id in data/raw")
    ap.add_argument("--prompt", default="v1", help="file stem in prompts/extraction")
    ap.add_argument("--list", action="store_true", help="list configs and exit")
    ap.add_argument("--golden", action="store_true", help="compare with data/golden/{doc}.json if it exists")
    ap.add_argument("--quiet", action="store_true", help="skip the full result JSON")
    args = ap.parse_args()

    if args.list or not args.config:
        for name, c in load_configs().items():
            print(f"{name:12s} {c.kind:9s} {c.model:20s} {c.params}")
        return

    provider, cfg = get(args.config)
    prompt = Prompt.load(args.prompt)
    text = (ROOT / "data" / "raw" / f"{args.doc}.txt").read_text(encoding="utf-8")
    res = provider.extract(prompt.instructions, text)
    out = res.to_dict()
    out["prompt_version"] = prompt.version
    out["doc_id"] = args.doc
    if not args.quiet:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\n{args.config} | prompt {prompt.version} | valid={res.valid} | {res.latency_ms:.0f} ms | "
          f"tokens {res.input_tokens}/{res.output_tokens} | cost ${res.cost_usd if res.cost_usd is not None else 0:.5f}"
          + (f" | error: {res.error}" if res.error else "") + (f" | invalid: {res.validation_error}" if res.validation_error else ""))
    if args.golden:
        from medassist.scoring import render_table, score_document
        gpath = ROOT / "data" / "golden" / f"{args.doc}.json"
        if not gpath.exists():
            print(f"(no golden label for {args.doc})")
        else:
            golden = json.loads(gpath.read_text(encoding="utf-8"))
            print()
            print(render_table(score_document(args.doc, golden, res.parsed if res.valid else None)))


if __name__ == "__main__":
    main()
