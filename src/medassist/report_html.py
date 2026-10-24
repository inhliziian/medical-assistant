"""Render the HTML report (reports/checkpoint-1.html) from result files. Self-contained page: inline CSS and SVG."""
from __future__ import annotations

import argparse
import html
import json
import re
import tomllib
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from .metrics import load_rows, run_metrics
from .scoring import FIELDS, fmt_value

ROOT = Path(__file__).resolve().parents[2]
E = html.escape

SERIES = {"anthropic": "var(--s1)", "ollama": "var(--s2)"}


def pct(x: float) -> str:
    return "n/a" if x != x else f"{100 * x:.1f}%"


def ms(x: float) -> str:
    return f"{x / 1000:.1f} s" if x >= 1000 else f"{x:.0f} ms"


def params_str(p: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in p.items()) or "defaults"


def label(m: dict) -> str:
    return f"{m['config']} · v{m['prompt']}"


# ---------- charts (inline SVG, drawn to one scale) ----------

def bar_chart(items: list[tuple[str, float, str, str]], vmax: float, fmt, title: str, note: str = "") -> str:
    """items: (label, value, color, tooltip). Horizontal bars, labels left, values right."""
    row_h, top, left, width, right = 30, 14, 190, 760, 70
    h = top + row_h * len(items) + 30
    plot_w = width - left - right
    out = [f'<figure class="chart"><figcaption>{E(title)}</figcaption>'
           f'<svg viewBox="0 0 {width} {h}" role="img" aria-label="{E(title)}">']
    for i in range(5):
        x = left + plot_w * i / 4
        out.append(f'<line class="grid" x1="{x:.1f}" x2="{x:.1f}" y1="{top - 4}" y2="{h - 26}"/>'
                   f'<text class="tick" x="{x:.1f}" y="{h - 8}" text-anchor="middle">{E(fmt(vmax * i / 4))}</text>')
    for i, (lab, val, color, tip) in enumerate(items):
        y = top + i * row_h
        w = 0 if val != val else max(0.0, min(1.0, val / vmax)) * plot_w
        out.append(f'<g><title>{E(tip)}</title>'
                   f'<text class="lab" x="{left - 10}" y="{y + 19}" text-anchor="end">{E(lab)}</text>'
                   f'<rect x="{left}" y="{y + 6}" width="{w:.1f}" height="16" style="fill:{color}"/>'
                   f'<text class="val" x="{left + w + 6:.1f}" y="{y + 19}">{E(fmt(val))}</text></g>')
    out.append(f'<line class="axis" x1="{left}" x2="{left}" y1="{top - 4}" y2="{h - 26}"/></svg>')
    if note:
        out.append(f'<p class="note">{E(note)}</p>')
    out.append("</figure>")
    return "".join(out)


def heat_cell(v: float) -> str:
    if v != v:
        return '<td class="num">n/a</td>'
    # one hue, light -> dark with accuracy; text stays in ink tokens
    alpha = 0.08 + 0.72 * v
    return f'<td class="num heat" style="--a:{alpha:.2f}">{pct(v)}</td>'


# ---------- sections ----------

