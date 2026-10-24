# Golden set status

Each row is a golden item. `verified` is flipped to yes by a human after reading
`data/raw/{id}.txt` next to `data/golden/{id}.json` and correcting the JSON if needed.

| id | type | lang | length | age | sex | meds | labs | urgency | verified |
|---|---|---|---|---|---|---|---|---|---|
| 004 | discharge | mixed | medium | null | male | 1 | 0 | urgent | yes |
| 016 | discharge | en | long | null | female | 2 | 4 | soon | yes |
| 023 | consult | en | long | 41 | male | 3 | 3 | soon | yes |
| 027 | progress_note | mixed | medium | 34 | female | 2 | 2 | routine | yes |
| 032 | consult | en | long | null | unknown | 2 | 3 | urgent | yes |
| 034 | lab | uk | medium | null | female | 2 | 1 | urgent | yes |
| 035 | radiology | uk | short | 59 | female | 0 | 0 | routine | yes |
| 037 | consult | uk | long | null | male | 3 | 0 | routine | yes |
| 038 | referral | mixed | medium | null | male | 1 | 0 | routine | yes |
| 048 | consult | en | long | null | unknown | 4 | 3 | soon | yes |

## Corrections log

- 2026-10-24, 032: `patient_sex` female -> unknown. The text never states the patient's sex; the only "her" refers to the patient's mother. Seed said female; the generated text did not express it, and the text wins.
- 2026-10-24, 048: `patient_sex` male -> unknown. Same situation: the only "his" is "Father: died suddenly in his 50s".
- Convention confirmed by these two cases: sex is labelled only when the text states or grammatically implies the patient's own sex (pronoun for the patient, Mr/Mrs, gendered noun such as "пацієнтка", gendered verb form in Ukrainian). Relatives' pronouns do not count.
