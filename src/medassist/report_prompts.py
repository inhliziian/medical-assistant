"""Prompt comparison page: what prompt v2 changed against v1, measured on the golden set and the full dataset.

  uv run python scripts/report_prompts.py            # results/*_full.json -> results/report-prompt-v1-vs-v2.html
  (also rebuilt by `python main.py` after a full run and by `python main.py --skip-run`)

Reads every results/*_full.json (prompt versions 1 and 2, all configurations), the unconstrained demo files
(results/*_golden_unconstrained.json, task 3 evidence) and the prompt files. Hand-written interpretation of
the remaining errors and the v3 proposals live in NOTES / V3 at the top of this file."""
from __future__ import annotations

import html
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

from .metrics import load_rows, run_metrics
from .scoring import FIELDS, fmt_value

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "results" / "report-prompt-v1-vs-v2.html"

E = html.escape
CONFIG_ORDER = ["haiku_low", "haiku_high", "qwen_t0", "qwen_t07"]
FIELD_SHORT = {"patient_age": "age", "patient_sex": "sex", "report_type": "type", "diagnoses": "diagnoses",
               "lab_values": "labs", "medications": "meds", "urgency": "urgency", "follow_up_required": "follow-up"}

# Why a golden field is still wrong after v2 (doc, field) -> explanation. Written by hand from the result files.
NOTES: dict[tuple[str, str], str] = {
    ("016", "diagnoses"): (
        "The text says “routine admission bloods also showed elevated liver enzymes … the cause remains unclear”. "
        "The golden label lists it as a second diagnosis; prompt v2 rule 4 says “do not include findings that are not "
        "diagnoses”, so both Haiku settings now drop it. The prompt and the label disagree, and the label was written "
        "before the rule. Decide the convention (abnormal-finding diagnoses such as “elevated liver enzymes” or "
        "“hyperlipidemia” count when the document treats them as a problem to follow up) and state it in v3."),
    ("035", "diagnoses"): (
        "Golden says “L4-L5 disc protrusion”; v2 rule 4 says drop the level, so the models answer “disc protrusion” or "
        "“intervertebral disc protrusion”. Same kind of conflict: for spinal findings the level is part of the clinical "
        "name, and v3 should say so explicitly (“keep vertebral levels and the organ for disc, fracture and stenosis "
        "findings”) or the golden label should change. One rule fixes both models at once."),
    ("004", "medications"): (
        "Text: “naproxen 500 mg twice daily”. Qwen v2 wrote the dose as “50:00 mg”; v1 had it right. A decoding glitch "
        "of the 4B model, not a rule problem: the colon-separated digits look like a time. A dose pattern in the schema "
        "(number, optional slash number, unit) would turn this into a validation failure that the repair call fixes."),
    ("023", "medications"): (
        "“Continue amlodipine … as before” has no dose, so golden leaves dose null. Qwen fills dose with “once daily” "
        "although v2 rule 6 forbids a frequency in the dose field and the frequency field already says 1x/day. The "
        "4B model follows the rule when a dose exists and falls back to copying text when it does not. A worked "
        "example with a dose-less drug would show the expected null."),
    ("027", "medications"): (
        "Same pattern as 023: “sertraline once daily” lands in dose as well as in frequency. Everything else in the "
        "list is right, including the 875/125 mg combination dose."),
    ("032", "medications"): (
        "Naproxen appears twice (“taking naproxen twice daily with partial relief”, then “hold naproxen pending surgical "
        "decision”) but Qwen lists only atorvastatin, under v1 and v2. The hold instruction probably reads as “not a "
        "current drug”. Rule 6 says “takes, is prescribed or is told to continue”; v3 should add “or is told to hold”, "
        "since a held drug is still part of the record."),
    ("023", "urgency"): (
        "Follow-up “within 1 week” is the definition of soon in rule 7; Qwen answers urgent in v1 and v2, probably "
        "triggered by the symptom word “urgency” (urinary urgency) in the first line. The hosted model is not fooled. "
        "v3 could add: clinical symptoms named urgency/urgent are not a timing instruction."),
    ("027", "lab_values"): (
        "“CRP 12, white blood cells 11.2 10^9/L”: golden keeps CRP without a unit because none is written; Qwen copies "
        "the neighbouring unit onto CRP, despite rule 5 (“never add a unit”). The same error as in v1, so the written "
        "rule does not reach the 4B model here; an example with a unit-less value next to a unit-bearing one would."),
    ("016", "lab_values"): (
        "“AST was 96.” has no unit; Qwen adds “U/L” from the ALT value one clause earlier. Identical mechanism to the "
        "CRP case above. v1 got the whole list wrong for a different reason (potassium misread), so this is a partial "
        "improvement that still fails the field."),
    ("048", "lab_values"): (
        "Qwen writes the analyte as “25-O-H vitamin D” where the text says “25-OH vitamin D”; the value and unit are "
        "right. Under the fixed matching rules a hyphen inside the name is a mismatch. Arguably a scorer strictness "
        "issue (lab names could be compared without hyphens); the rules were fixed before the runs, so it stays a miss "
        "and is noted here instead of being patched away."),
    ("034", "diagnoses"): (
        "“asthma exacerbation” instead of “asthma”. Rule 4 names exactly this example; the 4B model still keeps the "
        "episode word. Haiku fixed it in v2. A candidate for the worked example in v3."),
    ("037", "diagnoses"): (
        "“osteoarthritis right knee” keeps laterality against rule 4. Haiku fixed the same item in v2; Qwen partially "
        "(the other two diagnoses are right now, v1 had all three wrong)."),
    ("037", "medications"): (
        "Ibuprofen is missing. It is the first item of the recommendations (“ibuprofen 400 mg, приймати після їжі”) at "
        "the end of a 500-word Ukrainian dictation with no line breaks; Qwen keeps the two drugs mentioned earlier and "
        "drops the new one. Recall on long unstructured text is the 4B model's weak spot; a final self-check (“every "
        "drug in the text is listed”) is the v3 candidate."),
    ("038", "diagnoses"): (
        "A v2 regression: v1 answered “gout”, v2 answers “gout, recurrent gout attacks”. The longer rule list made the "
        "model more exhaustive, and “recurrent gout attacks” reads to it as a second condition. Rule 4 says one entry "
        "per condition; a worked example is the fix."),
}

