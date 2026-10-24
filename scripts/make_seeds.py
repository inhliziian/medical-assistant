"""Generate 50 deterministic seeds for synthetic medical reports.

Each seed = the ground-truth facts (a Report object) + generation hints (language, style,
length, specialty) + a dirt plan for scripts/add_noise.py. The facts of golden items must
survive the noise pass, so golden items never get truncation or sentence drops.

Usage: python -I scripts/make_seeds.py  -> data/seeds/seeds.json
"""
from __future__ import annotations

import json
import random
from pathlib import Path

random.seed(20261018)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "seeds" / "seeds.json"

# Coherent clinical bundles: condition -> typical meds and labs. Values are plausible, some abnormal.
BUNDLES = [
    {"dx": "essential hypertension", "meds": [("amlodipine", "5 mg", "1x/day"), ("lisinopril", "10 mg", "1x/day")],
     "labs": [("creatinine", 92, "umol/L"), ("potassium", 4.4, "mmol/L")], "spec": "general medicine"},
    {"dx": "type 2 diabetes mellitus", "meds": [("metformin", "500 mg", "2x/day"), ("empagliflozin", "10 mg", "1x/day")],
     "labs": [("HbA1c", 7.9, "%"), ("fasting glucose", 8.6, "mmol/L")], "spec": "endocrinology"},
    {"dx": "chronic kidney disease stage 3", "meds": [("lisinopril", "10 mg", None)],
     "labs": [("creatinine", 180, "umol/L"), ("eGFR", 38, "mL/min"), ("potassium", 5.6, "mmol/L")], "spec": "nephrology"},
    {"dx": "hyperkalemia", "meds": [], "labs": [("potassium", 6.8, "mmol/L")], "spec": "nephrology", "urgent": True},
    {"dx": "community-acquired pneumonia", "meds": [("amoxicillin-clavulanate", "875/125 mg", "2x/day")],
     "labs": [("CRP", 12, None), ("white blood cells", 11.2, "10^9/L")], "spec": "internal medicine"},
    {"dx": "hypothyroidism", "meds": [("levothyroxine", "75 mcg", "1x/day")],
     "labs": [("TSH", 6.8, "mIU/L")], "spec": "endocrinology"},
    {"dx": "asthma", "meds": [("salbutamol", "100 mcg", "as needed"), ("budesonide", "200 mcg", "2x/day")],
     "labs": [], "spec": "pulmonology"},
    {"dx": "atrial fibrillation", "meds": [("apixaban", "5 mg", "2x/day"), ("bisoprolol", "2.5 mg", "1x/day")],
     "labs": [("INR", 1.1, None)], "spec": "cardiology"},
    {"dx": "gastroesophageal reflux disease", "meds": [("omeprazole", "20 mg", "1x/day")], "labs": [], "spec": "gastroenterology"},
    {"dx": "urinary tract infection", "meds": [("nitrofurantoin", "100 mg", "2x/day")],
     "labs": [("urine leukocytes", 500, "/uL")], "spec": "general medicine", "soon": True},
    {"dx": "iron deficiency anemia", "meds": [("ferrous sulfate", "325 mg", "1x/day")],
     "labs": [("hemoglobin", 9.8, "g/dL"), ("ferritin", 8, "ng/mL")], "spec": "hematology"},
    {"dx": "major depressive disorder", "meds": [("sertraline", "50 mg", "1x/day")], "labs": [], "spec": "psychiatry"},
    {"dx": "knee osteoarthritis", "meds": [("ibuprofen", "400 mg", "as needed")], "labs": [], "spec": "orthopedics"},
    {"dx": "migraine without aura", "meds": [("sumatriptan", "50 mg", "as needed")], "labs": [], "spec": "neurology"},
    {"dx": "heart failure with reduced ejection fraction", "meds": [("furosemide", "40 mg", "1x/day"), ("carvedilol", "6.25 mg", "2x/day")],
     "labs": [("BNP", 890, "pg/mL"), ("sodium", 134, "mmol/L")], "spec": "cardiology", "soon": True},
    {"dx": "hyperlipidemia", "meds": [("atorvastatin", "20 mg", "1x/day")],
     "labs": [("LDL cholesterol", 4.1, "mmol/L")], "spec": "general medicine"},
    {"dx": "gout", "meds": [("allopurinol", "100 mg", "1x/day")], "labs": [("uric acid", 520, "umol/L")], "spec": "rheumatology"},
    {"dx": "lumbar radiculopathy", "meds": [("naproxen", "500 mg", "2x/day")], "labs": [], "spec": "neurology"},
    {"dx": "acute otitis media", "meds": [("amoxicillin", "250 mg", "3x/day")], "labs": [], "spec": "pediatrics", "child": True},
    {"dx": "atopic dermatitis", "meds": [("hydrocortisone 1% cream", None, "2x/day")], "labs": [], "spec": "dermatology"},
    {"dx": "chronic obstructive pulmonary disease", "meds": [("tiotropium", "18 mcg", "1x/day")],
     "labs": [], "spec": "pulmonology"},
    {"dx": "vitamin D deficiency", "meds": [("cholecalciferol", "2000 IU", "1x/day")],
     "labs": [("25-OH vitamin D", 14, "ng/mL")], "spec": "general medicine"},
    {"dx": "acute appendicitis", "meds": [], "labs": [("white blood cells", 15.4, "10^9/L"), ("CRP", 86, "mg/L")],
     "spec": "surgery", "urgent": True},
    {"dx": "deep vein thrombosis", "meds": [("rivaroxaban", "15 mg", "2x/day")],
     "labs": [("D-dimer", 2.4, "mg/L")], "spec": "vascular medicine", "urgent": True},
    {"dx": "elevated liver enzymes", "meds": [], "labs": [("ALT", 128, "U/L"), ("AST", 96, "U/L")], "spec": "gastroenterology", "soon": True},
    {"dx": "allergic rhinitis", "meds": [("cetirizine", "10 mg", "1x/day")], "labs": [], "spec": "allergy"},
    {"dx": "osteoporosis", "meds": [("alendronate", "70 mg", "weekly")], "labs": [], "spec": "endocrinology"},
    {"dx": "benign prostatic hyperplasia", "meds": [("tamsulosin", "0.4 mg", "1x/day")], "labs": [("PSA", 2.1, "ng/mL")], "spec": "urology", "sex": "male"},
]

