# Harder, real-world-messy data for the extraction task

Research date: 2026-10-21. Method: about 100 Hugging Face API searches (English, Cyrillic and domain terms), the dataset info and datasets-server endpoints for licences and sample rows, GitHub/Zenodo APIs for sources that are not on the Hub, web search for Ukrainian, Russian and German clinical corpora. Snippets below are real rows, shortened; names are replaced by initials.

**Baseline, already ruled out (too clean or wrong fit):** AGBonnet/augmented-clinical-notes, Asclepius, mtsamples, PMC-Patients, clinical-notes-to-fhir, ChatDoctor x2, MediQ_AskDocs, AskDocs-uncleaned, drug-reviews, russian-medical-complaints, NHSE synthetic notes, Zowel radiology reports.

## Key finding

The Hub has almost no **real, messy clinical text that ships as text**. The best "dirty" material comes from three routes: (a) raw ASR transcripts that sit in GitHub repos next to the HF copies, (b) real records published on Zenodo, (c) scanned documents with ground truth that **you OCR yourself**. A quick Tesseract run on one "fax" PDF from candidate 4 already produced the kind of noise the synthetic set lacks:

```
Apixaban 35mg PO BD NEW - stom Day 8 for 6 months      <- truth: 5mg, "from Day 8"
Paracetamot 1g PO O10 PAN for pain                     <- QID PRN
Acute bilatera) Pulmonary embolism (0CD-10-AM: 126.99) <- ICD-10-AM: I26.99
D-dimer 8.400 ng/mL (H). Troponin | 24 ng/L (H}. BNP 180 paymL (H)
```

## Candidates

| # | Source | Size | Licence / access | Kind | Verdict |
|---|---|---|---|---|---|
| 1 | ACI-Bench raw ASR: `github.com/wyim/aci-bench` `data/src_experiment_data/*_asr.csv` (clean copy on HF: `mkieffer/ACI-Bench`) | 207 encounters; ASR files cover about 90 (e.g. test1: 22 aci_asr + 8 virtscribe_asr) | CC BY 4.0, open | 2 | **Best fit** |
| 2 | RuMedPrime, `zenodo.org/records/5765873` (not on HF) | 7,625 real outpatient visits, TSV, 7.7 MB | CC BY 3.0, open | 3, 4, 5 | **Best non-English** |
| 3 | `RootCauseAnalytics/synthetic-australian-medical-documents-sample` | 50 PDFs, 29 doc types, scanned/poor/fax variants + `ground_truth.jsonl` | CC BY-NC 4.0, open | 1, 4 | Strong, OCR it yourself |
| 4 | Primock57: `github.com/babylonhealth/primock57` (HF: `sdialog/Primock-57`) | 57 consultations, ~9 h audio, human transcripts, GP-written notes | CC BY 4.0, open | 2, 3 | Strong, small |
| 5 | `Nigeria-Health-data-OCR-pipeline/African-Medical-Records` | 62 handwritten scans + exact transcriptions (15 to 6,500 words, median ~60) | CC BY 4.0, open | 6, 1 | Good, needs vision OCR |
| 6 | `modulate/synthetic-medical-dictation` | 300 notes x 6 audio conditions (clean ... "hard") | CC BY 4.0, open | 2 | Good, synthetic text |
| 7 | `johannsr/GraSCCo` (orig. Zenodo 6539131) | 62 German clinical letters/reports | CC BY 4.0 (Zenodo), open | 5 | Usable, clean-ish |
| 8 | `anechaev/ru_med_history` | 638 Russian textbook case histories (131 to 11k chars) | **no licence**, from textbooks | 4, 5 | Messy but legally unclear |
| 9 | `ekacare/medical_records_parsing_validation_set` | 288 real Indian lab reports and prescriptions (images), expert JSON turned into rubrics | MIT, **auto-gated** (accept terms) | 1, 4 | Real, images only, not inspected |
| 10 | `morzel85/synthetic-medical-document-recognition-benchmark` | 5 Synthea patients x 33 layouts x photo/photocopy/stain variants | CC BY 4.0 | 1 | Images only, repetitive |
| 11 | `ekacare/eka-medical-asr-evaluation-dataset` | 3,619 EN + 320 HI utterances with entity spans | MIT | 2 | Too fragmentary (10 s clips) |
| 12 | MIMIC-IV-Note (PhysioNet) / n2c2 2018 Track 2 (DBMI portal) | 330k discharge notes / 505 notes with medication labels | Credentialed: CITI course + DUA, 1-2 weeks; n2c2 DUA | 3 | Ideal content, heavy gating |