def dataset_summary() -> str:
    seeds = json.loads((ROOT / "data/seeds/seeds.json").read_text(encoding="utf-8"))
    types = Counter(s["facts"]["report_type"] for s in seeds)
    langs = Counter(s["hints"]["language"] for s in seeds)
    lens = Counter(s["hints"]["length"] for s in seeds)
    null_age = sum(s["facts"]["patient_age"] is None for s in seeds)
    unk_sex = sum(s["facts"]["patient_sex"] == "unknown" for s in seeds)
    golden = [s["id"] for s in seeds if s["golden"]]
    dirt = Counter()
    for s in seeds:
        for k, v in s["dirt"].items():
            if v:
                dirt[k] += 1
    return f"""
<div class="cards">
  <div class="card"><div class="k">{len(seeds)}</div><div class="l">documents in <code>data/raw</code></div></div>
  <div class="card"><div class="k">{len(golden)}</div><div class="l">golden labels, hand-verified</div></div>
  <div class="card"><div class="k">{langs['en']} / {langs['uk']} / {langs['mixed']}</div><div class="l">English / Ukrainian / mixed</div></div>
  <div class="card"><div class="k">{null_age}</div><div class="l">documents with no stated age</div></div>
</div>
<div class="tbl"><table>
<tr><th>Report types</th><td>{", ".join(f"{k} {v}" for k, v in types.most_common())}</td></tr>
<tr><th>Length</th><td>short {lens['short']} (45-90 words), medium {lens['medium']} (120-220), long {lens['long']} (260-420)</td></tr>
<tr><th>Missing by design</th><td>age not stated in {null_age}, sex not inferable in {unk_sex}, doses and frequencies withheld on some medications, units withheld on some lab values</td></tr>
<tr><th>Noise applied</th><td>{", ".join(f"{k.replace('_', ' ')} ×{v}" for k, v in dirt.most_common())}</td></tr>
<tr><th>Golden ids</th><td>{", ".join(golden)}</td></tr>
<tr><th>Provenance</th><td>Synthetic. Notes written by Claude Opus 5.5 agents from deterministic seeds, then dirtied by <code>scripts/add_noise.py</code>. No personal data. The generation model is not one of the evaluated models.</td></tr>
</table></div>"""


def configs_table() -> str:
    data = tomllib.loads((ROOT / "config/runs.toml").read_text(encoding="utf-8"))
    rows = []
    for name, c in data["configs"].items():
        p = data["providers"][c["provider"]]
        knobs = {k: v for k, v in c.items() if k != "provider"}
        price = f"${p.get('price_input_per_mtok', 0):.2f} / ${p.get('price_output_per_mtok', 0):.2f} per MTok" if p["type"] == "anthropic" else "none (local)"
        rows.append(f"<tr><td><code>{E(name)}</code></td><td>{E(p['type'])}</td><td>{E(p['model'])}</td><td>{E(params_str(knobs))}</td><td>{E(price)}</td><td>{p.get('timeout_s')} s, {p.get('max_retries')} retries</td></tr>")
    return ('<div class="tbl"><table><thead><tr><th>config</th><th>provider</th><th>model</th><th>knobs</th><th>price</th><th>timeout</th></tr></thead>'
            + "".join(rows) + "</table></div>")


def prompt_block(version: str) -> str:
    p = ROOT / "prompts/extraction" / f"{version}.md"
    text = p.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    fm, body = (m.group(1), m.group(2)) if m else ("", text)
    return f'<details><summary>Prompt {E(version)}: front matter and text</summary><pre>{E(fm)}\n---\n{E(body.strip())}</pre></details>'


def overview_table(ms_: list[dict]) -> str:
    best = max(m["accuracy"] for m in ms_ if m["accuracy"] == m["accuracy"])
    rows = []
    for m in ms_:
        cls = ' class="best"' if m["accuracy"] == best else ""
        tok = f"{m['avg_in']:.0f} / {m['avg_out']:.0f}" if m["avg_in"] is not None else "n/a"
        rows.append(f"<tr{cls}><td><code>{E(m['config'])}</code></td><td>{E(m['model'])}</td><td>v{E(m['prompt'])}</td><td>{E(params_str(m['params']))}</td>"
                    f"<td class='num'>{m['n']}</td><td class='num'><strong>{pct(m['accuracy'])}</strong></td><td class='num'>{pct(m['doc_exact'])}</td>"
                    f"<td class='num'>{pct(m['valid'])}</td><td class='num'>{ms(m['p50'])}</td><td class='num'>{ms(m['p95'])}</td>"
                    f"<td class='num'>${m['cost_per_1000']:.3f}</td><td class='num'>{tok}</td></tr>")
    return ('<div class="tbl"><table><thead><tr><th>config</th><th>model</th><th>prompt</th><th>sampling</th><th>docs</th>'
            '<th>field accuracy<br><small>golden, 8 fields × docs</small></th><th>docs fully correct</th><th>valid JSON<br><small>all docs</small></th>'
            '<th>latency p50</th><th>latency p95</th><th>cost / 1000 docs</th><th>avg tokens in / out</th></tr></thead>'
            + "".join(rows) + "</table></div>")