RADIOLOGY_FINDINGS = [
    ("possible right lower lobe opacity", "chest x-ray"),
    ("no acute intracranial abnormality", "CT head"),
    ("L4-L5 disc protrusion", "MRI lumbar spine"),
    ("medial meniscus tear", "MRI knee"),
    ("simple renal cyst", "ultrasound abdomen"),
    ("cholelithiasis without cholecystitis", "ultrasound abdomen"),
]

REPORT_TYPES = (["consult"] * 12 + ["progress_note"] * 10 + ["discharge"] * 10 +
                ["referral"] * 6 + ["lab"] * 6 + ["radiology"] * 6)
LANGUAGES = ["en"] * 30 + ["uk"] * 10 + ["mixed"] * 10
LENGTHS = ["short"] * 12 + ["medium"] * 26 + ["long"] * 12
STYLES = ["soap", "narrative", "dictation", "bullet"]
random.shuffle(REPORT_TYPES); random.shuffle(LANGUAGES); random.shuffle(LENGTHS)

seeds = []
for i in range(50):
    sid = f"{i+1:03d}"
    rtype = REPORT_TYPES[i]
    lang = LANGUAGES[i]
    length = LENGTHS[i]
    style = random.choice(STYLES) if rtype in ("consult", "progress_note") else random.choice(["narrative", "dictation"])

    n_bundles = {"short": 1, "medium": random.choice([1, 2]), "long": random.choice([2, 3])}[length]
    bundles = random.sample(BUNDLES, n_bundles)
    child = any(b.get("child") for b in bundles)

    diagnoses = [b["dx"] for b in bundles]
    meds, labs = [], []
    for b in bundles:
        for name, dose, freq in b["meds"]:
            # randomly withhold dose/frequency so the text is silent -> null in golden
            d = dose if random.random() > 0.2 else None
            f = freq if random.random() > 0.25 else None
            meds.append({"name": name, "dose": d, "frequency": f})
        if rtype in ("lab", "consult", "discharge", "progress_note"):
            for name, value, unit in b["labs"]:
                u = unit if random.random() > 0.2 else None
                labs.append({"name": name, "value": value, "unit": u})
    if rtype == "radiology":
        finding, modality = random.choice(RADIOLOGY_FINDINGS)
        diagnoses = [finding]
        meds, labs = [], []
    if rtype == "referral":
        labs = labs[:1]
        meds = meds[:2]
    if rtype == "lab" and not labs:
        labs = [{"name": "hemoglobin", "value": 13.4, "unit": "g/dL"}]

    age = None if random.random() < 0.3 else (random.randint(1, 12) if child else random.randint(19, 84))
    sex = "unknown" if random.random() < 0.15 else random.choice(["male", "female"])
    # sex-specific conditions override the random draw (no extra random calls, so other seeds are unchanged)
    forced = [b["sex"] for b in bundles if b.get("sex")]
    if forced and sex != "unknown":
        sex = forced[0]

    if any(b.get("urgent") for b in bundles):
        urgency = "urgent"
    elif any(b.get("soon") for b in bundles):
        urgency = "soon"
    else:
        urgency = random.choices(["routine", "soon", "urgent"], weights=[75, 18, 7])[0]
    follow_up = True if urgency != "routine" else random.random() < 0.6

    facts = {
        "patient_age": age, "patient_sex": sex, "report_type": rtype, "diagnoses": diagnoses,
        "lab_values": labs, "medications": meds, "urgency": urgency, "follow_up_required": follow_up,
    }
    hints = {
        "language": lang, "style": style, "length": length,
        "target_words": {"short": random.randint(45, 90), "medium": random.randint(120, 220), "long": random.randint(260, 420)}[length],
        "specialty": bundles[0]["spec"] if rtype != "radiology" else "radiology",
        "modality": modality if rtype == "radiology" else None,
        "distractors": random.sample(["allergies", "family history", "social history", "vitals", "physical exam", "plan details", "review of systems"], 2),
    }
    seeds.append({"id": sid, "facts": facts, "hints": hints, "dirt": None, "golden": False})