### Sample rows and schema mapping

**1. ACI-Bench ASR.** Lower-case, no punctuation in virtscribe, and **speaker tags swapped by ASR** (left in on purpose by the authors):
```
[doctor] is n't what it used to be
[patient] sure
[doctor] yeah it's you know i i seem to catch my breath a lot more than i used to
[doctor] eyes they're water does n't make very much sense to me
```
Maps to all 8 fields (age/sex usually spoken, meds and doses in dialogue, follow-up in the plan). Hard because facts are spread over 800 to 1,500 words, doses get corrected mid-conversation, and medications are discussed that are *not* taken. Schema gap: `report_type` has no value for a transcript (add `encounter_transcript` or map to `consult`); consider a medication `status` (new / continued / stopped). Privacy: role-played, no real patients.

**2. RuMedPrime.** Real outpatient visits, two-pass de-identified (`*ДАТА*`), columns symptoms / anamnesis / ICD-10:
```
головная боль, озноб, насморк, ... кашель (сухой, влажный), боль в горле (умеренная, сильная, небольшая) ... Повышение температуры до С.
Принимала ингавирин по 90 мг 1 раз в день ..., парацетамол 500 мг 1 т в день 3 дня
по УЗИ щит=9,9 ... ТТГ=5.07 ( 0.4-4,0) Т4св=115 ( 9-22.2)
```
Template junk left in (all checkbox options kept, `до С.` with the number missing), typos (`осмотор`, `на фое`), inline labs with reference ranges and decimal commas, meds in prose. Maps to diagnoses (ICD-10 given, helps checking), labs, meds, sometimes age; sex only from grammar (`Принимала`), so a good test of "infer vs. guess". Gap: optional `icd10` and `ref_range` fields. Russian, not Ukrainian; dates shifted. Privacy: published de-identified under CC BY, fine for a course; do not try to re-link `new_patient_id`.

**3. Australian scanned PDFs.** Ground truth per document gives age, sex, principal diagnosis, ICD, medications (`Temazepam 10mg PO nocte PRN | Levothyroxine 100mcg PO mane | ...`); labs and urgency are not labelled. OCR output (above) adds broken columns, merged header fields, `O10`/`QID`, `126.99`/`I26.99`. Gap: frequency enum lacks `nocte`, `mane`, `BD`, `QID PRN` mappings (already map to `1x/day`, `2x/day`, `as needed`); lab `flag` (H/L) would be useful. Note one generator artefact ("hormonal contraception" in a male patient). NC licence is fine for coursework, not for commercial use.

**4. Primock57.** Transcripts carry `<UNSURE>` / `<UNIN/>` tags and disfluencies; the doctor's own note is real GP shorthand, a second messy input type on its own:
```
3/7 hx of diarrhea, mainly watery. ... Opening bowels x6/day. Associated LLQ pain
PMH: Asthma  DH: Inhalers ... Nil smoking/etOH hx   Imp: gastroenteritis
```
Run Whisper on the audio to get genuine ASR errors. Doses are rare, ages often unstated. Actors, not patients.

**5. African Medical Records.** Nursing charts with column tables as text, visit forms, lab request forms (`Indication for Investigation: URGENT!!`), prescriptions, local shorthand (`PC:`, `SR: NS, GI System, RS all normal`, `GCS - 13/5`). Tesseract returns **nothing** on these scans, so you need a vision model as the OCR step, which makes the pipeline two-stage. The transcriptions alone are only moderately dirty. Card says "synthesized/volunteer-produced"; it contains realistic names, so treat it as sensitive.

**6. Synthetic dictation.** The `script` column is what was spoken: `vedolizumab two milligrams three times daily ... Alkaline phosphatase is one hundred twenty four point seven ... period`, with `terms` labelling drugs, doses, diagnoses, labs and age, which is close to a free draft label. Spoken numbers already make it harder; Whisper on the `hard` condition adds real ASR errors. Synthetic text, so it measures robustness more than realism.

