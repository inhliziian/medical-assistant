"""Field-level comparison of a model output with a golden label.

Matching rules (fixed before any model output was inspected; mirrored in data/README.md):
- enums and booleans: exact
- patient_age: exact, or both null
- strings: case-insensitive, hyphens as spaces, punctuation and extra whitespace removed
- lists: compared as sets, order ignored
- lab_values: set of (name, value, unit); names pass through a small alias table (hb -> hemoglobin ...)
- medications: set of (name, dose, frequency); doses compared with spaces removed ("500 mg" == "500mg")
Per-field accuracy for a document = matched fields / 8. The scorer never looks at the raw text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

FIELDS = ["patient_age", "patient_sex", "report_type", "diagnoses", "lab_values", "medications",
          "urgency", "follow_up_required"]

LAB_ALIASES = {
    "hb": "hemoglobin", "hgb": "hemoglobin", "haemoglobin": "hemoglobin",
    "k": "potassium", "na": "sodium", "cr": "creatinine", "crea": "creatinine",
    "wbc": "white blood cells", "leukocytes": "white blood cells", "white cell count": "white blood cells",
    "white blood cell count": "white blood cells", "white blood cell": "white blood cells", "wbc count": "white blood cells",
    "glucose": "fasting glucose", "blood glucose": "fasting glucose", "fasting plasma glucose": "fasting glucose",
    "hba1c": "hba1c", "glycated hemoglobin": "hba1c",
    "c reactive protein": "crp", "c-reactive protein": "crp",
    "ldl": "ldl cholesterol", "ldl c": "ldl cholesterol",
    "vitamin d": "25-oh vitamin d", "25 oh vitamin d": "25-oh vitamin d", "25 hydroxyvitamin d": "25-oh vitamin d",
    "egfr": "egfr", "gfr": "egfr",
    "d dimer": "d-dimer",
}


def norm_str(s: Any) -> str:
    if s is None:
        return ""
    s = str(s).lower().strip().replace("-", " ").replace("_", " ")
    s = re.sub(r"[^\w\s/.%]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_lab_name(s: Any) -> str:
    n = norm_str(s)
    n2 = n.replace(" ", "-") if n in ("d dimer", "25 oh vitamin d") else n
    return LAB_ALIASES.get(n, LAB_ALIASES.get(n2, n))


def norm_dose(s: Any) -> str:
    return norm_str(s).replace(" ", "") if s is not None else ""


def norm_unit(s: Any) -> str:
    return norm_str(s).replace(" ", "").replace("µ", "u").replace("μ", "u") if s is not None else ""


def norm_value(v: Any) -> str:
    try:
        f = float(str(v).replace(",", "."))
        return f"{f:.3f}".rstrip("0").rstrip(".")
    except Exception:
        return norm_str(v)


def lab_key(l: dict) -> tuple:
    return (norm_lab_name(l.get("name")), norm_value(l.get("value")), norm_unit(l.get("unit")))


def med_key(m: dict) -> tuple:
    return (norm_str(m.get("name")), norm_dose(m.get("dose")), norm_str(m.get("frequency")))


@dataclass
class FieldResult:
    field: str
    match: bool
    golden: Any
    predicted: Any
    note: str = ""


@dataclass
class DocScore:
    doc_id: str
    fields: list[FieldResult] = field(default_factory=list)

    @property
    def matched(self) -> int:
        return sum(f.match for f in self.fields)

    @property
    def accuracy(self) -> float:
        return self.matched / len(self.fields) if self.fields else 0.0


def _set_compare(golden: list, pred: list, keyf) -> tuple[bool, str]:
    g = {keyf(x) if isinstance(x, dict) else norm_str(x) for x in (golden or [])}
    p = {keyf(x) if isinstance(x, dict) else norm_str(x) for x in (pred or [])}
    if g == p:
        return True, ""
    missing, extra = g - p, p - g
    parts = []
    if missing:
        parts.append("missing: " + "; ".join(" | ".join(map(str, k)) if isinstance(k, tuple) else k for k in sorted(missing)))
    if extra:
        parts.append("extra: " + "; ".join(" | ".join(map(str, k)) if isinstance(k, tuple) else k for k in sorted(extra)))
    return False, "  ".join(parts)


def score_document(doc_id: str, golden: dict, predicted: dict | None) -> DocScore:
    ds = DocScore(doc_id)
    if predicted is None:
        for f in FIELDS:
            ds.fields.append(FieldResult(f, False, golden.get(f), None, "no valid output"))
        return ds
    for f in FIELDS:
        g, p = golden.get(f), predicted.get(f)
        if f == "patient_age":
            ok = (g is None and p is None) or (g is not None and p is not None and int(g) == int(p))
            ds.fields.append(FieldResult(f, ok, g, p, "" if ok else ("invented" if g is None else "wrong/missing")))
        elif f in ("patient_sex", "report_type", "urgency", "follow_up_required"):
            ds.fields.append(FieldResult(f, g == p, g, p))
        elif f == "diagnoses":
            ok, note = _set_compare(g, p, norm_str)
            ds.fields.append(FieldResult(f, ok, g, p, note))
        elif f == "lab_values":
            ok, note = _set_compare(g, p, lab_key)
            ds.fields.append(FieldResult(f, ok, g, p, note))
        elif f == "medications":
            ok, note = _set_compare(g, p, med_key)
            ds.fields.append(FieldResult(f, ok, g, p, note))
    return ds


def fmt_value(v: Any) -> str:
    if isinstance(v, list):
        if not v:
            return "[]"
        if isinstance(v[0], dict):
            return "; ".join(" ".join(str(x) for x in d.values() if x is not None) for d in v)
        return ", ".join(map(str, v))
    return "null" if v is None else str(v)


def render_table(ds: DocScore) -> str:
    rows = [f"{'field':<20} {'ok':<4} {'golden':<48} predicted"]
    for fr in ds.fields:
        mark = "yes" if fr.match else "NO"
        rows.append(f"{fr.field:<20} {mark:<4} {fmt_value(fr.golden)[:48]:<48} {fmt_value(fr.predicted)[:60]}")
        if fr.note and not fr.match:
            rows.append(f"{'':<25}-> {fr.note}")
    rows.append(f"{'per-field accuracy':<20} {ds.matched}/{len(ds.fields)} = {ds.accuracy:.0%}")
    return "\n".join(rows)
