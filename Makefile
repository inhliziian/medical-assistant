.PHONY: install run quick report score test clean

PY ?= $(shell command -v uv >/dev/null 2>&1 && echo "uv run python" || echo "python3")

install:            ## install dependencies (uv if available, else pip)
	@if command -v uv >/dev/null 2>&1; then uv sync; else pip install -r requirements.txt; fi
	@test -f .env || (cp .env.example .env && echo "created .env — add your ANTHROPIC_API_KEY")

run:                ## prompt v1, all configs, all documents, then REPORT.md and the HTML report in results/
	$(PY) main.py

quick:              ## golden documents only (fast smoke run)
	$(PY) main.py --quick

report:             ## rebuild REPORT.md and results/report-checkpoint-1.html from existing results
	$(PY) main.py --skip-run

score:              ## print the metrics table for all full runs
	$(PY) scripts/score.py --fields results/*_full.jsonl

test:               ## offline checks: schema strictness, scorer rules, dataset facts
	$(PY) scripts/verify_clean.py raw
	$(PY) -c "from medassist.schema import strict_json_schema as s; print('schema ok,', len(s()['properties']), 'fields')"

clean:
	rm -rf .venv __pycache__ src/medassist/__pycache__ src/medassist/providers/__pycache__ schema/__pycache__