# Hand-written proposals for prompt v3, grounded in what v2 still gets wrong.
V3: list[dict[str, str]] = [
    {"title": "Settle the two convention conflicts the golden set exposed",
     "what": "Add to rule 4: keep vertebral levels for spine findings (“L4-L5 disc protrusion”), and count abnormal "
             "laboratory findings as diagnoses when the document lists them as a problem or orders follow-up for them "
             "(“elevated liver enzymes”). Re-check the golden labels against the final wording before measuring.",
     "why": "Both remaining Haiku misses (016, 035) are rule-vs-label disagreements, not extraction errors. Fixing the "
            "convention is worth 2 of 80 golden fields for every configuration.",
     "who": "both models"},
    {"title": "One worked example per hard field",
     "what": "Append a short input → output example for medications and for diagnoses (two or three lines of clinical "
             "text, the exact JSON fragment expected). Keep the example in English with one Ukrainian line.",
     "why": "Rules alone fixed most Haiku errors, but the 4B model still copies the text’s wording (“once daily” in dose, "
            "stage qualifiers in diagnoses). Small models follow a demonstrated pattern better than a described one.",
     "who": "mainly Qwen"},
    {"title": "Ukrainian lexicon for the three list fields",
     "what": "A compact table of frequent Ukrainian terms and abbreviations: dosing (“1 р/д”, “двічі на добу”, "
             "“за потреби”), common analytes (креатинін, калій, ШОЕ, гемоглобін), and diagnoses with their English "
             "name (ГХ, ХОЗЛ, ЦД 2 типу, ФП, протрузія диска).",
     "why": "Every Qwen miss that involved a Ukrainian document was a translation or normalisation miss; v2 only lists "
            "a handful of abbreviations.",
     "who": "mainly Qwen"},
    {"title": "Move field rules into the schema descriptions",
     "what": "Put the one-line rule for each field into the JSON Schema `description`, and tighten `unit` and `dose` with "
             "patterns (dose must look like `<number> <unit>`). The prompt keeps only the reasoning rules.",
     "why": "Both providers receive the schema with every request, so the rule travels with the field it governs. "
            "Patterns make a wrong dose a validation failure that the repair step can fix, instead of a silent "
            "accuracy miss.",
     "who": "both models"},
    {"title": "Final self-check list before answering",
     "what": "End the prompt with four checks the model runs on its own draft: every drug in the text is listed; no unit "
             "was added; dose and frequency are in separate fields; diagnoses are bare English names.",
     "why": "Cheap for the hosted model (a few hundred output tokens) and it targets the exact error classes seen in v1 "
            "and v2. Measure whether it helps the 4B model or only makes it slower.",
     "who": "both models, measure separately"},
    {"title": "Output discipline for free-form mode",
     "what": "First line of the answer must be `{`; no Markdown, no explanation. For Qwen add `/no_think` to the user "
             "turn as a belt-and-braces guard.",
     "why": "Only matters when constrained decoding is unavailable, but the unconstrained demo showed Haiku wraps JSON "
            "in code fences 7 times out of 10 and Qwen writes an essay every time. One line removes the repair calls.",
     "who": "both models, unconstrained mode"},
]


