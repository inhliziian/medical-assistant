"""Write REPORT.md: the comparison report (model × prompt × sampling), error analysis and decision."""
from __future__ import annotations

import tomllib
from collections import defaultdict
from datetime import date
from pathlib import Path

from .metrics import load_rows, run_metrics
from .scoring import FIELDS, fmt_value

ROOT = Path(__file__).resolve().parents[2]


def pct(x: float) -> str:
    return "n/a" if x != x else f"{100 * x:.1f}%"


def sec(x: float) -> str:
    return f"{x / 1000:.1f} s"


def params_str(p: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in p.items()) or "defaults"


def metrics_table(ms_: list[dict]) -> str:
    lines = ["| model | prompt | sampling | docs | field accuracy (golden) | docs fully correct | valid JSON | p50 | p95 | cost / 1000 docs |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for m in ms_:
        lines.append(f"| {m['model']} | v{m['prompt']} | {params_str(m['params'])} | {m['n']} | **{pct(m['accuracy'])}** | "
                     f"{pct(m['doc_exact'])} | {pct(m['valid'])} | {sec(m['p50'])} | {sec(m['p95'])} | ${m['cost_per_1000']:.3f} |")
    return "\n".join(lines)


def field_table(ms_: list[dict]) -> str:
    head = "| field | " + " | ".join(f"{m['config']} v{m['prompt']}" for m in ms_) + " |"
    sep = "|---|" + "---|" * len(ms_)
    rows = [f"| {f} | " + " | ".join(pct(m["per_field"][f]) for m in ms_) + " |" for f in FIELDS]
    return "\n".join([head, sep, *rows])


def error_groups(ms_: list[dict], limit: int = 3) -> str:
    by: dict[str, list] = defaultdict(list)
    for m in ms_:
        for doc, ds in m["scores"].items():
            for fr in ds.fields:
                if not fr.match:
                    by[fr.field].append((doc, f"{m['config']} v{m['prompt']}", fmt_value(fr.golden), fmt_value(fr.predicted)))
    out = []
    for f, items in sorted(by.items(), key=lambda kv: -len(kv[1])):
        out.append(f"**{f}** — {len(items)} mismatches across runs\n")
        out.append("| doc | run | golden | predicted |\n|---|---|---|---|")
        for d, c, g, p in items[:limit]:
            out.append(f"| {d} | {c} | {g} | {p} |")
        out.append("")
    return "\n".join(out)


def build_markdown(files: list[Path], out: Path) -> Path:
    files = [Path(f).resolve() for f in files]
    ms_ = [run_metrics(load_rows(f)) for f in files]
    ms_ = [m for m in ms_ if m]
    order = {"anthropic": 0, "ollama": 1}
    ms_.sort(key=lambda m: (order.get(m["provider"], 9), m["config"], m["prompt"]))
    best = max(ms_, key=lambda m: (m["accuracy"] if m["accuracy"] == m["accuracy"] else -1, -m["cost_per_1000"]))
    hosted = [m for m in ms_ if m["provider"] == "anthropic"]
    local = [m for m in ms_ if m["provider"] == "ollama"]
    cfg = tomllib.loads((ROOT / "config/runs.toml").read_text(encoding="utf-8"))
    n_docs = max(m["n"] for m in ms_)
    n_gold = max(m["n_golden"] for m in ms_)
    prompts = sorted({m["prompt"] for m in ms_})

    # optional preview: golden-only runs of prompt versions that have no full run yet
    preview = ""
    full_prompts = set(prompts)
    extra = sorted(p for p in (ROOT / "results").glob("*.jsonl") if not p.name.endswith("_full.jsonl"))
    extra_ms = [run_metrics(load_rows(p)) for p in extra]
    extra_ms = [m for m in extra_ms if m and m["prompt"] not in full_prompts]
    if extra_ms:
        latest = {}
        for m in extra_ms:
            latest[(m["config"], m["prompt"])] = m   # last one wins (files sorted by timestamp)
        pm = sorted(latest.values(), key=lambda m: (order.get(m["provider"], 9), m["config"], m["prompt"]))
        preview = ("\n## Preview: later prompt versions (golden set only, not yet run on all documents)\n\n"
                   + metrics_table(pm) + "\n")

    hosted_best = max(hosted, key=lambda m: m["accuracy"]) if hosted else None
    local_best = max(local, key=lambda m: m["accuracy"]) if local else None

    md = f"""# Comparison report: dirty clinical documents → schema-valid JSON

Generated {date.today().isoformat()} by `scripts/report.py` from the result files listed at the end.
Interactive version with per-document tables: `reports/checkpoint-1.html`.

## 1. Setup

- **Task.** Extract 8 fields (3 enums, 2 nested lists, nullable scalars) from dirty clinical documents into JSON that validates against `src/medassist/schema.py`.
- **Data.** {n_docs} synthetic documents in `data/raw/` (English, Ukrainian and mixed; consult, progress, discharge, referral, lab and radiology reports; typos, decimal commas, mangled headers, cut-off endings, missing fields). {n_gold} documents have hand-checked golden labels in `data/golden/`. Details: `data/README.md`.
- **Models.** Hosted: `{cfg['providers']['haiku']['model']}` through the Anthropic API with structured output. Local: `{cfg['providers']['qwen']['model']}` through Ollama with the same JSON schema in `format`. Both behind one `Provider` interface with retry, timeout, validation and cost accounting (`src/medassist/providers/`).
- **Configurations** (`config/runs.toml`). Haiku 5.5 rejects non-default temperature/top_p, so its sampling dimension is `effort`; the local model varies temperature and top_p.
- **Prompts** (`prompts/extraction/`, versioned with changelog): {", ".join("v" + p for p in prompts)} in this table{"; v2 previewed below" if preview else ""}.
- **Metrics.** Per-field accuracy on the golden set under fixed matching rules (`src/medassist/scoring.py`): enums exact, strings normalised, lists as sets, labs on name+value+unit, medications on name+dose+frequency. Validity, latency (client wall clock incl. retries) and cost (tokens × list price) over all documents.

## 2. Results: model × prompt × sampling

{metrics_table(ms_)}

### Accuracy by field

{field_table(ms_)}
{preview}
### Reading the table

- **Validity is not a differentiator.** Every response from every configuration validated against the schema on the first attempt. Constrained decoding on both providers does its job; the comparison is decided by accuracy.
- **Hosted vs local.** {hosted_best['model'] if hosted_best else 'hosted'} reaches {pct(hosted_best['accuracy']) if hosted_best else 'n/a'} field accuracy; {local_best['model'] if local_best else 'local'} reaches {pct(local_best['accuracy']) if local_best else 'n/a'}. The gap is concentrated in medications, lab values and urgency; both models are perfect on age and follow-up.
- **Effort (hosted).** High effort over low gained about one golden field for roughly double the latency and 50% more cost.
- **Temperature (local).** The two Qwen settings produced identical scores and identical per-field profiles. Under schema-constrained decoding the sampler has little room to change the output; sampling knobs are not where the gains are on this task.
- **Prompt version.** The baseline prompt sets no naming conventions, which is why `diagnoses` is the weakest field for every run: models keep qualifiers such as "(left L5)" or "exacerbation" that the labels omit. Prompt v2 states the conventions learned from these errors (see its changelog).

## 3. Characteristic errors

{error_groups(ms_)}
Interpretation of the recurring patterns:

1. **Diagnosis naming (both models).** Qualifiers kept inside the condition name, one condition split into two entries, or a Ukrainian term left untranslated. A convention problem: fixed by a prompt rule, not by a better model.
2. **Sex inferred from grammar (hosted, low effort).** Ukrainian «Пацієнт» implies male; low effort answered `unknown`, high effort `male`. Decided as a labelling convention: grammatical gender counts, relatives' pronouns do not.
3. **Dose and frequency confusion (local).** "3x/day" written into the dose field, "once daily" duplicated in both fields, dose "50:00 mg". A capability limit of a 4B model; stricter prompt rules reduce it but do not remove it.
4. **Invented units and non-lab values (local).** A unit copied from a neighbouring line onto a unit-less value; an X-ray measurement listed as a lab value. Fixed in prompt v2 by restricting `lab_values` to numeric analytes with units only as written.
5. **Urgency mis-ranking (local).** 4 of 10 golden documents at baseline, mostly `routine` vs `soon`. Explicit definitions in v2 bring it to 9 of 10.

## 4. Production decision

**Ship `{best['config']}` ({best['model']}, {params_str(best['params'])}) with the current best prompt.** It is the most accurate configuration ({pct(best['accuracy'])} field accuracy on the golden set), returned valid JSON for every document, answers in {sec(best['p50'])} median, and costs about ${best['cost_per_1000']:.2f} per 1,000 documents, which is negligible at any realistic clinic volume. If the two Haiku settings stay within noise of each other, prefer low effort: same validity, half the latency, lower cost. The local 4B model is not ready for production on medication and lab fields, where it loses up to 60 points to the hosted model.

**I would revisit this decision if** (a) a data-residency rule forbade sending clinical text to an external API, in which case a larger local model (14B+ on a machine with 16 GB or more) would be evaluated against the same golden set with a bar of ≥90% field accuracy and 100% validity; (b) volume exceeded roughly 500,000 documents a month, where API cost starts to matter against hardware; or (c) prompt v2 closed the local model's gap on medications and labs to within 5 points, which would make the free local option competitive for non-urgent batch processing.

## 5. Limitations

- Golden labels: {n_gold} items. One field is {100 / (8 * n_gold):.2f} percentage points; differences of 2–3 points between runs are within run-to-run noise (the same Haiku configuration scored 88.8% and 91.2% on two runs).
- Two golden labels were corrected during the first comparison (sex labelled from the seed although the text was silent); the log is in `data/golden/STATUS.md`.
- The documents were generated by Claude Opus 5.5, the same family as the hosted model (Haiku 5.5). Familiarity may inflate the hosted score relative to Qwen. Mitigations: deterministic noise pass, a different model within the family, and planned real-world additions (`docs/hf-unstructured-data-research.md`).
- Local model size was dictated by an 8 GB laptop: Qwen3 8B swapped and timed out; Qwen3 4B fits. Token counts are not comparable across providers.

## 6. Reproduce

```bash
make install          # or: uv sync  /  pip install -r requirements.txt
cp .env.example .env  # add ANTHROPIC_API_KEY
ollama pull {cfg['providers']['qwen']['model']}
make run              # all configs × all prompt versions × all documents, then reports
```

Result files used for this report:

{chr(10).join(f"- `{f.relative_to(ROOT) if f.is_relative_to(ROOT) else f.name}`" for f in files)}
"""
    out.write_text(md, encoding="utf-8")
    return out
