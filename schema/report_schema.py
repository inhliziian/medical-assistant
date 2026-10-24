"""Thin re-export so the schema is also visible at the project root (course deliverable).
The model lives in src/medassist/schema.py. Running this file regenerates report.schema.json."""
from __future__ import annotations

import json

from medassist.schema import Frequency, LabValue, Medication, Report, ReportType, Sex, Urgency, strict_json_schema  # noqa: F401

if __name__ == "__main__":
    print(json.dumps(strict_json_schema(), indent=2, ensure_ascii=False))