def pct(x: float) -> str:
    return "n/a" if x != x else f"{100 * x:.1f}%"


def sec(ms: float) -> str:
    return f"{ms / 1000:.1f} s"


def params_str(p: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in p.items() if k != "constrained") or "defaults"


def front_matter(version: str) -> tuple[str, str]:
    text = (ROOT / "prompts/extraction" / f"{version}.md").read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    return (m.group(1), m.group(2).strip()) if m else ("", text)


def load_runs(files: list[Path]) -> dict[tuple[str, str], dict]:
    """(config, prompt) -> metrics dict (with rows attached)."""
    out = {}
    for f in files:
        rows = load_rows(f)
        if not rows:
            continue
        m = run_metrics(rows)
        m["rows"], m["file"] = rows, f
        out[(m["config"], m["prompt"])] = m
    return out


def transitions(v1: dict, v2: dict) -> tuple[dict[str, int], list[dict]]:
    """Per golden field cell: kept / fixed / still / regressed, plus the cells that are not 'kept'."""
    counts = defaultdict(int)
    cells = []
    for doc in sorted(v1["scores"]):
        if doc not in v2["scores"]:
            continue
        a = {fr.field: fr for fr in v1["scores"][doc].fields}
        b = {fr.field: fr for fr in v2["scores"][doc].fields}
        for f in FIELDS:
            x, y = a[f].match, b[f].match
            kind = "kept" if x and y else "fixed" if (not x and y) else "regressed" if (x and not y) else "still"
            counts[kind] += 1
            if kind != "kept":
                cells.append({"doc": doc, "field": f, "kind": kind, "golden": fmt_value(a[f].golden),
                              "v1": fmt_value(a[f].predicted), "v2": fmt_value(b[f].predicted)})
    return counts, cells


# ----------------------------------------------------------------------------------------------- rendering

def paired_bars(pairs: list[tuple[str, float, float]]) -> str:
    """Horizontal paired bars, v1 (muted) and v2 (accent), 0–100%."""
    row_h, gap, left, width = 44, 14, 118, 720
    h = len(pairs) * (row_h + gap) + 30
    out = [f'<svg viewBox="0 0 {width + left + 70} {h}" role="img" aria-label="Golden field accuracy, prompt v1 and v2">']
    for i, t in enumerate((0, 0.25, 0.5, 0.75, 1.0)):
        x = left + t * width
        out.append(f'<line x1="{x:.0f}" y1="8" x2="{x:.0f}" y2="{h - 22}" class="grid"/>'
                   f'<text x="{x:.0f}" y="{h - 6}" class="tick" text-anchor="middle">{int(t * 100)}%</text>')
    for i, (name, a, b) in enumerate(pairs):
        y = 12 + i * (row_h + gap)
        out.append(f'<text x="{left - 10}" y="{y + row_h / 2 + 4}" class="lbl" text-anchor="end">{E(name)}</text>')
        for j, (v, cls) in enumerate(((a, "b1"), (b, "b2"))):
            if v != v:
                continue
            w = max(2, v * width)
            yy = y + j * (row_h / 2)
            out.append(f'<rect x="{left}" y="{yy:.0f}" width="{w:.1f}" height="{row_h / 2 - 2:.0f}" class="{cls}"/>'
                       f'<text x="{left + w + 6:.1f}" y="{yy + row_h / 4 + 4:.0f}" class="val">{"v" + str(j + 1)} {pct(v)}</text>')
    out.append("</svg>")
    return "\n".join(out)


