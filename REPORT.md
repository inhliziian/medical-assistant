# Comparison report: dirty clinical documents → schema-valid JSON

Generated 2026-10-28 by `scripts/report.py` from the result files listed at the end.
Interactive version with per-document tables: `results/report-checkpoint-1.html`.

## 1. Setup

- **Task.** Extract 8 fields (3 enums, 2 nested lists, nullable scalars) from dirty clinical documents into JSON that validates against `src/medassist/schema.py`.
- **Data.** 50 synthetic documents in `data/raw/` (English 30, Ukrainian 10, mixed 10; six report types; 45 to 420 words), 10 with golden labels in `data/golden/`. Made in five deterministic steps: `scripts/make_seeds.py` draws 50 seeds, each a schema-valid ground-truth record plus language, style, length and a dirt plan; **Claude Opus 5.5** (five Claude Code subagents) writes one clean note per seed under `prompts/generation/v1.md` (every seed fact must appear, nothing schema-relevant may be invented, nulls mean silence); `scripts/verify_clean.py` checks every fact against the text; `scripts/add_noise.py` adds typos, decimal commas, mangled headers, case and whitespace damage, and for non-golden documents dropped sentences or a cut-off tail; `scripts/make_golden.py` writes the seed facts of the golden documents as draft labels, checked by hand against the raw text (two corrected so far; status in `data/golden/STATUS.md`). No real patient data. Opus 5.5 is the same family as the hosted evaluated model but not an evaluated model; see limitations. Details: `data/README.md`.
- **Models.** Hosted `claude-haiku-5-5` (Anthropic API, structured output) and local `qwen3:4b` (Ollama, same JSON schema in `format`), behind one `Provider` interface (`src/medassist/providers/`).
- **Configurations** (`config/runs.toml`). Haiku 5.5 rejects non-default temperature/top_p, so its sampling dimension is `effort`; the local model varies temperature and top_p.
- **Prompts** (`prompts/extraction/`, versioned with changelog): v1, v2.
- **Metrics.** Per-field accuracy on the golden set under fixed matching rules (`src/medassist/scoring.py`); validity, repairs, latency (client wall clock) and cost (tokens × list price) over all documents. Validation and repair policy: section 3.

## 2. Results: model × prompt × sampling

| model | prompt | sampling | docs | field accuracy (golden) | docs fully correct | valid JSON | repaired / failed | p50 | p95 | cost / 1000 docs |
|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5 | v1 | effort=high | 50 | **92.5%** | 40.0% | 100.0% | 0 / 0 | 3.1 s | 5.2 s | $0.486 |
| claude-haiku-5-5 | v2 | effort=high | 50 | **97.5%** | 80.0% | 100.0% | 0 / 0 | 2.9 s | 4.7 s | $0.610 |
| claude-haiku-5-5 | v1 | effort=low | 50 | **91.2%** | 40.0% | 100.0% | 0 / 0 | 1.7 s | 3.0 s | $0.320 |
| claude-haiku-5-5 | v2 | effort=low | 50 | **97.5%** | 80.0% | 100.0% | 0 / 0 | 1.8 s | 3.7 s | $0.445 |
| qwen3:4b | v1 | temperature=0.0, top_p=1.0 | 50 | **68.8%** | 10.0% | 100.0% | 0 / 0 | 7.3 s | 13.5 s | $0.000 |
| qwen3:4b | v2 | temperature=0.0, top_p=1.0 | 50 | **83.8%** | 0.0% | 100.0% | 0 / 0 | 6.7 s | 12.4 s | $0.000 |
| qwen3:4b | v1 | temperature=0.7, top_p=0.9 | 50 | **68.8%** | 10.0% | 100.0% | 0 / 0 | 6.9 s | 13.0 s | $0.000 |
| qwen3:4b | v2 | temperature=0.7, top_p=0.9 | 50 | **81.2%** | 0.0% | 100.0% | 0 / 0 | 6.9 s | 11.7 s | $0.000 |

### Accuracy by field

| field | haiku_high v1 | haiku_high v2 | haiku_low v1 | haiku_low v2 | qwen_t0 v1 | qwen_t0 v2 | qwen_t07 v1 | qwen_t07 v2 |
|---|---|---|---|---|---|---|---|---|
| patient_age | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| patient_sex | 100.0% | 100.0% | 90.0% | 100.0% | 80.0% | 100.0% | 80.0% | 100.0% |
| report_type | 100.0% | 100.0% | 100.0% | 100.0% | 90.0% | 100.0% | 90.0% | 100.0% |
| diagnoses | 40.0% | 80.0% | 40.0% | 80.0% | 20.0% | 60.0% | 20.0% | 60.0% |
| lab_values | 100.0% | 100.0% | 100.0% | 100.0% | 60.0% | 70.0% | 60.0% | 70.0% |
| medications | 100.0% | 100.0% | 100.0% | 100.0% | 40.0% | 50.0% | 40.0% | 50.0% |
| urgency | 100.0% | 100.0% | 100.0% | 100.0% | 60.0% | 90.0% | 60.0% | 70.0% |
| follow_up_required | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |

### Reading the table

- **Validity is not a differentiator in production mode.** Every one of the 400 answers in the table validated against the schema on the first attempt; the repair call never ran. Constrained decoding on both providers does its job; the comparison is decided by accuracy. The repair path is exercised separately, with the schema removed from the request (section 3).
- **Hosted vs local.** claude-haiku-5-5 reaches 97.5% field accuracy; qwen3:4b reaches 83.8%. The remaining gap sits in medications and lab values (the 4B model copies text into the wrong field and invents units) and in recall of drugs named late in long documents.
- **Prompt version (v1 → v2, golden field accuracy).** `haiku_high` 92.5% → 97.5% (+5.0 pp; cost $0.486 → $0.610 per 1,000 docs, input tokens 1986 → 3304); `haiku_low` 91.2% → 97.5% (+6.2 pp; cost $0.320 → $0.445 per 1,000 docs, input tokens 1986 → 3304); `qwen_t0` 68.8% → 83.8% (+15.0 pp; cost $0.000 → $0.000 per 1,000 docs, input tokens 426 → 1372); `qwen_t07` 68.8% → 81.2% (+12.5 pp; cost $0.000 → $0.000 per 1,000 docs, input tokens 426 → 1372) The longer prompt costs more input tokens per request and gains far more accuracy than any sampling change. Two of the misses that remain for the hosted model are disagreements between a v2 rule and a golden label (documents 016 and 035), not extraction errors.
- **Effort (hosted).** With v1, high effort gained about one golden field over low for roughly double the latency and 50% more cost. With v2 the two settings score the same; low effort is the better buy.
- **Temperature (local).** The two Qwen settings produced the same score under v1 and nearly the same under v2. With schema-constrained decoding the sampler has little room to change the output; sampling knobs are not where the gains are on this task.

Per-prompt comparison with every changed field, the full-dataset cost of the longer prompt and the proposals for v3: `results/report-prompt-v1-vs-v2.html` (`scripts/report_prompts.py`).

## 3. Validation, repair and failure

Every answer is validated against the schema. An invalid answer gets one repair call (same model, prompt and settings, the conversation extended with the invalid answer and the validation error); if that answer is invalid too, the document is marked `failed`. Each record logs model, prompt version and hash, sampling parameters and the status `ok` / `repaired` / `failed` / `error` (`src/medassist/providers/base.py`, tests in `tests/test_repair.py`).

With constrained decoding, the production setting, all 400 answers above were valid on the first try. With the schema removed from the request (`--unconstrained`, golden documents): `haiku_low` (prompt v2, 10 golden docs): 3 ok, 7 repaired, 0 failed; `qwen_t0` (prompt v2, 4 golden docs): 0 ok, 0 repaired, 4 failed. Haiku's only fault is a Markdown code fence, fixed by the repair every time; Qwen 4B answers with prose and fails. Constrained decoding stays on in production; the repair is the safety net.

## 4. Characteristic errors

**diagnoses** — 40 mismatches across runs

| doc | run | golden | predicted |
|---|---|---|---|
| 004 | haiku_high v1 | lumbar radiculopathy | lumbar radiculopathy (left l5) |
| 016 | haiku_high v1 | essential hypertension, elevated liver enzymes | essential hypertension, elevated liver transaminases of unclear cause |
| 032 | haiku_high v1 | lumbar radiculopathy, hyperlipidemia, acute appendicitis | lumbar radiculopathy right l5, acute appendicitis, hyperlipidemia |

**medications** — 22 mismatches across runs

| doc | run | golden | predicted |
|---|---|---|---|
| 016 | qwen_t0 v1 | amlodipine 5 mg 1x/day; lisinopril 10 mg | amlodipine 5 mg 1x/day; lisinopril 10 mg 1x/day |
| 023 | qwen_t0 v1 | amlodipine 1x/day; lisinopril 10 mg 1x/day; nitrofurantoin 100 mg 2x/day | amlodipine once daily 1x/day; lisinopril 10 mg 1x/day; nitrofurantoin 100 mg 2x/day |
| 027 | qwen_t0 v1 | sertraline 1x/day; amoxicillin-clavulanate 875/125 mg | sertraline once daily 1x/day; amoxicillin-clavulanate 875/125 mg as needed |

**lab_values** — 14 mismatches across runs

| doc | run | golden | predicted |
|---|---|---|---|
| 016 | qwen_t0 v1 | creatinine 92.0 umol/L; potassium 4.4 mmol/L; ALT 128.0 U/L; AST 96.0 | creatinine 92.0 umol/L; potassium 10.0 mmol/L; ALT 128.0 U/L; AST 96.0 U/L |
| 027 | qwen_t0 v1 | CRP 12.0; white blood cells 11.2 10^9/L | CRP 12.0 mg/L; White blood cells 11.2 10^9/L |
| 037 | qwen_t0 v1 | [] | X-ray right knee joint 1.0 mm |