# Golden selection: 10 items covering every report type, every language, several dirt kinds, nulls.
def pick_golden(seeds):
    chosen, used_types, used_langs = [], set(), set()
    order = sorted(seeds, key=lambda s: (s["facts"]["report_type"], s["hints"]["language"]))
    # first pass: one per report type with preference for non-English and null age
    for s in sorted(order, key=lambda s: (s["hints"]["language"] == "en", s["facts"]["patient_age"] is not None)):
        t = s["facts"]["report_type"]
        if t not in used_types:
            chosen.append(s); used_types.add(t); used_langs.add(s["hints"]["language"])
        if len(chosen) == 6: break
    # second pass: fill to 10 with variety of language and length
    for s in sorted(order, key=lambda s: (s["hints"]["language"] in used_langs, s["hints"]["length"] != "long")):
        if s in chosen: continue
        chosen.append(s); used_langs.add(s["hints"]["language"])
        if len(chosen) == 10: break
    return chosen

for s in pick_golden(seeds):
    s["golden"] = True

# Dirt plan: typos and formatting never destroy facts; truncation / sentence drops only on non-golden items.
for s in seeds:
    g = s["golden"]
    s["dirt"] = {
        "typos": random.choice([2, 3, 4, 5]),
        "decimal_comma": bool(s["facts"]["lab_values"]) and random.random() < 0.6,
        "mangle_headers": random.random() < 0.5,
        "case_noise": random.random() < 0.3,
        "whitespace_noise": random.random() < 0.5,
        "drop_sentence": (not g) and random.random() < 0.35,
        "truncate_tail": (not g) and random.random() < 0.2,
    }

OUT.write_text(json.dumps(seeds, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
g = [s for s in seeds if s["golden"]]
print(f"wrote {len(seeds)} seeds -> {OUT.relative_to(ROOT)}")
print("golden:", ", ".join(f'{s["id"]}({s["facts"]["report_type"]}/{s["hints"]["language"]})' for s in g))
from collections import Counter
print("types:", dict(Counter(s["facts"]["report_type"] for s in seeds)))
print("langs:", dict(Counter(s["hints"]["language"] for s in seeds)))
print("null age:", sum(s["facts"]["patient_age"] is None for s in seeds), "| sex unknown:", sum(s["facts"]["patient_sex"]=="unknown" for s in seeds))
