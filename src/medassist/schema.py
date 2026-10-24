"""Target schema for the extraction task (single source of truth).

8 top-level fields: 3 enums (patient_sex, report_type, urgency), 2 nested lists of objects
(lab_values, medications), nullable scalars where the source text may be silent.
`strict_json_schema()` returns the JSON Schema in the shape both providers accept.
"""
from __future__ import annotations

import copy
from typing import Any, Literal

from pydantic import BaseModel, Field

Frequency = Literal["1x/day", "2x/day", "3x/day", "4x/day", "weekly", "as needed"]
ReportType = Literal["consult", "progress_note", "discharge", "referral", "lab", "radiology"]
Urgency = Literal["routine", "soon", "urgent"]
Sex = Literal["male", "female", "unknown"]


class LabValue(BaseModel):
    name: str = Field(description="Canonical English analyte name, e.g. 'potassium', 'HbA1c', 'CRP'")
    value: float = Field(description="Numeric value; a decimal comma in the source becomes a decimal point")
    unit: str | None = Field(description="Unit exactly as stated in the text, null if the text gives none")


class Medication(BaseModel):
    name: str = Field(description="Generic or brand name as written, lowercase")
    dose: str | None = Field(description="Dose with unit, e.g. '500 mg'; null if not stated")
    frequency: Frequency | None = Field(description="Normalised frequency; null if not stated")


class Report(BaseModel):
    patient_age: int | None = Field(description="Age in years; null if the text does not state it. Never guess.")
    patient_sex: Sex
    report_type: ReportType
    diagnoses: list[str] = Field(description="English, lowercase, one entry per condition")
    lab_values: list[LabValue]
    medications: list[Medication]
    urgency: Urgency = Field(description="urgent = same day, soon = days to 2 weeks, routine = scheduled follow-up or none")
    follow_up_required: bool


def strict_json_schema(model: type[BaseModel] = Report) -> dict[str, Any]:
    """Pydantic JSON Schema with `additionalProperties: false` and a full `required` list on every
    object, which structured-output endpoints demand. Same schema is sent to every provider."""
    schema = copy.deepcopy(model.model_json_schema())

    def harden(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
            for v in node.values():
                harden(v)
        elif isinstance(node, list):
            for v in node:
                harden(v)

    harden(schema)
    return schema