def per_field_table(ms_: list[dict]) -> str:
    head = "".join(f"<th>{E(f)}</th>" for f in FIELDS)
    rows = "".join(f"<tr><td><code>{E(label(m))}</code></td>" + "".join(heat_cell(m["per_field"][f]) for f in FIELDS) + "</tr>" for m in ms_)
    return f'<div class="tbl"><table class="heatmap"><thead><tr><th>config</th>{head}</tr></thead>{rows}</table></div>'


def failures(ms_: list[dict], runs: dict[str, list[dict]]) -> str:
    rows = []
    for m in ms_:
        bad = [r for r in runs[label(m)] if not r["valid"]]
        detail = "; ".join(f"{r['doc_id']}: {E((r.get('error') or r.get('validation_error') or '')[:90])}" for r in bad[:6])
        rows.append(f"<tr><td><code>{E(m['config'])}</code> v{E(m['prompt'])}</td><td class='num'>{m['n'] - len(bad)}/{m['n']}</td><td class='num'>{m['n_invalid']}</td><td class='num'>{m['n_error']}</td><td class='num'>{m['retries']}</td><td>{detail or '—'}</td></tr>")
    return ('<div class="tbl"><table><thead><tr><th>run</th><th>valid</th><th>schema-invalid</th><th>transport errors</th><th>retries</th><th>failed documents</th></tr></thead>'
            + "".join(rows) + "</table></div>")


def golden_detail(ms_: list[dict]) -> str:
    golden_ids = sorted(set().union(*[set(m["scores"]) for m in ms_]))
    out = []
    for doc in golden_ids:
        raw = (ROOT / "data/raw" / f"{doc}.txt").read_text(encoding="utf-8")
        head = "".join(f"<th>{E(label(m))}<br><small>{m['scores'][doc].matched}/8</small></th>" for m in ms_ if doc in m["scores"])
        body = []
        for i, f in enumerate(FIELDS):
            cells = []
            golden_val = None
            for m in ms_:
                if doc not in m["scores"]:
                    continue
                fr = m["scores"][doc].fields[i]
                golden_val = fr.golden
                cls = "ok" if fr.match else "miss"
                cells.append(f"<td class='{cls}'><span class='mark'>{'✓' if fr.match else '✗'}</span> {E(fmt_value(fr.predicted))}</td>")
            body.append(f"<tr><th>{E(f)}</th><td class='gold'>{E(fmt_value(golden_val))}</td>{''.join(cells)}</tr>")
        out.append(f"""<details class="doc"><summary><strong>{doc}</strong> · {" · ".join(f"{E(m['config'])} v{m['prompt']} {m['scores'][doc].matched}/8" for m in ms_ if doc in m['scores'])}</summary>
<div class="cols"><div><h4>Raw document</h4><pre class="raw">{E(raw)}</pre></div>
<div class="tbl"><table class="detail"><thead><tr><th>field</th><th>golden</th>{head}</tr></thead>{"".join(body)}</table></div></div></details>""")
    return "".join(out)


