"""Write golden-label drafts for the seeds marked golden: data/golden/{id}.json.

The draft is the seed's facts, validated against schema/report_schema.py. It is a DRAFT until a human
reads data/raw/{id}.txt side by side and confirms it; data/golden/STATUS.md tracks that.

Usage: python -I scripts/make_golden.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from medassist.schema import Report  # noqa: E402

SEEDS = ROOT / "data" / "seeds" / "seeds.json"
GOLD = ROOT / "data" / "golden"


def main():
    GOLD.mkdir(parents=True, exist_ok=True)
    seeds = json.loads(SEEDS.read_text(encoding="utf-8"))
    rows = []
    for s in seeds:
        if not s["golden"]:
            continue
        report = Report.model_validate(s["facts"])  # raises if the seed violates the schema
        (GOLD / f"{s['id']}.json").write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
        f = s["facts"]
        rows.append((s["id"], f["report_type"], s["hints"]["language"], s["hints"]["length"],
                     "null" if f["patient_age"] is None else str(f["patient_age"]), f["patient_sex"],
                     len(f["medications"]), len(f["lab_values"]), f["urgency"]))
    status = ["# Golden set status", "",
              "Each row is a golden item. `verified` is flipped to yes by a human after reading",
              "`data/raw/{id}.txt` next to `data/golden/{id}.json` and correcting the JSON if needed.", "",
              "| id | type | lang | length | age | sex | meds | labs | urgency | verified |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        status.append("| " + " | ".join(str(x) for x in r) + " | no |")
    (GOLD / "STATUS.md").write_text("\n".join(status) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} golden drafts -> data/golden/ (see STATUS.md)")


if __name__ == "__main__":
    main()