def heat(v: float) -> str:
    if v != v:
        return '<td class="num muted">—</td>'
    tone = "h4" if v >= 0.999 else "h3" if v >= 0.9 else "h2" if v >= 0.7 else "h1"
    return f'<td class="num {tone}">{pct(v)}</td>'


def delta(a: float, b: float) -> str:
    if a != a or b != b:
        return '<span class="muted">—</span>'
    d = 100 * (b - a)
    cls = "up" if d > 0.05 else "down" if d < -0.05 else "muted"
    return f'<span class="{cls}">{d:+.1f}</span>'


def field_table(runs: dict, configs: list[str]) -> str:
    head = "".join(f"<th colspan='3'>{E(FIELD_SHORT[f])}</th>" for f in FIELDS)
    sub = "".join("<th class='sub'>v1</th><th class='sub'>v2</th><th class='sub'>Δ pp</th>" for _ in FIELDS)
    rows = []
    for c in configs:
        v1, v2 = runs.get((c, "1")), runs.get((c, "2"))
        if not v1 and not v2:
            continue
        cells = []
        for f in FIELDS:
            a = v1["per_field"][f] if v1 else float("nan")
            b = v2["per_field"][f] if v2 else float("nan")
            cells.append(heat(a) + heat(b) + f"<td class='num'>{delta(a, b)}</td>")
        rows.append(f"<tr><th scope='row'><code>{E(c)}</code></th>{''.join(cells)}</tr>")
    return (f"<div class='tbl'><table class='heat'><thead><tr><th></th>{head}</tr><tr><th></th>{sub}</tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></div>")


def transitions_section(runs: dict, configs: list[str]) -> str:
    blocks = []
    for c in configs:
        v1, v2 = runs.get((c, "1")), runs.get((c, "2"))
        if not v1 or not v2 or v2["n_golden"] < v1["n_golden"]:
            if v1:
                state = (f"Prompt v2 run in progress: {v2['n']} of 50 documents, {v2['n_golden']} of {v1['n_golden']} golden documents so far."
                         if v2 else "Prompt v2 has not been run on the full set for this configuration yet.")
                blocks.append(f"<div class='trans'><h4><code>{E(c)}</code></h4><p class='muted'>{state}</p></div>")
            continue
        counts, cells = transitions(v1, v2)
        chips = " ".join(f"<span class='chip {k}'>{counts.get(k, 0)} {k}</span>" for k in ("fixed", "still", "regressed", "kept"))
        body = "".join(
            f"<tr><td>{E(d['doc'])}</td><td>{E(FIELD_SHORT[d['field']])}</td><td><span class='chip {d['kind']}'>{d['kind']}</span></td>"
            f"<td>{E(str(d['golden']))}</td><td>{E(str(d['v1']))}</td><td>{E(str(d['v2']))}</td></tr>" for d in cells)
        tbl = (f"<div class='tbl'><table><thead><tr><th>doc</th><th>field</th><th>v1 → v2</th><th>golden</th><th>v1 answer</th><th>v2 answer</th></tr></thead>"
               f"<tbody>{body}</tbody></table></div>") if cells else "<p class='muted'>All 80 golden fields identical between v1 and v2.</p>"
        blocks.append(f"<div class='trans'><h4><code>{E(c)}</code> <span class='sm'>{E(v1['model'])}, {E(params_str(v1['params']))}</span> "
                      f"<span class='score'>{pct(v1['accuracy'])} → <b>{pct(v2['accuracy'])}</b></span></h4><p>{chips}</p>{tbl}</div>")
    return "\n".join(blocks)