**7-12, short.** GraSCCo: German radiology and discharge letters, real style (`dikt. Arzt`, `7,6 cm x ca. 3,5 cm große hypodense tumoröse RF`) but tidy; good only for a German slice. ru_med_history: genuinely dirty (lost `ё` gives `лгких`, `отк`; several diary entries merged; `1 0, 5 см`) but has no licence and comes from textbooks, so use it at most for internal tests. Eka parsing set: real lab printouts, the closest to category 1 on the Hub, but images only and gated, so not inspected here. MIMIC: **warning**, `dischargesum/discharge` (98k notes with `subject_id`/`hadm_id`), `hiimivantang/mimic-iv-notes`, `stabgan/cleaned_discharge_note_120k` and similar are **ungated re-uploads of MIMIC-IV-Note**; using them breaks the PhysioNet DUA. If you get credentialed access, PhysioNet also forbids sending notes to LLM APIs that retain data, which rules out most hosted model comparisons.

## Top 5

1. **ACI-Bench raw ASR**: the only open set with true ASR output of full doctor-patient encounters, CC BY, maps to every field, and the reference note helps a human check labels.
2. **RuMedPrime**: real records, real template junk, Cyrillic (closest to the Ukrainian slice you already have), CC BY, short so cheap to label; the ICD-10 column is a free check on diagnoses.
3. **Australian scanned PDFs + your own OCR**: real OCR damage on numbers and frequencies, exactly where the scorer is strict; ground truth covers 4 of 8 fields.
4. **Primock57**: small but real clinician shorthand plus audio for ASR; good add-on to #1.
5. **African Medical Records**: real handwriting, but adds an OCR model to the comparison, which mixes two error sources.

## Recommendation

Add **two slices, 40 documents total**:

- **ACI-Bench ASR, 15 encounters** (from `test1/test2_aci_asr` and `*_virtscribe_asr`, prefer ones that mention medications with doses). Labelling: 15 to 25 min each (read ~1,000 words, resolve swapped speakers and dose corrections), about **5 h**.
- **RuMedPrime, 25 visits**, stratified by ICD-10 chapter, half chosen to contain `мг` or `=` (meds or labs). Labelling: 5 to 8 min each, about **3 h**. Diagnoses translated to English lowercase, ICD-10 used only as a check.

Optional third slice: **10 Australian PDFs** (fax/poor variants) OCR'd with Tesseract at 150 dpi; draft from `ground_truth.jsonl` for age, sex, diagnosis, meds, then add labs, urgency, follow-up by hand: about 10 min each, **under 2 h**. Keep the OCR text fixed in `data/raw/` so every model sees the same input.

Golden-label protocol without seeds: the human labels the first 5 items of each slice from scratch to fix conventions (how to treat stopped meds, negated diagnoses, `nocte`/`mane`), writes them into the README, then labels the rest. Do not let one evaluated model draft the labels; if you want drafts, take two different models and have the human resolve every field where they disagree and spot-check the rest. A second pass on 5 items a week later gives a self-agreement figure for the report. Total effort: **about 8 to 10 hours** for 40 to 50 items. Decide the schema extensions (transcript `report_type`, optional `icd10`, lab `ref_range`/`flag`, med `status`) before labelling, or label to the current schema and record the gaps as findings.

## What does not exist (stop searching)

- **Ukrainian clinical notes:** none on the Hub or the open web. Published Ukrainian medical corpora (UKRMED, Lviv Polytechnic NER corpus, Grabar et al. aligned corpus) are protocols, blogs, Wikipedia or translations, not patient records. Hub search for Ukrainian medical terms returns nothing.
- **Polish and Czech clinical notes:** nothing on the Hub beyond exam questions. German real notes (BRONCO) need a signed DUA and must be deleted after 12 months.
- **OCR text of modern scanned medical documents:** the only text-form set (`jason1966/...medical-document-ocr-text-dataset`, 16.5k rows) is random word salad with fake typos. Everything else is images; you produce the OCR text yourself.
- **Handwritten prescriptions with full-document transcriptions:** HF sets (`avi-kai/...Handwritten_Words`, `tavishm/100-handwritten-medical-records`) are word crops or images without text; AMR is the only one with page transcriptions.
- **Real-patient ASR conversations:** none are public; all open sets (ACI-Bench, Primock57, MTS-Dialog) are role-played. The many `*/doctor-patient-conversations-*` and `omi-health` sets are LLM-generated.
- **Legal open MIMIC notes:** none; every ungated copy on the Hub is a licence violation.
