# medical-assistant

Course project (AI engineering): turn **dirty clinical documents into schema-valid JSON** and prove with
numbers which model, prompt and settings should go to production. Checkpoint 1 covers steps 1–2 of the
assignment (schema + baseline prompt + hosted model; second, local model + measurements). The same data
and model interface feed the RAG and agent stages later.

- Report: [`REPORT.md`](REPORT.md) · interactive version with per-document tables: `reports/checkpoint-1.html`
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

`make run` executes every configuration × every prompt version × all 50 documents (≈ 20–40 min, nearly
all of it the local model), writes one JSONL per run into `results/`, and regenerates `REPORT.md` and
`reports/checkpoint-1.html`. Faster options:

| command | what it does |
|---|---|
| `make quick` | golden documents only, ≈ 5 min |
| `make report` | rebuild both reports from the existing `results/*_full.jsonl` without calling any model |
| `make score` | print the metrics table |
| `make test` | offline checks: dataset facts, schema strictness |
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
  providers/base.py         Provider interface: extract() with retry, timeout, validation, latency, cost
  providers/anthropic_provider.py   Claude via the Anthropic SDK, structured output, effort
  providers/ollama_provider.py      any Ollama model via /api/chat with the schema in `format`
  config.py                 loads .env and config/runs.toml, builds providers
  prompts.py                prompt files → system instructions
  scoring.py                matching rules, per-field comparison with a golden label
  metrics.py                aggregate metrics per run (accuracy, validity, p50/p95, cost)
  runner.py                 the run loop, one JSONL line per document
  report_html.py / report_md.py     report generators
schema/                     re-export of the schema + report.schema.json (course deliverable)
scripts/                    make_seeds, add_noise, verify_clean, make_golden, run, score, report, extract_one
data/seeds | clean | raw | golden    dataset pipeline, see data/README.md
results/                    model outputs, one JSONL per (config, prompt), committed
reports/checkpoint-1.html   interactive report
REPORT.md                   comparison report
docs/                       research notes (harder real-world datasets)
```

## Design notes

- **One interface, any model.** `Provider.extract(instructions, text)` returns raw text, parsed JSON, validity,
  latency, tokens, attempts and cost. Timing, retry and validation live in the base class; a provider only
  implements the API call. The same hardened JSON Schema is sent to both providers.
- **Configuration, not code.** A run configuration is a name in `config/runs.toml`. Haiku 5.5 rejects
  non-default temperature/top_p, so its sampling dimension is `effort`; the local model varies temperature
  and top_p. Adding an experiment is a new TOML block.
- **Fixed matching rules.** The scorer never reads the raw text. Rules are written down in `data/README.md`
  and implemented once in `scoring.py`; they were fixed before any model output was inspected.
- **Everything regenerable.** Seeds are deterministic, noise is seeded, reports are built from result files.
  Secrets stay in `.env`; only `.env.example` is committed.

## Status

Checkpoint 1 (steps 1–2) complete; prompt v2 (step 3) exists with a changelog and golden-set numbers, the
full v2 run and the final report (step 4) follow the Q&A. Golden labels: see `data/golden/STATUS.md`.