def full_table(runs: dict, configs: list[str]) -> str:
    rows = []
    for c in configs:
        for p in ("1", "2"):
            m = runs.get((c, p))
            if not m:
                continue
            rows.append(
                f"<tr class='p{p}'><td><code>{E(c)}</code></td><td>v{p}</td><td class='num'>{m['n']}</td>"
                f"<td class='num'>{pct(m['valid'])}</td><td class='num'>{m['n_repaired']} / {m['n_failed']}</td>"
                f"<td class='num'>{sec(m['p50'])}</td><td class='num'>{sec(m['p95'])}</td>"
                f"<td class='num'>{m['avg_in']:.0f} / {m['avg_out']:.0f}</td><td class='num'>${m['cost_per_1000']:.3f}</td>"
                f"<td class='num'><b>{pct(m['accuracy'])}</b></td><td class='num'>{pct(m['doc_exact'])}</td></tr>")
    return ("<div class='tbl'><table><thead><tr><th>config</th><th>prompt</th><th>docs</th><th>valid JSON</th><th>repaired / failed</th>"
            "<th>p50</th><th>p95</th><th>avg tokens in / out</th><th>cost / 1000 docs</th><th>golden field acc.</th><th>docs fully correct</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></div>")


def demo_section(files: list[Path]) -> str:
    if not files:
        return "<p class='muted'>No unconstrained demo files found.</p>"
    cards = []
    for f in sorted(files):
        rows = load_rows(f)
        if not rows:
            continue
        m = run_metrics(rows)
        first = next((r for r in rows if r.get("extra", {}).get("first_answer")), None)
        sample = (first["extra"]["first_answer"][:220] + "…") if first else ""
        kind = "code fence" if sample.lstrip().startswith("```") else "prose before any JSON" if sample else "—"
        cards.append(
            f"<div class='demo'><h4><code>{E(m['config'])}</code> <span class='sm'>{E(m['model'])}, prompt v{E(m['prompt'])}, schema removed from the request</span></h4>"
            f"<p><span class='chip kept'>{m['n_ok']} ok</span> <span class='chip fixed'>{m['n_repaired']} repaired</span> <span class='chip regressed'>{m['n_failed']} failed</span> "
            f"<span class='sm'>over {m['n']} golden documents · median {sec(m['p50'])} per document incl. repair</span></p>"
            f"<p class='sm'>Typical first answer ({E(kind)}):</p><pre class='sample'>{E(sample)}</pre></div>")
    return "\n".join(cards)


