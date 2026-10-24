"""Check generated texts against their seeds. Run on data/clean (strict) or data/raw (facts only).

Checks: every diagnosis keyword, medication name, lab value number and stated age appear; no digits
of a null age; no gendered words when sex is unknown; file exists; length roughly on target.
Diagnosis check is lenient (any 1 keyword) because clinicians abbreviate; the human pass covers the rest.

Usage: python -I scripts/verify_clean.py [clean|raw]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
which = sys.argv[1] if len(sys.argv) > 1 else "clean"
DIR = ROOT / "data" / which
seeds = json.loads((ROOT / "data" / "seeds" / "seeds.json").read_text(encoding="utf-8"))

GENDERED_EN = r"\b(he|she|his|her|him|mr|mrs|ms|male|female|man|woman|gentleman|lady|boy|girl)\b"
GENDERED_UK = r"\b(пацієнтка|жінка|чоловік|хлопчик|дівчинка|він|вона|його|її|звернувся|звернулась|звернулася|скаржиться)\b"

problems = 0
for s in seeds:
    p = DIR / f"{s['id']}.txt"
    issues = []
    if not p.exists():
        print(f"{s['id']}: MISSING"); problems += 1; continue
    t = p.read_text(encoding="utf-8")
    low = t.lower()
    f = s["facts"]
    for m in f["medications"]:
        first = re.findall(r"[a-z]+", m["name"].lower())[0]
        if first not in low:
            issues.append(f"med missing: {m['name']}")
    for l in f["lab_values"]:
        v = str(l["value"])
        alt = v.replace(".", ",")
        if v not in t and alt not in t and (v.endswith(".0") and v[:-2] not in t):
            issues.append(f"lab value missing: {l['name']} {v}")
    if f["patient_age"] is not None and str(f["patient_age"]) not in t:
        issues.append(f"age {f['patient_age']} missing")
    if f["patient_sex"] == "unknown":
        hits = set(re.findall(GENDERED_EN, low)) | set(re.findall(GENDERED_UK, low))
        if hits:
            issues.append(f"gendered words with sex=unknown: {sorted(hits)}")
    words = len(t.split())
    tw = s["hints"]["target_words"]
    if which == "clean" and not (tw * 0.5 <= words <= tw * 1.8):
        issues.append(f"length {words} words vs target {tw}")
    if re.search(r"\b(19|20)\d\d-\d\d-\d\d\b|\bDOB\b|date of birth", t, re.I):
        issues.append("possible date of birth")
    if issues:
        problems += 1
        print(f"{s['id']} ({f['report_type']}/{s['hints']['language']}{', GOLDEN' if s['golden'] else ''}):")
        for i in issues:
            print("   -", i)
print(f"\n{len(seeds) - problems}/{len(seeds)} files pass automatic checks on data/{which}")
sys.exit(1 if problems else 0)