def error_catalogue(ms_: list[dict]) -> str:
    by_field: dict[str, list] = defaultdict(list)
    for m in ms_:
        for doc, ds in m["scores"].items():
            for fr in ds.fields:
                if not fr.match:
                    by_field[fr.field].append((doc, label(m), fr.golden, fr.predicted, fr.note))
    total = sum(len(v) for v in by_field.values())
    out = [f"<p>{total} field mismatches across all runs on the golden documents, grouped by field. Each group shows up to four examples.</p>"]
    for f, items in sorted(by_field.items(), key=lambda kv: -len(kv[1])):
        rows = "".join(f"<tr><td>{E(d)}</td><td><code>{E(c)}</code></td><td>{E(fmt_value(g))}</td><td>{E(fmt_value(p))}</td><td>{E(n)}</td></tr>" for d, c, g, p, n in items[:4])
        out.append(f"<h4>{E(f)} <small>{len(items)} mismatches</small></h4><div class='tbl'><table><thead><tr><th>doc</th><th>run</th><th>golden</th><th>predicted</th><th>note</th></tr></thead>{rows}</table></div>")
    return "".join(out)


def status_log() -> str:
    s = (ROOT / "data/golden/STATUS.md").read_text(encoding="utf-8")
    i = s.find("## Corrections log")
    return f"<pre>{E(s[i:].strip())}</pre>" if i >= 0 else "<p>No corrections logged.</p>"


def qa_section(ms_: list[dict]) -> str:
    """Questions for the course Q&A, each grounded in a measurement from this report."""
    by = {label(m): m for m in ms_}
    low, high = by.get("haiku_low · v1"), by.get("haiku_high · v1")
    q0, q7 = by.get("qwen_t0 · v1"), by.get("qwen_t07 · v1")
    sex_low = pct(low["per_field"]["patient_sex"]) if low else "n/a"
    sex_high = pct(high["per_field"]["patient_sex"]) if high else "n/a"
    qacc = f"{pct(q0['accuracy'])} at t=0 and {pct(q7['accuracy'])} at t=0.7" if q0 and q7 else "n/a"
    items = [
        ("Grammatical gender as evidence: how far may the model infer?",
         f"Document 037 is a Ukrainian consult note. The only gender cue is the masculine noun «Пацієнт», five times; there is no pronoun, no title, no gendered verb form. Haiku 5.5 at low effort answered <code>unknown</code> (sex accuracy {sex_low}), at high effort <code>male</code> ({sex_high}). Our golden label says male, and prompt v2 states the rule explicitly, after which both models answer male.",
         "Is grammatical gender acceptable evidence for a labelled field, or does it violate the \"never guess\" principle we apply to age? Where do practitioners draw the line between inference from language and invention? Should the labelling convention be the schema's job (a field description) or the prompt's?"),
        ("Temperature changed nothing for the local model. Is that expected under constrained decoding?",
         f"Qwen3 4B scored {qacc}, with an identical per-field profile in both runs, over 50 documents. Ollama constrains generation to the JSON schema, so the sampler can only choose among tokens that keep the output valid.",
         "With schema-constrained decoding, is a temperature / top_p comparison still a meaningful experiment for extraction tasks? If not, which knob should take its place as the second \"sampling\" dimension: thinking on/off, context length, quantisation, model size? And for hosted models that reject temperature (Haiku 5.5), is <code>effort</code> the right analogue?"),
        ("If sampling does not move accuracy, the prompt is the only lever left. How much belongs in the prompt versus the schema?",
         "Prompt v2 adds conventions learned from v1 errors (bare diagnosis names, sex from the patient's own pronouns, no invented units, dose and frequency in their own fields). On the golden set it lifted Haiku from 88.8% to 97.5% and Qwen from 68.8% to 83.8%. Some of these rules could instead live in the schema, for example a stricter enum for frequency or richer field descriptions.",
         "What is the recommended split between prompt rules and schema design? Do field descriptions in a JSON Schema reach the model as reliably as prompt text for both hosted and local providers? Is there a point where a long rule list starts to hurt a small local model?"),
        ("AI-generated data evaluated by AI: how serious is the familiarity bias, and how should we control for it?",
         "The 50 documents were written by Claude Opus 5.5 agents from deterministic seeds, then dirtied by a script. The hosted evaluated model is Claude Haiku 5.5, a different model but the same family; the local model is Qwen3 4B, a different family. Risk: Haiku reads Opus-written text more comfortably than it would read real clinic notes, inflating its score relative to Qwen.",
         "Is a different model within the same family enough separation for a course project, or should generation and evaluation come from different vendors? How would you measure the bias in practice, for example by adding 10 real notes (mtsamples, ACI-Bench transcripts) and checking whether the Haiku-versus-Qwen gap changes? Is documenting the bias in the limitations section sufficient at this stage?"),
        ("Ten golden items: how much variance is acceptable before a difference counts?",
         "The same Haiku low-effort configuration scored 88.8% on one run and 91.2% on another with identical prompt and settings. With 10 golden documents, one field equals 1.25 percentage points, so differences of 2 to 3 points are within noise.",
         "What golden-set size do you consider the minimum for a trustworthy model comparison in a project like this? Should we report confidence intervals, repeat runs, or simply grow the set as we find errors in production, as the regression-suite approach suggests?"),
    ]
    out = ["<p>Each question is tied to a measurement on this page, so the discussion can start from evidence rather than opinion.</p>"]
    for i, (title, context, question) in enumerate(items, 1):
        out.append(f'<div class="qa"><h3>Q{i}. {title}</h3><p class="ctx"><strong>What we observed.</strong> {context}</p><p class="ask"><strong>Question.</strong> {question}</p></div>')
    return "".join(out)