**urgency** — 12 mismatches across runs

| doc | run | golden | predicted |
|---|---|---|---|
| 016 | qwen_t0 v1 | soon | routine |
| 023 | qwen_t0 v1 | soon | urgent |
| 037 | qwen_t0 v1 | routine | urgent |

**patient_sex** — 5 mismatches across runs

| doc | run | golden | predicted |
|---|---|---|---|
| 037 | haiku_low v1 | male | unknown |
| 032 | qwen_t0 v1 | unknown | male |
| 048 | qwen_t0 v1 | unknown | male |

**report_type** — 2 mismatches across runs

| doc | run | golden | predicted |
|---|---|---|---|
| 027 | qwen_t0 v1 | progress_note | consult |
| 027 | qwen_t07 v1 | progress_note | consult |

Interpretation of the recurring patterns (what the model wrote instead of what, and why):

1. **Diagnosis naming (both models under v1; local under v2).** "lumbar radiculopathy (left L5)" instead of "lumbar radiculopathy", "bronchial asthma, asthma exacerbation" instead of "asthma", a Ukrainian term left untranslated. A convention problem: the v2 rule (bare English condition name, one entry per condition) fixed every Haiku case; the 4B model still keeps laterality and episode words in 3 of 10 documents, and v2 made it split "gout, recurrent gout attacks" where v1 had "gout".
2. **Rule and label disagree (both models, v2).** "elevated liver enzymes" (016) is a golden diagnosis but v2 rule 4 excludes "findings that are not diagnoses"; "L4-L5 disc protrusion" (035) keeps its level in the label but rule 4 says drop levels. Both models now follow the rule and lose the field. The fix is a decision, written into v3 and mirrored in the labels.
3. **Dose and frequency confusion (local).** "once daily" written into dose while frequency already says 1x/day (023, 027), "50:00 mg" for "500 mg" (004). Rule 6 forbids exactly this, and the 4B model still does it when the drug has no dose in the text. A dose pattern in the schema would turn these into validation failures the repair step can fix.
4. **Invented units (local).** CRP 12 (no unit written) gets "10^9/L" from the next value (027); "AST was 96." gets "U/L" from ALT (016). Rule 5 says "never add a unit"; the written rule does not reach the model, a worked example might.
5. **Missed drugs and the urgency word trap (local).** Naproxen on hold (032) and ibuprofen at the end of a 500-word Ukrainian dictation (037) are dropped from the list; "urinary urgency" in the first line of 023 pushes `urgency` to `urgent` although follow-up is "within 1 week". Recall over long unstructured text is where the 4B model loses to the hosted one; the hosted model made none of these errors under v2.

## 5. Production decision

**Ship `haiku_low` (claude-haiku-5-5, effort=low) with prompt v2, constrained decoding on, one repair call as safety net.** Highest golden accuracy (97.5%), valid JSON on all 50 documents, 1.8 s median latency, about $0.45 per 1,000 documents. High effort scores the same for more latency and cost; the local 4B model (83.8% at best) still fails on medications and labs, the clinically critical fields.

**I would change the decision if** a data-residency rule forbade sending clinical text to an external API. Then a larger local model (14B+ on a machine with 16 GB or more) would be evaluated against the same golden set, with a bar of ≥90% field accuracy and 100% validity before it replaces the hosted model.

## 6. Limitations

- Golden labels: 10 items. One field is 1.25 percentage points; differences of 2–3 points between runs are within run-to-run noise (the same Haiku configuration scored 88.8% and 91.2% on two runs).
- Two golden labels were corrected during the first comparison (sex labelled from the seed although the text was silent); the log is in `data/golden/STATUS.md`.
- The documents were generated by Claude Opus 5.5, the same family as the hosted model (Haiku 5.5). Familiarity may inflate the hosted score relative to Qwen. Mitigations: deterministic noise pass, a different model within the family, and planned real-world additions (`docs/hf-unstructured-data-research.md`).
- Local model size was dictated by an 8 GB laptop: Qwen3 8B swapped and timed out; Qwen3 4B fits. Token counts are not comparable across providers.

## 7. Reproduce

```bash
make install          # or: uv sync  /  pip install -r requirements.txt
cp .env.example .env  # add ANTHROPIC_API_KEY
ollama pull qwen3:4b
make run              # all configs × all prompt versions × all documents, then reports
```

Result files used for this report:

- `results/20261024-202633_haiku_high_v1_full.json`
- `results/20261024-202633_haiku_low_v1_full.json`
- `results/20261024-202633_qwen_t07_v1_full.json`
- `results/20261024-202633_qwen_t0_v1_full.json`
- `results/20261027-224121_haiku_high_v2_full.json`
- `results/20261027-224121_haiku_low_v2_full.json`
- `results/20261027-224121_qwen_t07_v2_full.json`
- `results/20261027-224121_qwen_t0_v2_full.json`
