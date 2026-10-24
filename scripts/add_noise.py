"""Deterministic noise pass: data/clean/{id}.txt -> data/raw/{id}.txt according to seed.dirt.

Facts are protected: typos never touch tokens that carry digits, and never touch medication names,
lab names or diagnosis words listed in the seed (so golden labels stay valid). Truncation and sentence
drops are only enabled by make_seeds.py for non-golden items.

Usage: python -I scripts/add_noise.py [--seed 7]
"""
from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEEDS = ROOT / "data" / "seeds" / "seeds.json"
CLEAN = ROOT / "data" / "clean"
RAW = ROOT / "data" / "raw"

# Typo operations that keep a word recognisable: swap two adjacent letters, drop a letter,
# double a letter, or a common keyboard neighbour substitution.
NEIGHBOURS = {"a": "s", "s": "d", "d": "f", "e": "r", "r": "t", "i": "o", "o": "p", "n": "m", "m": "n",
              "а": "п", "о": "л", "е": "н", "и": "т", "н": "г", "т": "ь", "с": "ч", "в": "а"}


def protected_tokens(seed: dict) -> set[str]:
    f = seed["facts"]
    words: set[str] = set()
    for m in f["medications"]:
        words.update(re.findall(r"[^\W\d_]+", m["name"].lower()))
    for l in f["lab_values"]:
        words.update(re.findall(r"[^\W\d_]+", l["name"].lower()))
    for d in f["diagnoses"]:
        words.update(re.findall(r"[^\W\d_]+", d.lower()))
    return {w for w in words if len(w) > 3}


def typo(word: str, rng: random.Random) -> str:
    if len(word) < 5:
        return word
    op = rng.choice(["swap", "drop", "double", "neighbour"])
    i = rng.randrange(1, len(word) - 2)
    if op == "swap":
        return word[:i] + word[i + 1] + word[i] + word[i + 2:]
    if op == "drop":
        return word[:i] + word[i + 1:]
    if op == "double":
        return word[:i] + word[i] + word[i:]
    ch = word[i].lower()
    if ch in NEIGHBOURS:
        rep = NEIGHBOURS[ch]
        return word[:i] + (rep.upper() if word[i].isupper() else rep) + word[i + 1:]
    return word[:i] + word[i + 1] + word[i] + word[i + 2:]


def apply_typos(text: str, n: int, protected: set[str], rng: random.Random) -> str:
    tokens = re.split(r"(\s+)", text)
    candidates = [k for k, t in enumerate(tokens)
                  if t.strip() and not re.search(r"\d", t) and len(re.sub(r"\W", "", t)) >= 5
                  and re.sub(r"\W", "", t).lower() not in protected and ":" not in t]
    rng.shuffle(candidates)
    for k in candidates[:n]:
        core = re.sub(r"\W", "", tokens[k])
        tokens[k] = tokens[k].replace(core, typo(core, rng), 1)
    return "".join(tokens)


def decimal_comma(text: str, rng: random.Random) -> str:
    # Turn some "6.8" into "6,8" (not all, to mimic inconsistent typing).
    def rep(m):
        return m.group(0).replace(".", ",") if rng.random() < 0.7 else m.group(0)
    return re.sub(r"(?<!\d)\d{1,3}\.\d{1,2}(?!\d)", rep, text)


def mangle_headers(text: str, rng: random.Random) -> str:
    # mtsamples-style scraping artefacts around headers: "PLAN:,  " and lost newlines before headers.
    def rep(m):
        choice = rng.random()
        if choice < 0.4:
            return f"{m.group(1)}:, "
        if choice < 0.7:
            return f"{m.group(1)}: ,"
        return f"{m.group(1).lower()}:"
    return re.sub(r"^([A-ZА-ЯІЇЄ][A-ZА-ЯІЇЄ /'\-]{2,40}):", rep, text, flags=re.M)


def case_noise(text: str, rng: random.Random) -> str:
    lines = text.split("\n")
    k = rng.randrange(len(lines))
    if rng.random() < 0.5:
        lines[k] = lines[k].upper()
    else:
        lines[k] = lines[k].lower()
    return "\n".join(lines)


def whitespace_noise(text: str, rng: random.Random) -> str:
    text = re.sub(r"\n\n", lambda m: "\n" if rng.random() < 0.5 else "\n\n\n", text)
    text = re.sub(r" ,", ",", text)
    text = re.sub(r", ", lambda m: "," if rng.random() < 0.3 else ", ", text)
    text = re.sub(r"(\w)\.\s+(\w)", lambda m: f"{m.group(1)}.{m.group(2)}" if rng.random() < 0.15 else m.group(0), text)
    return text


def drop_sentence(text: str, protected_digits: list[str], rng: random.Random) -> str:
    sents = re.split(r"(?<=[.!?])\s+", text)
    if len(sents) < 4:
        return text
    safe = [i for i, s in enumerate(sents) if not any(d in s for d in protected_digits) and not re.search(r"\d", s)]
    if not safe:
        return text
    del sents[rng.choice(safe)]
    return " ".join(sents)


def truncate_tail(text: str, protected_digits: list[str], rng: random.Random) -> str:
    """Cut the last paragraph(s) like a dictation that stopped early. Keeps at least 65% of the words
    and never removes a protected number (lab value, dose, age)."""
    paras = [p for p in text.rstrip().split("\n") if p.strip()]
    if len(paras) < 4:
        return text
    total = sum(len(p.split()) for p in paras)
    options = []
    for cut in range(2, len(paras)):
        kept = paras[:cut]
        tail = "\n".join(paras[cut:])
        if sum(len(p.split()) for p in kept) >= 0.65 * total and not any(d in tail for d in protected_digits):
            options.append(cut)
    if not options:
        return text
    cut = rng.choice(options)
    return "\n".join(paras[:cut]).rstrip() + ("" if rng.random() < 0.5 else " [...]") + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    seeds = json.loads(SEEDS.read_text(encoding="utf-8"))
    done = 0
    for s in seeds:
        src = CLEAN / f"{s['id']}.txt"
        if not src.exists():
            print(f"skip {s['id']}: no clean text")
            continue
        rng = random.Random(f"{args.seed}-{s['id']}")
        text = src.read_text(encoding="utf-8").strip() + "\n"
        prot = protected_tokens(s)
        digits = [str(l["value"]) for l in s["facts"]["lab_values"]] + \
                 [m["dose"] for m in s["facts"]["medications"] if m["dose"]] + \
                 ([str(s["facts"]["patient_age"])] if s["facts"]["patient_age"] is not None else [])
        d = s["dirt"]
        if d["drop_sentence"]:
            text = drop_sentence(text, digits, rng)
        if d["truncate_tail"]:
            text = truncate_tail(text, digits, rng)
        text = apply_typos(text, d["typos"], prot, rng)
        if d["decimal_comma"]:
            text = decimal_comma(text, rng)
        if d["mangle_headers"]:
            text = mangle_headers(text, rng)
        if d["case_noise"]:
            text = case_noise(text, rng)
        if d["whitespace_noise"]:
            text = whitespace_noise(text, rng)
        (RAW / f"{s['id']}.txt").write_text(text.rstrip() + "\n", encoding="utf-8")
        done += 1
    print(f"noised {done} documents -> data/raw/")


if __name__ == "__main__":
    main()
