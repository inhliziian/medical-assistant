# Comparison report: dirty clinical documents → schema-valid JSON

Generated 2026-10-24 by `scripts/report.py` from the result files listed at the end.
Interactive version with per-document tables: `results/report-checkpoint-1.html`.

## 1. Setup

- **Task.** Extract 8 fields (3 enums, 2 nested lists, nullable scalars) from dirty clinical documents into JSON that validates against `src/medassist/schema.py`.
- **Data.** 50 synthetic documents in `data/raw/` (English, Ukrainian and mixed; consult, progress, discharge, referral, lab and radiology reports; typos, decimal commas, mangled headers, cut-off endings, missing fields). 10 documents have hand-checked golden labels in `data/golden/`. Details: `data/README.md`.
- **Models.** Hosted: `claude-haiku-5-5` through the Anthropic API with structured output. Local: `qwen3:4b` through Ollama with the same JSON schema in `format`. Both behind one `Provider` interface with retry, timeout, validation and cost accounting (`src/medassist/providers/`).
- **Configurations** (`config/runs.toml`). Haiku 5.5 rejects non-default temperature/top_p, so its sampling dimension is `effort`; the local model varies temperature and top_p.
- **Prompts** (`prompts/extraction/`, versioned with changelog): v1 in this table; v2 previewed below.
- **Metrics.** Per-field accuracy on the golden set under fixed matching rules (`src/medassist/scoring.py`): enums exact, strings normalised, lists as sets, labs on name+value+unit, medications on name+dose+frequency. Validity, latency (client wall clock incl. retries) and cost (tokens × list price) over all documents.

## 2. Results: model × prompt × sampling

| model | prompt | sampling | docs | field accuracy (golden) | docs fully correct | valid JSON | p50 | p95 | cost / 1000 docs |
|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5 | v1 | effort=high | 50 | **92.5%** | 40.0% | 100.0% | 3.1 s | 5.2 s | $0.486 |
| claude-haiku-5-5 | v1 | effort=low | 50 | **91.2%** | 40.0% | 100.0% | 1.7 s | 3.0 s | $0.320 |
| qwen3:4b | v1 | temperature=0.0, top_p=1.0 | 50 | **68.8%** | 10.0% | 100.0% | 7.3 s | 13.5 s | $0.000 |
| qwen3:4b | v1 | temperature=0.7, top_p=0.9 | 50 | **68.8%** | 10.0% | 100.0% | 6.9 s | 13.0 s | $0.000 |

### Accuracy by field

| field | haiku_high v1 | haiku_low v1 | qwen_t0 v1 | qwen_t07 v1 |
|---|---|---|---|---|
| patient_age | 100.0% | 100.0% | 100.0% | 100.0% |
| patient_sex | 100.0% | 90.0% | 80.0% | 80.0% |
| report_type | 100.0% | 100.0% | 90.0% | 90.0% |
| diagnoses | 40.0% | 40.0% | 20.0% | 20.0% |
| lab_values | 100.0% | 100.0% | 60.0% | 60.0% |
| medications | 100.0% | 100.0% | 40.0% | 40.0% |
| urgency | 100.0% | 100.0% | 60.0% | 60.0% |
| follow_up_required | 100.0% | 100.0% | 100.0% | 100.0% |

## Preview: later prompt versions (golden set only, not yet run on all documents)

| model | prompt | sampling | docs | field accuracy (golden) | docs fully correct | valid JSON | p50 | p95 | cost / 1000 docs |
|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5 | v2 | effort=low | 10 | **97.5%** | 80.0% | 100.0% | 1.7 s | 2.6 s | $0.471 |
| qwen3:4b | v2 | temperature=0.0, top_p=1.0 | 10 | **83.8%** | 0.0% | 100.0% | 9.5 s | 14.6 s | $0.000 |

### Reading the table

- **Validity is not a differentiator.** Every response from every configuration validated against the schema on the first attempt. Constrained decoding on both providers does its job; the comparison is decided by accuracy.
- **Hosted vs local.** hosted reaches n/a field accuracy; local reaches n/a. The gap is concentrated in medications, lab values and urgency; both models are perfect on age and follow-up.
- **Effort (hosted).** High effort over low gained about one golden field for roughly double the latency and 50% more cost.
- **Temperature (local).** The two Qwen settings produced identical scores and identical per-field profiles. Under schema-constrained decoding the sampler has little room to change the output; sampling knobs are not where the gains are on this task.
- **Prompt version.** The baseline prompt sets no naming conventions, which is why `diagnoses` is the weakest field for every run: models keep qualifiers such as "(left L5)" or "exacerbation" that the labels omit. Prompt v2 states the conventions learned from these errors (see its changelog).

## 3. Characteristic errors

**diagnoses** — 28 mismatches across runs

| doc | run | golden | predicted |
|---|---|---|---|
| 004 | haiku_high v1 | lumbar radiculopathy | lumbar radiculopathy (left l5) |
| 016 | haiku_high v1 | essential hypertension, elevated liver enzymes | essential hypertension, elevated liver transaminases of unclear cause |
| 032 | haiku_high v1 | lumbar radiculopathy, hyperlipidemia, acute appendicitis | lumbar radiculopathy right l5, acute appendicitis, hyperlipidemia |

