"""Aggregate metrics over result rows (shared by scripts/score.py and scripts/report.py)."""
from __future__ import annotations

import json
import statistics
from pathlib import Path

from .scoring import FIELDS, DocScore, score_document

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "data" / "golden"


def load_rows(path: Path) -> list[dict]:
    """A result file is a pretty-printed JSON array (current) or JSON Lines (legacy)."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return json.loads(text)
    return [json.loads(l) for l in text.splitlines() if l.strip()]


def golden_for(doc_id: str) -> dict | None:
    p = GOLD / f"{doc_id}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def percentile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    return s[min(len(s) - 1, max(0, round(q * (len(s) - 1))))]


def row_status(r: dict) -> str:
    """ok | repaired | failed | error. Result files written before the repair step have no `status`."""
    if r.get("status"):
        return r["status"]
    if r.get("error"):
        return "error"
    return "ok" if r.get("valid") else "failed"


def doc_scores(rows: list[dict]) -> dict[str, DocScore]:
    out = {}
    for r in rows:
        g = golden_for(r["doc_id"])
        if g is not None:
            out[r["doc_id"]] = score_document(r["doc_id"], g, r["parsed"] if r["valid"] else None)
    return out


def run_metrics(rows: list[dict]) -> dict:
    scored = doc_scores(rows)
    per_field = {f: [] for f in FIELDS}
    for ds in scored.values():
        for fr in ds.fields:
            per_field[fr.field].append(fr.match)
    lat = [r["latency_ms"] for r in rows]
    costs = [r["cost_usd"] for r in rows if r.get("cost_usd") is not None]
    in_tok = [r["input_tokens"] for r in rows if r.get("input_tokens") is not None]
    out_tok = [r["output_tokens"] for r in rows if r.get("output_tokens") is not None]
    first = rows[0]
    n_gold = len(scored)
    return {
        "config": first["config"], "provider": first["provider"], "model": first["model"],
        "prompt": str(first["prompt_version"]),
        "params": {k: v for k, v in first["params"].items() if k in ("effort", "temperature", "top_p", "constrained")},
        "prompt_sha256": first.get("prompt_sha256"),
        "n": len(rows), "n_golden": n_gold,
        "accuracy": (sum(d.matched for d in scored.values()) / (8 * n_gold)) if n_gold else float("nan"),
        "doc_exact": (sum(d.matched == 8 for d in scored.values()) / n_gold) if n_gold else float("nan"),
        "valid": sum(r["valid"] for r in rows) / len(rows),          # ok + repaired
        "n_ok": sum(row_status(r) == "ok" for r in rows),
        "n_repaired": sum(row_status(r) == "repaired" for r in rows),
        "n_failed": sum(row_status(r) == "failed" for r in rows),
        "n_invalid": sum(row_status(r) == "failed" for r in rows),    # legacy name
        "n_first_invalid": sum(row_status(r) in ("repaired", "failed") for r in rows),
        "n_error": sum(row_status(r) == "error" for r in rows),
        "retries": sum(r.get("transport_retries", max(0, r.get("attempts", 1) - 1)) for r in rows),
        "p50": percentile(lat, 0.5), "p95": percentile(lat, 0.95), "mean_ms": statistics.mean(lat),
        "cost_per_1000": (statistics.mean(costs) * 1000) if costs else 0.0,
        "avg_in": statistics.mean(in_tok) if in_tok else None, "avg_out": statistics.mean(out_tok) if out_tok else None,
        "per_field": {f: (sum(v) / len(v) if v else float("nan")) for f, v in per_field.items()},
        "scores": scored,
    }
