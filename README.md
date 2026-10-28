# medical-assistant

Course project (AI engineering): turn **dirty clinical documents into schema-valid JSON** and prove with
numbers which model, prompt and settings should go to production. Steps 1–2 of the assignment: schema,
baseline prompt, hosted model, then a local model and measurements. Step 3: prompt v2 with a changelog,
schema validation with one repair attempt, every result logged with model, prompt version and sampling
parameters. Step 4: the comparison report. The same data and model interface feed the RAG and agent
stages later.

- Report: [`REPORT.md`](REPORT.md) · interactive version with per-document tables: `results/report-checkpoint-1.html`
- Prompt v1 against v2, field by field, with the proposals for v3: `results/report-prompt-v1-vs-v2.html`
- Dataset: 50 dirty documents (EN / UK / mixed), 10 golden labels — [`data/README.md`](data/README.md)
- Prompts with versions and changelog: [`prompts/extraction/`](prompts/extraction/)

## Run it

Requirements: Python 3.11+, [Ollama](https://ollama.com) for the local model, an Anthropic API key
(a few cents of credit is enough: a full run costs about $0.10).

```bash
git clone https://github.com/inhliziian/medical-assistant.git && cd medical-assistant
make install                 # uv sync if uv is installed, otherwise pip install -r requirements.txt; creates .env
# edit .env and set ANTHROPIC_API_KEY=sk-ant-...
ollama pull qwen3:4b         # 2.5 GB; fits an 8 GB laptop
make run                     # == python main.py
```

`make run` executes every configuration with prompts v1 and v2 over all 50 documents (≈ 30 min, nearly all
of it the local model), writes one JSON file per run into `results/`, and regenerates `REPORT.md`,
`results/report-checkpoint-1.html` and `results/report-prompt-v1-vs-v2.html`. `python main.py --prompts v1`
runs one version only. Other options:

| command | what it does |
|---|---|
| `make quick` | golden documents only, ≈ 3 min |
| `make report` | rebuild both reports from the existing `results/*_full.json` without calling any model |
| `make score` | print the metrics table |
| `make test` | offline checks: validate → repair → failed policy (fake provider, no API), dataset facts, schema strictness |
| `python main.py --quick --prompts v2 --unconstrained` | free-form JSON (schema dropped from the request): shows real validation failures and the one-shot repair |
| `python main.py --configs haiku_low --prompts v1 --docs 004` | one document, one config |
| `python scripts/extract_one.py --config qwen_t0 --doc 034 --golden` | one document with the field-by-field comparison |

Without `make`: `python main.py` with the same flags. `uv run python main.py` if you use uv.

## What is where

```
main.py                     one-command entry point (run → score → reports)
Makefile                    install / run / quick / report / score / test
config/runs.toml            providers (model, price, timeout) and named configurations (effort / temperature / top_p)
prompts/extraction/v1.md    baseline prompt  (front matter: version, date, changelog)
prompts/extraction/v2.md    rules learned from v1 errors on the golden set
prompts/generation/v1.md    prompt used to generate the synthetic documents
src/medassist/
  schema.py                 Pydantic model: 8 fields, 3 enums, 2 nested lists; strict JSON Schema export
  providers/base.py         Provider interface: extract() with transport retry, validation, one repair call, latency, cost
  providers/anthropic_provider.py   Claude via the Anthropic SDK, structured output, effort
  providers/ollama_provider.py      any Ollama model via /api/chat with the schema in `format`
  config.py                 loads .env and config/runs.toml, builds providers
  prompts.py                prompt files → system instructions
  scoring.py                matching rules, per-field comparison with a golden label
  metrics.py                aggregate metrics per run (accuracy, validity, p50/p95, cost)
  runner.py                 the run loop, one JSON record per document
  report_html.py / report_md.py / report_prompts.py     report generators
schema/                     re-export of the schema + report.schema.json (course deliverable)
scripts/                    make_seeds, add_noise, verify_clean, make_golden, run, score, report, extract_one
data/seeds | clean | raw | golden    dataset pipeline, see data/README.md
tests/test_repair.py        the validate → repair → failed policy, exercised with a scripted fake provider
results/                    model outputs, one JSON file per (config, prompt), committed
results/report-checkpoint-1.html   interactive report (all runs, per-document tables, Q&A notes)
results/report-prompt-v1-vs-v2.html   prompt v1 against v2, remaining errors, proposals for v3
results/*_golden_unconstrained.json   task 3 evidence: runs with the schema removed from the request
REPORT.md                   comparison report (step 4)
docs/                       research notes (harder real-world datasets)
```

## Design notes

- **One interface, any model.** `Provider.extract(instructions, text)` returns raw text, parsed JSON, validity,
  status, latency, tokens, attempts and cost. Timing, retry, validation and repair live in the base class; a
  provider only implements the API call. The same hardened JSON Schema is sent to both providers.
- **Validate, repair once, then fail.** Every answer is validated against the schema. An invalid answer gets
  exactly one repair call with the same model, prompt and sampling settings: the conversation is extended with
  the model's invalid answer and the validation error, and the model is asked for a corrected object. The
  record's `status` is `ok`, `repaired`, `failed` (second answer also invalid) or `error` (transport failure
  after retries). Transport retries are counted separately and are never repairs. With constrained decoding
  on, both providers return valid JSON on the first try; `--unconstrained` drops the schema from the request so
  the repair path is exercised for real.
- **Every result is traceable.** Each record logs the configuration name, model, sampling parameters, prompt
  version and a hash of the prompt file, so a result can always be tied to the exact prompt text it was made with.
- **Configuration, not code.** A run configuration is a name in `config/runs.toml`. Haiku 5.5 rejects
  non-default temperature/top_p, so its sampling dimension is `effort`; the local model varies temperature
  and top_p. Adding an experiment is a new TOML block.
- **Fixed matching rules.** The scorer never reads the raw text. Rules are written down in `data/README.md`
  and implemented once in `scoring.py`; they were fixed before any model output was inspected.
- **Everything regenerable.** Seeds are deterministic, noise is seeded, reports are built from result files.
  Secrets stay in `.env`; only `.env.example` is committed.

## Status

Steps 1–4 complete: both prompt versions run on all 50 documents for all four configurations, validation
with one repair attempt in place and demonstrated, `REPORT.md` carries the comparison table, the error
analysis and the production decision. Open points: the golden labels still need the human verification
pass (`data/golden/STATUS.md`), and two label-vs-rule conventions (documents 016 and 035) must be decided
before prompt v3.