**medications** — 12 mismatches across runs

| doc | run | golden | predicted |
|---|---|---|---|
| 016 | qwen_t0 v1 | amlodipine 5 mg 1x/day; lisinopril 10 mg | amlodipine 5 mg 1x/day; lisinopril 10 mg 1x/day |
| 023 | qwen_t0 v1 | amlodipine 1x/day; lisinopril 10 mg 1x/day; nitrofurantoin 100 mg 2x/day | amlodipine once daily 1x/day; lisinopril 10 mg 1x/day; nitrofurantoin 100 mg 2x/day |
| 027 | qwen_t0 v1 | sertraline 1x/day; amoxicillin-clavulanate 875/125 mg | sertraline once daily 1x/day; amoxicillin-clavulanate 875/125 mg as needed |

**lab_values** — 8 mismatches across runs

| doc | run | golden | predicted |
|---|---|---|---|
| 016 | qwen_t0 v1 | creatinine 92.0 umol/L; potassium 4.4 mmol/L; ALT 128.0 U/L; AST 96.0 | creatinine 92.0 umol/L; potassium 10.0 mmol/L; ALT 128.0 U/L; AST 96.0 U/L |
| 027 | qwen_t0 v1 | CRP 12.0; white blood cells 11.2 10^9/L | CRP 12.0 mg/L; White blood cells 11.2 10^9/L |
| 037 | qwen_t0 v1 | [] | X-ray right knee joint 1.0 mm |

**urgency** — 8 mismatches across runs

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

Interpretation of the recurring patterns:

1. **Diagnosis naming (both models).** Qualifiers kept inside the condition name, one condition split into two entries, or a Ukrainian term left untranslated. A convention problem: fixed by a prompt rule, not by a better model.
2. **Sex inferred from grammar (hosted, low effort).** Ukrainian «Пацієнт» implies male; low effort answered `unknown`, high effort `male`. Decided as a labelling convention: grammatical gender counts, relatives' pronouns do not.
3. **Dose and frequency confusion (local).** "3x/day" written into the dose field, "once daily" duplicated in both fields, dose "50:00 mg". A capability limit of a 4B model; stricter prompt rules reduce it but do not remove it.
4. **Invented units and non-lab values (local).** A unit copied from a neighbouring line onto a unit-less value; an X-ray measurement listed as a lab value. Fixed in prompt v2 by restricting `lab_values` to numeric analytes with units only as written.
5. **Urgency mis-ranking (local).** 4 of 10 golden documents at baseline, mostly `routine` vs `soon`. Explicit definitions in v2 bring it to 9 of 10.

## 4. Production decision

**Ship `haiku_high` (claude-haiku-5-5, effort=high) with the current best prompt.** It is the most accurate configuration (92.5% field accuracy on the golden set), returned valid JSON for every document, answers in 3.1 s median, and costs about $0.49 per 1,000 documents, which is negligible at any realistic clinic volume. If the two Haiku settings stay within noise of each other, prefer low effort: same validity, half the latency, lower cost. The local 4B model is not ready for production on medication and lab fields, where it loses up to 60 points to the hosted model.

**I would revisit this decision if** (a) a data-residency rule forbade sending clinical text to an external API, in which case a larger local model (14B+ on a machine with 16 GB or more) would be evaluated against the same golden set with a bar of ≥90% field accuracy and 100% validity; (b) volume exceeded roughly 500,000 documents a month, where API cost starts to matter against hardware; or (c) prompt v2 closed the local model's gap on medications and labs to within 5 points, which would make the free local option competitive for non-urgent batch processing.

## 5. Limitations

- Golden labels: 10 items. One field is 1.25 percentage points; differences of 2–3 points between runs are within run-to-run noise (the same Haiku configuration scored 88.8% and 91.2% on two runs).
- Two golden labels were corrected during the first comparison (sex labelled from the seed although the text was silent); the log is in `data/golden/STATUS.md`.
- The documents were generated by Claude Opus 5.5, the same family as the hosted model (Haiku 5.5). Familiarity may inflate the hosted score relative to Qwen. Mitigations: deterministic noise pass, a different model within the family, and planned real-world additions (`docs/hf-unstructured-data-research.md`).
- Local model size was dictated by an 8 GB laptop: Qwen3 8B swapped and timed out; Qwen3 4B fits. Token counts are not comparable across providers.

## 6. Reproduce

```bash
make install          # or: uv sync  /  pip install -r requirements.txt
cp .env.example .env  # add ANTHROPIC_API_KEY
ollama pull qwen3:4b
make run              # all configs × all prompt versions × all documents, then reports
```

Result files used for this report:

- `results/20261024-202633_haiku_high_v1_full.jsonl`
- `results/20261024-202633_haiku_low_v1_full.jsonl`
- `results/20261024-202633_qwen_t07_v1_full.jsonl`
- `results/20261024-202633_qwen_t0_v1_full.jsonl`
