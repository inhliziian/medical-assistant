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
    lines = ["| model | prompt | sampling | docs | field accuracy (golden) | docs fully correct | valid JSON | repaired / failed | p50 | p95 | cost / 1000 docs |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for m in ms_:
        lines.append(f"| {m['model']} | v{m['prompt']} | {params_str(m['params'])} | {m['n']} | **{pct(m['accuracy'])}** | "
                     f"{pct(m['doc_exact'])} | {pct(m['valid'])} | {m['n_repaired']} / {m['n_failed']} | {sec(m['p50'])} | {sec(m['p95'])} | ${m['cost_per_1000']:.3f} |")
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
    cfg = tomllib.loads((ROOT / "config/runs.toml").read_text(encoding="utf-8"))
    kind = {name: p.get("type", p.get("kind", name)) for name, p in cfg["providers"].items()}   # provider key -> anthropic | ollama
    for m in ms_:
        m["kind"] = kind.get(m["provider"], m["provider"])
    order = {"anthropic": 0, "ollama": 1}
    ms_.sort(key=lambda m: (order.get(m["kind"], 9), m["config"], m["prompt"]))
    best = max(ms_, key=lambda m: (m["accuracy"] if m["accuracy"] == m["accuracy"] else -1, -m["cost_per_1000"]))
    hosted = [m for m in ms_ if m["kind"] == "anthropic"]
    local = [m for m in ms_ if m["kind"] == "ollama"]
    n_docs = max(m["n"] for m in ms_)
    n_gold = max(m["n_golden"] for m in ms_)
    prompts = sorted({m["prompt"] for m in ms_})

    # optional preview: golden-only runs of prompt versions that have no full run yet
    preview = ""
    full_prompts = set(prompts)
    extra = sorted(p for p in (ROOT / "results").glob("*.json") if not p.name.endswith("_full.json"))
    extra_ms = [run_metrics(load_rows(p)) for p in extra]
    extra_ms = [m for m in extra_ms if m and m["prompt"] not in full_prompts]
    if extra_ms:
        latest = {}
        for m in extra_ms:
            latest[(m["config"], m["prompt"])] = m   # last one wins (files sorted by timestamp)
        pm = sorted(latest.values(), key=lambda m: (order.get(kind.get(m["provider"], m["provider"]), 9), m["config"], m["prompt"]))
        preview = ("\n## Preview: later prompt versions (golden set only, not yet run on all documents)\n\n"
                   + metrics_table(pm) + "\n")

    hosted_best = max(hosted, key=lambda m: m["accuracy"]) if hosted else None
    local_best = max(local, key=lambda m: m["accuracy"]) if local else None

    # prompt v1 -> v2 per configuration (golden field accuracy), for the narrative
    by_cfg: dict[str, dict[str, dict]] = defaultdict(dict)
    for m in ms_:
        by_cfg[m["config"]][m["prompt"]] = m
    v2_lines = []
    for c, vs in by_cfg.items():
        if "1" in vs and "2" in vs:
            a, b = vs["1"]["accuracy"], vs["2"]["accuracy"]
            v2_lines.append(f"`{c}` {pct(a)} → {pct(b)} ({100 * (b - a):+.1f} pp; cost ${vs['1']['cost_per_1000']:.3f} → ${vs['2']['cost_per_1000']:.3f} per 1,000 docs, "
                            f"input tokens {vs['1']['avg_in']:.0f} → {vs['2']['avg_in']:.0f})")
    n_first_invalid = sum(m["n_first_invalid"] for m in ms_)
    n_answers = sum(m["n"] for m in ms_)
    validity_note = ("Every one of the {n} answers in the table validated against the schema on the first attempt; the repair call never ran."
                     .format(n=n_answers) if n_first_invalid == 0 else
                     f"{n_first_invalid} of {n_answers} first answers were invalid; see the repaired / failed column.")
    demo_lines = []
    for p in sorted((ROOT / "results").glob("*_golden_unconstrained.json")):
        if p.stat().st_size == 0:
            continue
        dm = run_metrics(load_rows(p))
        demo_lines.append(f"`{dm['config']}` (prompt v{dm['prompt']}, {dm['n']} golden docs): {dm['n_ok']} ok, {dm['n_repaired']} repaired, {dm['n_failed']} failed")
    demo_text = ("; ".join(demo_lines) + ".") if demo_lines else "no demo files present."

    md = f"""# Comparison report: dirty clinical documents → schema-valid JSON

Generated {date.today().isoformat()} by `scripts/report.py` from the result files listed at the end.
Interactive version with per-document tables: `results/report-checkpoint-1.html`.

## 1. Setup

- **Task.** Extract 8 fields (3 enums, 2 nested lists, nullable scalars) from dirty clinical documents into JSON that validates against `src/medassist/schema.py`.
- **Data.** {n_docs} synthetic documents in `data/raw/` (English 30, Ukrainian 10, mixed 10; six report types; 45 to 420 words), {n_gold} with golden labels in `data/golden/`. Made in five deterministic steps: `scripts/make_seeds.py` draws 50 seeds, each a schema-valid ground-truth record plus language, style, length and a dirt plan; **Claude Opus 5.5** (five Claude Code subagents) writes one clean note per seed under `prompts/generation/v1.md` (every seed fact must appear, nothing schema-relevant may be invented, nulls mean silence); `scripts/verify_clean.py` checks every fact against the text; `scripts/add_noise.py` adds typos, decimal commas, mangled headers, case and whitespace damage, and for non-golden documents dropped sentences or a cut-off tail; `scripts/make_golden.py` writes the seed facts of the golden documents as draft labels, checked by hand against the raw text (two corrected so far; status in `data/golden/STATUS.md`). No real patient data. Opus 5.5 is the same family as the hosted evaluated model but not an evaluated model; see limitations. Details: `data/README.md`.
- **Models.** Hosted `{cfg['providers']['haiku']['model']}` (Anthropic API, structured output) and local `{cfg['providers']['qwen']['model']}` (Ollama, same JSON schema in `format`), behind one `Provider` interface (`src/medassist/providers/`).
- **Configurations** (`config/runs.toml`). Haiku 5.5 rejects non-default temperature/top_p, so its sampling dimension is `effort`; the local model varies temperature and top_p.
- **Prompts** (`prompts/extraction/`, versioned with changelog): {", ".join("v" + p for p in prompts)}{"; v2 previewed below" if preview else ""}.
- **Metrics.** Per-field accuracy on the golden set under fixed matching rules (`src/medassist/scoring.py`); validity, repairs, latency (client wall clock) and cost (tokens × list price) over all documents. Validation and repair policy: section 3.

## 2. Results: model × prompt × sampling

{metrics_table(ms_)}

### Accuracy by field

{field_table(ms_)}
{preview}
### Reading the table

- **Validity is not a differentiator in production mode.** {validity_note} Constrained decoding on both providers does its job; the comparison is decided by accuracy. The repair path is exercised separately, with the schema removed from the request (section 3).
- **Hosted vs local.** {hosted_best['model'] if hosted_best else 'hosted'} reaches {pct(hosted_best['accuracy']) if hosted_best else 'n/a'} field accuracy; {local_best['model'] if local_best else 'local'} reaches {pct(local_best['accuracy']) if local_best else 'n/a'}. The remaining gap sits in medications and lab values (the 4B model copies text into the wrong field and invents units) and in recall of drugs named late in long documents.
- **Prompt version (v1 → v2, golden field accuracy).** {"; ".join(v2_lines) if v2_lines else "only one prompt version in the table."} The longer prompt costs more input tokens per request and gains far more accuracy than any sampling change. Two of the misses that remain for the hosted model are disagreements between a v2 rule and a golden label (documents 016 and 035), not extraction errors.
- **Effort (hosted).** With v1, high effort gained about one golden field over low for roughly double the latency and 50% more cost. With v2 the two settings score the same; low effort is the better buy.
- **Temperature (local).** The two Qwen settings produced the same score under v1 and nearly the same under v2. With schema-constrained decoding the sampler has little room to change the output; sampling knobs are not where the gains are on this task.

Per-prompt comparison with every changed field, the full-dataset cost of the longer prompt and the proposals for v3: `results/report-prompt-v1-vs-v2.html` (`scripts/report_prompts.py`).

## 3. Validation, repair and failure

Every answer is validated against the schema. An invalid answer gets one repair call (same model, prompt and settings, the conversation extended with the invalid answer and the validation error); if that answer is invalid too, the document is marked `failed`. Each record logs model, prompt version and hash, sampling parameters and the status `ok` / `repaired` / `failed` / `error` (`src/medassist/providers/base.py`, tests in `tests/test_repair.py`).

With constrained decoding, the production setting, all {n_answers} answers above were valid on the first try. With the schema removed from the request (`--unconstrained`, golden documents): {demo_text} Haiku's only fault is a Markdown code fence, fixed by the repair every time; Qwen 4B answers with prose and fails. Constrained decoding stays on in production; the repair is the safety net.

## 4. Characteristic errors

{error_groups(ms_)}
Interpretation of the recurring patterns (what the model wrote instead of what, and why):

1. **Diagnosis naming (both models under v1; local under v2).** "lumbar radiculopathy (left L5)" instead of "lumbar radiculopathy", "bronchial asthma, asthma exacerbation" instead of "asthma", a Ukrainian term left untranslated. A convention problem: the v2 rule (bare English condition name, one entry per condition) fixed every Haiku case; the 4B model still keeps laterality and episode words in 3 of 10 documents, and v2 made it split "gout, recurrent gout attacks" where v1 had "gout".
2. **Rule and label disagree (both models, v2).** "elevated liver enzymes" (016) is a golden diagnosis but v2 rule 4 excludes "findings that are not diagnoses"; "L4-L5 disc protrusion" (035) keeps its level in the label but rule 4 says drop levels. Both models now follow the rule and lose the field. The fix is a decision, written into v3 and mirrored in the labels.
3. **Dose and frequency confusion (local).** "once daily" written into dose while frequency already says 1x/day (023, 027), "50:00 mg" for "500 mg" (004). Rule 6 forbids exactly this, and the 4B model still does it when the drug has no dose in the text. A dose pattern in the schema would turn these into validation failures the repair step can fix.
4. **Invented units (local).** CRP 12 (no unit written) gets "10^9/L" from the next value (027); "AST was 96." gets "U/L" from ALT (016). Rule 5 says "never add a unit"; the written rule does not reach the model, a worked example might.
5. **Missed drugs and the urgency word trap (local).** Naproxen on hold (032) and ibuprofen at the end of a 500-word Ukrainian dictation (037) are dropped from the list; "urinary urgency" in the first line of 023 pushes `urgency` to `urgent` although follow-up is "within 1 week". Recall over long unstructured text is where the 4B model loses to the hosted one; the hosted model made none of these errors under v2.

## 5. Production decision

**Ship `{best['config']}` ({best['model']}, {params_str(best['params'])}) with prompt v{best['prompt']}, constrained decoding on, one repair call as safety net.** Highest golden accuracy ({pct(best['accuracy'])}), valid JSON on all {best['n']} documents, {sec(best['p50'])} median latency, about ${best['cost_per_1000']:.2f} per 1,000 documents. High effort scores the same for more latency and cost; the local 4B model ({pct(local_best['accuracy']) if local_best else 'n/a'} at best) still fails on medications and labs, the clinically critical fields.

**I would change the decision if** a data-residency rule forbade sending clinical text to an external API. Then a larger local model (14B+ on a machine with 16 GB or more) would be evaluated against the same golden set, with a bar of ≥90% field accuracy and 100% validity before it replaces the hosted model.

## 6. Limitations

- Golden labels: {n_gold} items. One field is {100 / (8 * n_gold):.2f} percentage points; differences of 2–3 points between runs are within run-to-run noise (the same Haiku configuration scored 88.8% and 91.2% on two runs).
- Two golden labels were corrected during the first comparison (sex labelled from the seed although the text was silent); the log is in `data/golden/STATUS.md`.
- The documents were generated by Claude Opus 5.5, the same family as the hosted model (Haiku 5.5). Familiarity may inflate the hosted score relative to Qwen. Mitigations: deterministic noise pass, a different model within the family, and planned real-world additions (`docs/hf-unstructured-data-research.md`).
- Local model size was dictated by an 8 GB laptop: Qwen3 8B swapped and timed out; Qwen3 4B fits. Token counts are not comparable across providers.

## 7. Reproduce

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
