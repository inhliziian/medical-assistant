"""Run documents through configurations and write one pretty-printed JSON array per run.

Each record holds the parsed output, validity, status (ok | repaired | failed | error), latency, tokens, cost,
the model, prompt version + hash and the sampling parameters. The model's raw text is not stored (the parsed
JSON is the deliverable); validation errors are kept for error analysis."""
from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from .config import build_provider, get
from .prompts import Prompt

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
GOLD = ROOT / "data" / "golden"
RESULTS = ROOT / "results"


def select_docs(spec: str) -> list[str]:
    all_ids = sorted(p.stem for p in RAW.glob("*.txt"))
    golden = {p.stem for p in GOLD.glob("*.json")}
    if spec == "all":
        return all_ids
    if spec == "golden":
        return [d for d in all_ids if d in golden]
    return [d.strip() for d in spec.split(",") if d.strip()]


def run(configs: list[str], prompt_name: str, docs_spec: str = "all", tag: str = "", quiet: bool = False,
        unconstrained: bool = False) -> list[Path]:
    """Returns the result files written (one per config). `unconstrained` drops the schema from the API
    request (free-form JSON) so validation failures and the one-shot repair happen for real."""
    RESULTS.mkdir(exist_ok=True)
    prompt = Prompt.load(prompt_name)
    docs = select_docs(docs_spec)
    golden_ids = {p.stem for p in GOLD.glob("*.json")}
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    written: list[Path] = []
    for cname in configs:
        provider, cfg = get(cname)
        if unconstrained:
            cfg = replace(cfg, params={**cfg.params, "constrained": False})
            provider = build_provider(cfg)
        out = RESULTS / f"{stamp}_{cname}_{prompt_name}{('_' + tag) if tag else ''}.json"
        print(f"== {cname} ({cfg.model}) | prompt {prompt.version} | {len(docs)} docs -> {out.relative_to(ROOT)}", flush=True)
        t_batch = time.perf_counter()
        n_valid = 0
        rows: list[dict] = []
        for i, doc in enumerate(docs, 1):
                text = (RAW / f"{doc}.txt").read_text(encoding="utf-8")
                res = provider.extract(prompt.instructions, text)
                row = res.to_dict()
                row.pop("raw_text", None)
                row = {"doc_id": doc, "golden": doc in golden_ids, "prompt_version": prompt.version,
                       "prompt_name": prompt.name, "prompt_sha256": prompt.sha256, **row, "cost_usd": res.cost_usd,
                       "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                rows.append(row)
                out.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                n_valid += res.valid
                if not quiet:
                    status = {"ok": "ok  ", "repaired": "REP ", "failed": "FAIL", "error": "ERR "}[res.status]
                    note = res.error or (res.validation_errors[0] if res.validation_errors else "")
                    print(f"  [{i:2d}/{len(docs)}] {doc} {status} {res.latency_ms:7.0f} ms"
                          + (f"  {note[:70]}" if note else ""),
                          file=sys.stderr, flush=True)
        n_rep = sum(r["status"] == "repaired" for r in rows)
        n_fail = sum(r["status"] == "failed" for r in rows)
        print(f"   done: {n_valid}/{len(docs)} valid ({n_rep} repaired, {n_fail} failed) in {time.perf_counter() - t_batch:.0f} s", flush=True)
        written.append(out)
    return written