def remaining_errors(runs: dict, configs: list[str]) -> str:
    items = []
    for c in configs:
        m = runs.get((c, "2"))
        if not m:
            continue
        for doc, ds in sorted(m["scores"].items()):
            for fr in ds.fields:
                if not fr.match:
                    items.append((doc, fr.field, c, fmt_value(fr.golden), fmt_value(fr.predicted)))
    if not items:
        return "<p class='muted'>No v2 results yet.</p>"
    by: dict[tuple[str, str], list] = defaultdict(list)
    for doc, f, c, g, p in items:
        by[(doc, f)].append((c, g, p))
    out = []
    for (doc, f), lst in sorted(by.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        rows = "".join(f"<tr><td><code>{E(c)}</code></td><td>{E(str(p))}</td></tr>" for c, g, p in lst)
        note = NOTES.get((doc, f))
        out.append(
            f"<div class='err'><h4>Document {E(doc)} · {E(FIELD_SHORT[f])} <span class='sm'>wrong in {len(lst)} of {sum(1 for c in configs if (c, '2') in runs)} v2 runs</span></h4>"
            f"<p><b>Golden:</b> {E(str(lst[0][1]))}</p>"
            f"<div class='tbl'><table><thead><tr><th>config</th><th>v2 answer</th></tr></thead><tbody>{rows}</tbody></table></div>"
            + (f"<p class='note'>{E(note)}</p>" if note else "<p class='note muted'>No written interpretation yet.</p>") + "</div>")
    return "\n".join(out)


def v3_section() -> str:
    return "".join(
        f"<div class='prop'><h4>{E(p['title'])} <span class='who'>{E(p['who'])}</span></h4>"
        f"<p><b>Change.</b> {E(p['what'])}</p><p><b>Why.</b> {E(p['why'])}</p></div>" for p in V3)


CSS = """
/* Layout: one reading column, data tables full width inside it; v1 muted slate, v2 deep teal; semantic chips for fixed/still/regressed. */
:root{--bg:#f6f7f8;--card:#ffffff;--fg:#1d2730;--muted:#64717c;--line:#d9dee3;--v1:#9aa7b2;--v2:#0f766e;--v2soft:#d9efec;
 --ok:#1f8a4c;--oksoft:#dff3e6;--warn:#b26a00;--warnsoft:#fbeed3;--bad:#b3261e;--badsoft:#fadcd9;--h1:#f6d4cf;--h2:#fbe7c6;--h3:#e3f1e8;--h4:#c8e8d5;
 --sans:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;--mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#13181d;--card:#1b2229;--fg:#e6ebef;--muted:#98a4ae;--line:#2e3840;--v1:#6b7983;--v2:#3cc0b3;--v2soft:#15423e;
 --ok:#5fcf8a;--oksoft:#163f2a;--warn:#f0b35a;--warnsoft:#3f3015;--bad:#f28b82;--badsoft:#4a1f1c;--h1:#5a2a26;--h2:#5a4320;--h3:#1f3f2c;--h4:#1f5a38;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#13181d;--card:#1b2229;--fg:#e6ebef;--muted:#98a4ae;--line:#2e3840;--v1:#6b7983;--v2:#3cc0b3;--v2soft:#15423e;
 --ok:#5fcf8a;--oksoft:#163f2a;--warn:#f0b35a;--warnsoft:#3f3015;--bad:#f28b82;--badsoft:#4a1f1c;--h1:#5a2a26;--h2:#5a4320;--h3:#1f3f2c;--h4:#1f5a38;color-scheme:dark}
body{background:var(--bg);color:var(--fg);font:15px/1.55 var(--sans);margin:0;padding-block:32px 64px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
main{max-width:1060px;margin:0 auto;display:grid;gap:40px}
h1{font-size:clamp(26px,4vw,38px);line-height:1.15;margin:0 0 8px;text-wrap:balance;letter-spacing:-.01em}
h2{font-size:22px;margin:0 0 12px;text-wrap:balance}
h3{font-size:17px;margin:20px 0 8px}
h4{font-size:15px;margin:0 0 6px;display:flex;flex-wrap:wrap;gap:8px 12px;align-items:baseline}
p{margin:0 0 10px;max-width:72ch}
.lead{font-size:17px;color:var(--muted);max-width:68ch}
.eyebrow{font-family:var(--mono);font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin-bottom:6px}
code{font-family:var(--mono);font-size:.92em}
.muted{color:var(--muted)} .sm{font-size:13px;color:var(--muted)} .up{color:var(--ok);font-weight:600} .down{color:var(--bad);font-weight:600}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px 16px;min-width:0}
.tile .k{font-size:13px;color:var(--muted)} .tile .v{font-size:26px;font-weight:600;font-variant-numeric:tabular-nums;margin:2px 0}
.tile .v small{font-size:15px;font-weight:400;color:var(--muted)} .tile .d{font-size:13px}
section{display:grid;gap:8px}
.tbl{overflow-x:auto;max-width:100%}
table{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{font-weight:600;color:var(--muted);font-size:13px;white-space:nowrap} th.sub{font-weight:400;font-size:12px}
td.num,th.num{text-align:right;white-space:nowrap}
tr.p2 td{background:var(--v2soft)}
table.heat td.num{text-align:center} .h1{background:var(--h1)} .h2{background:var(--h2)} .h3{background:var(--h3)} .h4{background:var(--h4)}
svg{width:100%;height:auto;display:block} .grid{stroke:var(--line);stroke-width:1} .tick,.lbl,.val{fill:var(--fg);font-family:var(--mono);font-size:12px} .tick{fill:var(--muted)}
.b1{fill:var(--v1)} .b2{fill:var(--v2)}
.chip{display:inline-block;font-family:var(--mono);font-size:12px;padding:1px 8px;border-radius:999px;border:1px solid transparent;white-space:nowrap}
.chip.fixed{background:var(--oksoft);color:var(--ok)} .chip.still{background:var(--warnsoft);color:var(--warn)} .chip.regressed{background:var(--badsoft);color:var(--bad)} .chip.kept{background:var(--card);border-color:var(--line);color:var(--muted)}
.trans,.demo,.err,.prop{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px 16px;min-width:0}
.trans .score{margin-left:auto;font-family:var(--mono);font-size:14px} .trans .score b{color:var(--v2)}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
pre{font-family:var(--mono);font-size:12.5px;line-height:1.45;white-space:pre-wrap;word-break:break-word;background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:10px 12px;margin:6px 0 0;max-height:420px;overflow:auto}
pre.sample{max-height:150px}
.note{border-left:3px solid var(--v2);padding-left:10px;margin-top:8px}
.who{font-family:var(--mono);font-size:12px;color:var(--v2);background:var(--v2soft);padding:1px 8px;border-radius:999px}
details{border:1px solid var(--line);border-radius:8px;padding:8px 12px;background:var(--card)} summary{cursor:pointer;font-weight:600}
ol.rules{padding-left:20px;max-width:78ch} ol.rules li{margin-bottom:4px}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--muted)} .legend i{display:inline-block;width:12px;height:12px;border-radius:2px;vertical-align:-2px;margin-right:6px} .legend .i1{background:var(--v1)} .legend .i2{background:var(--v2)}
footer{color:var(--muted);font-size:13px}
a{color:var(--v2)}
@media (prefers-reduced-motion: reduce){*{animation:none!important;transition:none!important}}
"""


def render(runs: dict, demo_files: list[Path]) -> str:
    configs = [c for c in CONFIG_ORDER if any(k[0] == c for k in runs)]
    have_v2 = [c for c in configs if (c, "2") in runs]
    fm1, body1 = front_matter("v1")
    fm2, body2 = front_matter("v2")

    tiles = []
    for c in configs:
        v1, v2 = runs.get((c, "1")), runs.get((c, "2"))
        a = v1["accuracy"] if v1 else float("nan")
        b = v2["accuracy"] if v2 else float("nan")
        model = (v1 or v2)["model"]
        tiles.append(f"<div class='tile'><div class='k'><code>{E(c)}</code> · {E(model)}</div>"
                     f"<div class='v'>{pct(b) if v2 else '<small>running</small>'} <small>from {pct(a)}</small></div>"
                     f"<div class='d'>{delta(a, b)} pp golden field accuracy</div></div>")

    pairs = [(c, runs[(c, '1')]['accuracy'] if (c, '1') in runs else float('nan'),
              runs[(c, '2')]['accuracy'] if (c, '2') in runs else float('nan')) for c in configs]

    # totals across configs that have both versions
    fixed = still = regressed = 0
    for c in have_v2:
        if (c, "1") in runs:
            cnt, _ = transitions(runs[(c, "1")], runs[(c, "2")])
            fixed += cnt.get("fixed", 0); still += cnt.get("still", 0); regressed += cnt.get("regressed", 0)

    # cost / latency trade of the longer prompt
    trade = []
    for c in configs:
        v1, v2 = runs.get((c, "1")), runs.get((c, "2"))
        if v1 and v2:
            trade.append(f"<li><code>{E(c)}</code>: input tokens {v1['avg_in']:.0f} → {v2['avg_in']:.0f} per document, "
                         f"p50 {sec(v1['p50'])} → {sec(v2['p50'])}, cost ${v1['cost_per_1000']:.3f} → ${v2['cost_per_1000']:.3f} per 1,000 documents.</li>")

    rules = re.findall(r"^\s*\d\.\s+(\w+):", body2, re.M)
    files_list = "".join(f"<li><code>{E(m['file'].name)}</code> — prompt sha {E(str(m.get('prompt_sha256')))}</li>"
                         for k, m in sorted(runs.items())) + "".join(f"<li><code>{E(f.name)}</code> — unconstrained demo</li>" for f in demo_files)

    return f"""<title>Prompt v1 vs v2</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>{CSS}</style>
<main>
<header>
  <div class="eyebrow">medical-assistant · course tasks 3–4 · generated {date.today().isoformat()}</div>
  <h1>What prompt v2 changed, measured</h1>
  <p class="lead">Prompt v1 was a one-sentence task statement. Prompt v2 adds eight field rules written from the v1 errors on the golden set. This page shows, per configuration and per field, what v2 fixed, what it did not, what the longer prompt costs on the full dataset, and what a v3 should try next.</p>
</header>

<section>
  <div class="eyebrow">golden set · 10 documents · 80 fields</div>
  <div class="tiles">{''.join(tiles)}</div>
  <p class="sm">Across the {len([c for c in have_v2 if (c, '1') in runs])} configurations with both versions: <span class="chip fixed">{fixed} fields fixed</span> <span class="chip still">{still} still wrong</span> <span class="chip regressed">{regressed} regressed</span></p>
</section>

<section>
  <h2>1. What changed in the prompt</h2>
  <p>v2 keeps the task but replaces “fill every field as well as you can” with one rule per field: {', '.join(E(r) for r in rules)}. Every rule names the v1 error it answers; the changelog is in the prompt file's front matter.</p>
  <div class="cols">
    <details><summary>Prompt v1 (baseline)</summary><pre>{E(fm1)}
---
{E(body1)}</pre></details>
    <details><summary>Prompt v2 (rules + changelog)</summary><pre>{E(fm2)}
---
{E(body2)}</pre></details>
  </div>
</section>

<section>
  <h2>2. Golden-set accuracy, v1 against v2</h2>
  <div class="legend"><span><i class="i1"></i>prompt v1</span><span><i class="i2"></i>prompt v2</span><span>share of 80 golden fields matched under the fixed scoring rules</span></div>
  {paired_bars(pairs)}
  <h3>By field</h3>
  <p class="sm">Each cell is the share of the 10 golden documents where that field matched. Δ in percentage points; one document is 10 points.</p>
  {field_table(runs, configs)}
  <h3>Field by field, document by document</h3>
  <p class="sm">Only the cells that changed or stayed wrong are listed; “kept” cells were right under both prompts.</p>
  {transitions_section(runs, configs)}
</section>

<section>
  <h2>3. Full dataset: what the longer prompt costs</h2>
  <p>Accuracy comes from the 10 golden documents. Validity, latency, token use and cost are measured on all 50. v2 is roughly five times longer than v1, so every request carries more input tokens.</p>
  {full_table(runs, configs)}
  <ul class="sm">{''.join(trade)}</ul>
</section>

<section>
  <h2>4. Validation and the one repair call</h2>
  <p>Every answer is validated against the schema. An invalid answer triggers exactly one repair call with the same model, prompt and sampling settings, the conversation extended with the invalid answer and the validation error. A document ends as <code>ok</code>, <code>repaired</code>, <code>failed</code> (second answer also invalid) or <code>error</code> (transport failure after retries). With constrained decoding on, which is the production setting, every answer in every full run above validated on the first try, so the repair path is exercised here with the schema removed from the request.</p>
  <div class="cols">{demo_section(demo_files)}</div>
  <p class="sm">Reading: the hosted model's only free-form fault is a Markdown code fence, which the repair call removes every time. The 4B local model without a schema writes its reasoning as prose and the repair call repeats the behaviour, so it fails. The demo on Qwen was stopped after four documents on purpose; four failures of four was enough evidence.</p>
</section>

<section>
  <h2>5. What v2 still gets wrong</h2>
  <p>Each remaining golden mismatch after v2, grouped by document and field, with the answer of every configuration and an interpretation.</p>
  {remaining_errors(runs, configs)}
</section>

<section>
  <h2>6. Proposals for prompt v3</h2>
  <p>Ordered by expected gain per line of prompt. Each one is tied to an error still visible above, and each should be measured on the golden set before it is kept.</p>
  <div class="cols">{v3_section()}</div>
</section>

<footer>
  <p>Files used:</p><ul>{files_list}</ul>
  <p>Generated by <code>scripts/report_prompts.py</code> from the result files; scoring rules in <code>src/medassist/scoring.py</code>. Golden labels are the reference; where a label and a prompt rule disagree, the page says so instead of hiding it.</p>
</footer>
</main>
"""


def build_prompt_page(out: Path = DEFAULT_OUT, verbose: bool = False) -> Path:
    """results/*_full.json (+ unconstrained demo files) -> the prompt comparison page."""
    files = sorted((ROOT / "results").glob("*_full.json"))
    demo = [f for f in sorted((ROOT / "results").glob("*_golden_unconstrained.json")) if f.stat().st_size > 0]
    runs = load_runs(files)
    out.write_text(render(runs, demo), encoding="utf-8")
    if verbose:
        shown = out.relative_to(ROOT) if out.resolve().is_relative_to(ROOT) else out
        print(f"wrote {shown} from {len(files)} full runs and {len(demo)} demo files")
        for (c, p), m in sorted(runs.items()):
            print(f"  {c:11s} v{p}  golden {pct(m['accuracy']):>6}  valid {pct(m['valid']):>6}  rep/fail {m['n_repaired']}/{m['n_failed']}  p50 {sec(m['p50'])}  ${m['cost_per_1000']:.3f}/1000")
    return out
