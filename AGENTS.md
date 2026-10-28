# AGENTS.md

Instructions for coding agents (and humans) working in this repository.

## What this project is

Course project: dirty clinical documents (English, Ukrainian, mixed) → schema-valid JSON, with a measured
comparison of a hosted model (Claude Haiku 5.5) and a local model (Qwen3 4B via Ollama) across prompt
versions and sampling settings. Deliverables: code + schema, versioned prompts, dataset with golden labels,
model outputs in `results/`, `REPORT.md`, `README.md`.

## Run and test

```bash
make install            # uv sync (or pip install -r requirements.txt); copies .env.example -> .env
make run                # == python main.py: prompts v1,v2 × all configs × all 50 docs, then all reports
make quick              # golden documents only (fast smoke run)
make report             # rebuild REPORT.md and results/*.html from results/*_full.json, no model calls
make test               # offline: tests/ (repair policy with a fake provider), dataset facts, schema strictness
python main.py --quick --prompts v2 --unconstrained   # schema removed from the request: exercises validation + repair
python scripts/extract_one.py --config haiku_low --doc 004 --prompt v2 --golden   # one document, scored
```

Python 3.11+. `ANTHROPIC_API_KEY` lives in `.env` (git-ignored); Ollama must be running with `qwen3:4b`
pulled. `main.py` checks both before running.

## Layout

| Path | Role |
|---|---|
| `src/medassist/schema.py` | Pydantic `Report` and the hardened JSON Schema sent to both providers |
| `src/medassist/providers/` | `base.py`: `Provider.extract()` = call → validate → one repair call → status; `anthropic_provider.py`, `ollama_provider.py` implement `_call` only |
| `src/medassist/config.py`, `config/runs.toml` | named run configurations (provider, model, params, prices) |
| `src/medassist/prompts.py`, `prompts/extraction/v*.md` | prompt files with front matter (`version`, `changelog`); content hash logged per result |
| `src/medassist/runner.py` | run loop; one pretty-printed JSON array per (config, prompt) in `results/` |
| `src/medassist/scoring.py`, `metrics.py` | golden matching rules and per-run metrics |
| `src/medassist/report_md.py`, `report_html.py`, `report_prompts.py` | `REPORT.md`, `results/report-checkpoint-1.html`, `results/report-prompt-v1-vs-v2.html` |
| `scripts/` | dataset pipeline (`make_seeds`, `add_noise`, `verify_clean`, `make_golden`) and thin CLI wrappers |
| `data/` | `seeds/` → `clean/` → `raw/` (the dataset) + `golden/` labels; see `data/README.md` |
| `tests/test_repair.py` | validate → repair → failed policy, offline |

## Rules

- **Reports are generated.** Never hand-edit `REPORT.md` or `results/*.html`; change the generator in
  `src/medassist/report_*.py` and run `make report`. Numbers in the prose must come from the result files.
- **Prompts are versioned.** A behaviour change in extraction instructions is a new file
  `prompts/extraction/vN.md` with a `changelog` in the front matter that cites the errors it answers. Prompts
  stay model-independent: no Qwen-only or Haiku-only prompt, so the comparison stays fair.
- **Results are evidence.** Files tagged `_full` (all 50 documents) feed the reports and are committed.
  Golden-only or subset runs get another tag and are never written as `_full`. `--unconstrained` runs are a
  demonstration of the repair path, not a production setting. Result records contain no raw model text except
  the first invalid answer of a repaired/failed document (`extra.first_answer`).
- **Scoring rules are fixed.** `src/medassist/scoring.py` matching rules were set before model outputs were
  inspected. Do not loosen them to make a run look better; note scorer limitations in the report instead.
- **Golden labels follow the protocol** in `data/README.md`: the raw text wins over the seed; every edit is
  logged in `data/golden/STATUS.md`.
- **Dataset is synthetic** (Claude Opus 5.5 from deterministic seeds). Regenerating documents means
  re-running `verify_clean.py`, `add_noise.py` and re-checking the golden labels.
- **Secrets.** Only `.env.example` is committed. Never print or paste the API key.
- **Git.** Commit and push only when asked. This repository is nested inside a larger folder; run git from
  this directory.
- **Environment.** Use the project `.venv` (`uv run` or `.venv/bin/python`). Do not kill other processes on
  the machine (the user runs unrelated `uvx` services).

## Current state (2026-10-28)

Course steps 1–4 done: both prompt versions run on all documents for all four configurations, repair policy
implemented and demonstrated, `REPORT.md` has the comparison table, error analysis and production decision
(Haiku 5.5, low effort, prompt v2). Open: human verification pass of the golden labels; two label-vs-rule
conventions (documents 016 and 035) to decide before prompt v3; v3 proposals are in
`results/report-prompt-v1-vs-v2.html`.
