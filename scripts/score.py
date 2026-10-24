"""Aggregate metrics from results/*.json, or compare two runs document by document.

  uv run python scripts/score.py results/*.json              # metrics table, one row per run file
  uv run python scripts/score.py --fields results/X.json     # add per-field accuracy breakdown
  uv run python scripts/score.py --compare results/A.json results/B.json   # side-by-side on golden docs
Accuracy uses only documents that have a golden label; validity, latency and cost use every document.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from medassist.metrics import GOLD, golden_for, load_rows as load, run_metrics
from medassist.scoring import FIELDS, fmt_value, score_document

ROOT = Path(__file__).resolve().parents[1]


def pct(x: float) -> str:
    return f"{100 * x:5.1f}%"


def p(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    k = min(len(s) - 1, max(0, round(q * (len(s) - 1))))
    return s[k]


def metrics(rows: list[dict]) -> dict:
    m = run_metrics(rows)
    m["params"] = ", ".join(f"{k}={v}" for k, v in m["params"].items())
    return m


def print_table(ms: list[dict]) -> None:
    print(f"{'config':<12} {'model':<17} {'prompt':<6} {'params':<24} {'docs':>4} {'gold':>4} {'field acc':>9} {'doc exact':>9} {'valid':>7} {'p50 ms':>7} {'p95 ms':>7} {'$/1000':>8}")
    for m in ms:
        print(f"{m['config']:<12} {m['model']:<17} {m['prompt']:<6} {m['params']:<24} {m['n']:>4} {m['n_golden']:>4} "
              f"{pct(m['accuracy']):>9} {pct(m['doc_exact']):>9} {pct(m['valid']):>7} {m['p50']:>7.0f} {m['p95']:>7.0f} {m['cost_per_1000']:>8.3f}")


def print_fields(ms: list[dict]) -> None:
    print()
    print(f"{'field':<20}" + "".join(f"{m['config']:>12}" for m in ms))
    for f in FIELDS:
        print(f"{f:<20}" + "".join(f"{pct(m['per_field'][f]):>12}" for m in ms))


def compare(a: list[dict], b: list[dict]) -> None:
    A = {r["doc_id"]: r for r in a}
    B = {r["doc_id"]: r for r in b}
    na, nb = a[0]["config"], b[0]["config"]
    tot_a = tot_b = agree = identical_docs = n_fields = 0
    for doc in sorted(set(A) & set(B)):
        g = golden_for(doc)
        if g is None:
            continue
        ra, rb = A[doc], B[doc]
        da = score_document(doc, g, ra["parsed"] if ra["valid"] else None)
        db = score_document(doc, g, rb["parsed"] if rb["valid"] else None)
        same_doc = True
        print(f"\n=== {doc}  {na}: {da.matched}/8   {nb}: {db.matched}/8")
        print(f"{'field':<20} {'golden':<34} {na[:16]:<34} {nb[:16]:<34}")
        for fa, fb in zip(da.fields, db.fields):
            ma, mb = ("yes" if fa.match else "NO "), ("yes" if fb.match else "NO ")
            same = fa.match == fb.match and fmt_value(fa.predicted).lower() == fmt_value(fb.predicted).lower()
            same_doc &= same
            agree += same
            n_fields += 1
            print(f"{fa.field:<20} {fmt_value(fa.golden)[:33]:<34} {ma} {fmt_value(fa.predicted)[:29]:<30} {mb} {fmt_value(fb.predicted)[:29]:<30}" + ("" if same else "   <- differ"))
        tot_a += da.matched
        tot_b += db.matched
        identical_docs += same_doc
    n_docs = len(set(A) & set(B) & {p.stem for p in GOLD.glob('*.json')})
    print(f"\nSUMMARY over {n_docs} golden docs: {na} {tot_a}/{8*n_docs} = {pct(tot_a/(8*n_docs))} | {nb} {tot_b}/{8*n_docs} = {pct(tot_b/(8*n_docs))}")
    print(f"field-level agreement between the two models: {agree}/{n_fields} = {pct(agree/n_fields)} | documents with identical output: {identical_docs}/{n_docs}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--fields", action="store_true")
    ap.add_argument("--compare", action="store_true")
    args = ap.parse_args()
    runs = [load(Path(f)) for f in args.files]
    runs = [r for r in runs if r]
    if args.compare:
        if len(runs) != 2:
            raise SystemExit("--compare needs exactly two result files")
        compare(runs[0], runs[1])
        return
    ms = [metrics(r) for r in runs]
    print_table(ms)
    if args.fields:
        print_fields(ms)


if __name__ == "__main__":
    main()