# ---------- page ----------

CSS = """
:root{--bg:#f6f7f5;--surface:#fdfdfc;--surface-2:#eef1ed;--fg:#17201d;--fg-2:#4d5a55;--muted:#7f8b86;--line:#d9ded9;
--accent:#1f6f5c;--accent-soft:#dcebe5;--ok:#0ca30c;--ok-soft:#e3f4e3;--bad:#d03b3b;--bad-soft:#f8e4e4;--gold-soft:#f6ecd2;
--s1:#2a78d6;--s2:#eb6834;--grid:#e1e0d9;--axis:#c3c2b7;--heat:42,120,214;
--font-display:"Source Serif 4",Georgia,serif;--font-body:"IBM Plex Sans",system-ui,sans-serif;--font-mono:"IBM Plex Mono",ui-monospace,Menlo,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#121715;--surface:#1a201d;--surface-2:#232b27;--fg:#e8ece9;--fg-2:#b4bdb8;--muted:#8a948f;--line:#2e3733;
--accent:#5fb89f;--accent-soft:#1e3a32;--ok:#0ca30c;--ok-soft:#1b3a1b;--bad:#e66767;--bad-soft:#452222;--gold-soft:#3d3416;--s1:#3987e5;--s2:#d95926;--grid:#2c2c2a;--axis:#383835;--heat:57,135,229;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#121715;--surface:#1a201d;--surface-2:#232b27;--fg:#e8ece9;--fg-2:#b4bdb8;--muted:#8a948f;--line:#2e3733;
--accent:#5fb89f;--accent-soft:#1e3a32;--ok:#0ca30c;--ok-soft:#1b3a1b;--bad:#e66767;--bad-soft:#452222;--gold-soft:#3d3416;--s1:#3987e5;--s2:#d95926;--grid:#2c2c2a;--axis:#383835;--heat:57,135,229;color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font-family:var(--font-body);font-size:15.5px;line-height:1.55;margin:0;
padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:0 64px}
.wrap{max-width:1100px;margin:0 auto}
h1,h2,h3{font-family:var(--font-display);font-weight:600;line-height:1.2;text-wrap:balance;margin:0}
h1{font-size:clamp(28px,4.5vw,40px);margin-top:44px}
h2{font-size:24px;margin-top:56px;padding-top:18px;border-top:1px solid var(--line)}
h3{font-size:18px;margin-top:26px}
h4{margin:22px 0 6px;font-size:15px}h4 small{color:var(--muted);font-weight:400;margin-left:6px}
p{margin:10px 0;max-width:72ch}.lead{font-size:17.5px;color:var(--fg-2)}
.eyebrow{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);font-weight:600;margin-top:40px}
code,pre{font-family:var(--font-mono);font-size:13px}code{background:var(--surface-2);padding:1px 5px;border-radius:3px}
pre{background:var(--surface-2);border:1px solid var(--line);border-radius:6px;padding:12px 14px;overflow-x:auto;line-height:1.5;white-space:pre-wrap;word-break:break-word}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:16px 0}
.card{background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:14px 16px}.card .k{font-size:26px;font-weight:600;font-family:var(--font-display)}.card .l{color:var(--fg-2);font-size:13.5px}
.tbl{overflow-x:auto;margin:12px 0;border:1px solid var(--line);border-radius:6px;background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:8px 11px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}
thead th{font-size:12px;letter-spacing:.05em;text-transform:uppercase;color:var(--fg-2);background:var(--surface-2)}th small{display:block;font-weight:400;text-transform:none;letter-spacing:0}
tr:last-child td{border-bottom:none}td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
tr.best td{background:var(--accent-soft)}
td.heat{background:rgba(var(--heat),var(--a))}
td.ok{background:var(--ok-soft)}td.miss{background:var(--bad-soft)}td.gold{background:var(--gold-soft);font-weight:500}
.mark{font-weight:700;margin-right:4px}td.ok .mark{color:var(--ok)}td.miss .mark{color:var(--bad)}
table.detail td,table.detail th{font-size:13px}
.chart{margin:18px 0;background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:14px}
.chart figcaption{font-weight:600;font-size:14.5px;margin-bottom:6px}.chart svg{width:100%;height:auto;display:block;overflow:visible}
.chart text{font-family:var(--font-body);font-size:12px;fill:var(--fg-2)}.chart .lab{fill:var(--fg)}.chart .val{fill:var(--fg);font-variant-numeric:tabular-nums}
.chart .grid{stroke:var(--grid)}.chart .axis{stroke:var(--axis)}.chart .note{color:var(--muted);font-size:12.5px;margin:8px 0 0}
.legend{display:flex;gap:16px;font-size:13px;color:var(--fg-2);margin:4px 0 8px}.legend span::before{content:"";display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:-1px}
.legend .a::before{background:var(--s1)}.legend .b::before{background:var(--s2)}
details{margin:10px 0;border:1px solid var(--line);border-radius:6px;background:var(--surface)}summary{padding:10px 14px;cursor:pointer;font-weight:500}
details>*:not(summary){padding:0 14px 14px}details pre{margin:0}
details.doc .cols{display:grid;grid-template-columns:minmax(260px,1fr) minmax(0,1.6fr);gap:14px}
@media (max-width:860px){details.doc .cols{grid-template-columns:1fr}}
pre.raw{max-height:420px;overflow:auto;font-size:12px}
.qa{background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:14px 16px;margin:14px 0}.qa h3{margin:0 0 8px;font-size:17px}.qa p{max-width:none}.qa .ask{border-left:3px solid var(--accent);padding-left:12px}
.note-box{border-left:3px solid var(--accent);background:var(--accent-soft);padding:10px 14px;border-radius:0 6px 6px 0;margin:14px 0;max-width:80ch}
ul{padding-left:22px}li{margin:4px 0}
footer{color:var(--muted);font-size:13px;margin-top:48px}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
"""


def render(ms_: list[dict], runs: dict[str, list[dict]], title: str, files: list[Path]) -> str:
    best = max(ms_, key=lambda m: (m["accuracy"] if m["accuracy"] == m["accuracy"] else -1))
    prompts = sorted({m["prompt"] for m in ms_})
    acc_items = [(label(m), m["accuracy"], SERIES.get(m["provider"], "var(--s1)"), f"{label(m)}: {pct(m['accuracy'])} field accuracy on {m['n_golden']} golden docs") for m in ms_]
    lat_items = [(label(m), m["p50"], SERIES.get(m["provider"], "var(--s1)"), f"{label(m)}: p50 {ms(m['p50'])}, p95 {ms(m['p95'])}") for m in ms_]
    lat_max = max(m["p95"] for m in ms_) * 1.05
    valid_items = [(label(m), m["valid"], SERIES.get(m["provider"], "var(--s1)"), f"{label(m)}: {pct(m['valid'])} valid of {m['n']}") for m in ms_]
    n_docs = max(m["n"] for m in ms_)
    legend = '<div class="legend"><span class="a">Hosted (Anthropic)</span><span class="b">Local (Ollama)</span></div>'
    return f"""<title>{E(title)}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>{CSS}</style>
<div class="wrap">
<p class="eyebrow">Course project · checkpoint 1 · steps 1-2 · {date.today().isoformat()}</p>
<h1>{E(title)}</h1>
<p class="lead">Dirty clinical documents go in, schema-valid JSON comes out. This page records the setup (schema, baseline prompt, two models behind one interface, sampling configurations) and the measurements: per-field accuracy on the golden set, validity, latency and cost over all {n_docs} documents.</p>
<div class="cards">
  <div class="card"><div class="k">{len(ms_)}</div><div class="l">runs: model × prompt × sampling</div></div>
  <div class="card"><div class="k">{pct(best['accuracy'])}</div><div class="l">best field accuracy · <code>{E(label(best))}</code></div></div>
  <div class="card"><div class="k">{n_docs}</div><div class="l">documents per run</div></div>
  <div class="card"><div class="k">v{", v".join(prompts)}</div><div class="l">prompt version{'s' if len(prompts) > 1 else ''} in this report</div></div>
</div>

<h2>1. Setup</h2>
<h3>Dataset</h3>
{dataset_summary()}
<h3>Schema</h3>
<p>Eight top-level fields, three enums, two nested lists. Source of truth is <code>src/medassist/schema.py</code>; the JSON Schema sent to both providers is derived from it with <code>additionalProperties: false</code> on every object, so both models are constrained by the identical definition.</p>
<div class="tbl"><table><thead><tr><th>field</th><th>type</th><th>rule</th></tr></thead>
<tr><td>patient_age</td><td>int | null</td><td>null if not stated, never guessed</td></tr>
<tr><td>patient_sex</td><td>enum male / female / unknown</td><td>only from the patient's own pronouns or grammatical gender</td></tr>
<tr><td>report_type</td><td>enum consult / progress_note / discharge / referral / lab / radiology</td><td>document kind</td></tr>
<tr><td>diagnoses</td><td>list[str]</td><td>English, lowercase, one per condition</td></tr>
<tr><td>lab_values</td><td>list[{{name, value, unit | null}}]</td><td>numeric analytes only; decimal comma → point</td></tr>
<tr><td>medications</td><td>list[{{name, dose | null, frequency enum | null}}]</td><td>frequency normalised to 1x/day … as needed</td></tr>
<tr><td>urgency</td><td>enum routine / soon / urgent</td><td>same day = urgent, days to 2 weeks = soon</td></tr>
<tr><td>follow_up_required</td><td>bool</td><td>any named follow-up action</td></tr></table></div>
<h3>Models and configurations</h3>
<p>Both providers implement one interface, <code>Provider.extract(instructions, text)</code>, with retry, timeout, schema validation and cost accounting in the shared base class. Haiku 5.5 rejects non-default temperature and top_p, so its sampling dimension is the <code>effort</code> level; the local model exposes temperature and top_p. Switching models or settings is a config name in <code>config/runs.toml</code>.</p>
{configs_table()}
<h3>Prompt{'s' if len(prompts) > 1 else ''}</h3>
{"".join(prompt_block('v' + v) for v in prompts)}

<h2>2. Results</h2>
<p>Accuracy is measured on the golden documents only: each of the 8 fields is a match or a miss under fixed rules (enums exact, strings normalised, lists as sets, labs on name+value+unit, medications on name+dose+frequency). Validity, latency and cost are measured on every document. Latency is client-side wall clock including retries; cost is tokens × list price.</p>
{overview_table(ms_)}
{legend}
{bar_chart(acc_items, 1.0, pct, "Per-field accuracy on the golden set")}
{bar_chart(valid_items, 1.0, pct, "Share of documents with schema-valid JSON (after at most one retry)")}
{bar_chart(lat_items, lat_max, ms, "Latency p50 per document", "Bars show the median; hover a bar for p95. The first local call after idle includes model loading, which shows up in p95, not p50.")}
<h3>Accuracy by field</h3>
<p>Darker cells are higher. The weakest field for every run is the one to read first.</p>
{per_field_table(ms_)}
<h3>Validity, failures and retries</h3>
{failures(ms_, runs)}

<h2>3. Golden documents, field by field</h2>
<p>Each block shows the raw input as the models saw it, the golden label, and every run's answer. Green is a match under the scoring rules, red a miss. Open a block to read it.</p>
{golden_detail(ms_)}

<h2>4. Characteristic errors</h2>
{error_catalogue(ms_)}

<h2>5. Notes and limitations</h2>
<ul>
<li><strong>Golden labels were corrected during the first comparison.</strong> Two documents had the patient's sex labelled from the seed although the text never states it; the only pronouns referred to relatives. The labels now say <code>unknown</code> and the convention is recorded. Disagreements between model and label are read in both directions: sometimes the label is wrong.</li>
<li><strong>Local model size was dictated by hardware.</strong> Qwen3 8B on an 8 GB Mac placed only 76% of its weights on the GPU, swapped heavily and timed out after 8 minutes on one document. Qwen3 4B fits entirely and answers in seconds. Model choice for a local deployment is a memory question before it is a quality question.</li>
<li><strong>Sampling knobs differ by provider.</strong> Haiku 5.5 returns an error for non-default temperature and top_p; thinking depth is controlled by <code>effort</code>. The comparison therefore varies effort on the hosted side and temperature/top_p on the local side.</li>
<li><strong>Token counts are not comparable across providers.</strong> The two APIs tokenize differently and deliver the schema differently. Within one provider they are, which is what the cost column needs.</li>
<li><strong>Generation bias.</strong> The documents were written by Claude Opus 5.5, the same family as the hosted model. The deterministic noise pass and the planned addition of real-world texts (see <code>docs/hf-unstructured-data-research.md</code>) mitigate but do not remove this.</li>
<li><strong>Ten golden items</strong> means one field is 1.25 percentage points. Differences of a few points between runs are not significant; the field-level table is more informative than the headline number.</li>
</ul>
<h3>Golden set corrections log</h3>
{status_log()}

<h2>6. Questions for the Q&amp;A</h2>
{qa_section(ms_)}

<h2>Appendix: result files</h2>
<ul>{"".join(f"<li><code>{E(str(f.relative_to(ROOT)) if f.is_relative_to(ROOT) else f.name)}</code></li>" for f in files)}</ul>
<footer>Generated by <code>scripts/report.py</code> from the JSONL files above. Regenerate after every run.</footer>
</div>
"""


def build_html(files: list[Path], out: Path, title: str = "Extraction Baseline Report") -> Path:
    files = [Path(f).resolve() for f in files]
    runs_rows = [load_rows(f) for f in files]
    pairs = [(run_metrics(r), r) for r in runs_rows if r]
    order = {"anthropic": 0, "ollama": 1}
    pairs.sort(key=lambda pr: (order.get(pr[0]["provider"], 9), pr[0]["config"], pr[0]["prompt"]))
    ms_ = [m for m, _ in pairs]
    runs = {label(m): rows for m, rows in pairs}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(ms_, runs, title, files), encoding="utf-8")
    return out
