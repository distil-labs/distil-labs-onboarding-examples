# bindery-defect-triage

A worked job-input directory for a `classification` build — the first example of that task type
in this repo — sized so the whole pipeline runs in about 15 minutes on the fast path (about 24
with the prescribed smoke runs). A base `Qwen3-0.6B` collapses to a single label and scores
chance; 555 synthetic examples and 4 epochs take it to the teacher's score.

`base-input/` is the input directory as the stages expect it — submit it as-is
as a job input, unchanged.

## The task

One QA inspection line from a book-bindery finishing floor in, one disposition label out:

```
IN:  [BINDERY-QA] defect=<panel-skew> severity=<major> :: lot L-12083 shift=swing units=807
OUT: mark_and_pass
```

`panel-skew` resolves to the `stamping` station, and rule 1 sends every stamping line to
`mark_and_pass` whatever the severity says. The rules are invented, so no model can know them in
advance:

| Step | Rule |
|---|---|
| Station | 30 defect aliases map to 6 canonical stations |
| Disposition | ordered table, **first match wins** |
| → Rule 1 | `stamping` → **`mark_and_pass` always**, overriding the severity |
| → Rule 2 | `gluing`/`casing` at critical or major → `quarantine_lot` |
| → Rule 3 | critical → `rebind_unit` |
| → Rule 4 | major → `rework_signature` |
| → Rule 5 | minor → `press_and_hold` |
| → Rule 6 | trace → `mark_and_pass` |

Six of the 30 aliases point at a station their wording contradicts — `spine-void` is `trimming`,
not gluing; `foil-void` is `gathering`, not stamping; `board-slip` is `folding`, not casing;
`head-nib` is `gluing`, `crossfold` is `casing`, `panel-skew` is `stamping`. Ten of the 50 test
rows carry one.

Inputs arrive in four formats (logfmt station line, bracketed QA line, free-text floor note,
JSON line), and every line carries `lot`, `op`/`operator`, `press`, `shift` and `units` — all
decorative. A unit count in the hundreds never escalates anything.

## Why a base model fails it

Three independent failure modes, which is what makes the gap robust:

1. **Unguessable mappings.** Nothing in pretraining says `NF-5` means `casing`, and the six
   contradictory aliases actively punish reading the alias as words.
2. **Two exception rules.** Rules 1 and 2 both outrank the severity, and they decide **17 of the
   50 test rows**. A reader that resolves severity perfectly and ignores the station entirely
   caps at **33/50 = 0.66** — that is the ceiling on guessing, computed over this test set, not a
   model score.
3. **An invented label vocabulary.** `press_and_hold` versus `rework_signature` versus
   `rebind_unit` is not a taxonomy anything has seen, so nothing anchors severity to a code. In
   both measured runs the base model picked **one** label and applied it to all 50 rows
   (`mark_and_pass` recall 1.0, every other class 0.0) — exactly chance on a 5-way balanced set.

The test set is balanced 10 per class and over-samples exactly these cases: stamping at critical
and major, gluing and casing at critical and major, and the contradictory aliases.

## Results

50-row test set, 10 per class, primary metric `accuracy`:

| Model | accuracy | across runs |
|---|---|---|
| Base `Qwen3-0.6B` | 0.20 | 0.20, 0.20 |
| **Tuned `Qwen3-0.6B`** | **1.00** | 1.00, 1.00 |
| Teacher `openai.gpt-oss-120b` | 1.00 | 1.00, 1.00 |

`closed = (1.00 - 0.20) / (1.00 - 0.20) = 1.00` → Deploy candidate
— the whole base-to-teacher gap.

The tuned student matches the teacher on every class: precision, recall and f1 all 1.0 with
support 10, five classes out of five. Two independent full training runs over the same
TrainingDataset gave identical numbers.

**Expect variation.** Generation runs at non-zero temperature, so a rerun of this directory will
not reproduce the dataset row-for-row — but classification is scored by exact label match rather
than by a judge, so the score is less noisy than the QA examples' `llm-as-a-judge`. Both of my
full runs landed on 1.00 and both base evaluations on 0.20. On 50 rows one row is 0.02.

The synthetic data was clean enough to be worth recording: **0 label errors in 554 checkable
rows** when re-derived against the rule table, 0 malformed rows, 0 labels outside
`classes_description`, and class balance 110-112 per class. 3 rows in 555 (0.5%) named a station
in the input text, which `synthetic_data_generation_instructions` forbids; that is the one defect
rate worth watching if you adapt this.

Timings, measured: teacher eval 1.1 min, synthgen 1.8 min, training 10.8 and 13.4 min across the
two runs — about **15 minutes on the fast path**. Adding the prescribed smoke runs (synthgen
smoke 1.5 min, training calibration smoke 7.3 min) takes it to about **24 minutes** of job time.

## Files

| File | Notes |
|---|---|
| `base-input/config.yaml` | `Qwen3-0.6B`, `gpt-oss-120b`, 512 generated, 4 epochs at batch 8, a station × severity mutator grid, `num_few_shot_examples: 5` |
| `base-input/job_description.json` | the alias table, the ordered rule table, the input spec, and `classes_description` for the 5 labels |
| `base-input/train.jsonl` | 30 seed rows, 6 per class |
| `base-input/test.jsonl` | 50 test rows, 10 per class |
| `generate_input.py` | regenerates all four files; the rule table is executable here, so the labels are auditable |

The 24-cell mutator grid (6 stations × 4 severities) is wider than a 64-example smoke can
populate — it filled 19 of 24 cells on the smoke and **24 of 24** on the full run — so read its
coverage on the full run rather than the smoke.

Note there is no `llm_as_a_judge_instructions`: it is not valid for classification and the create
fails with it. Classification is judged by label accuracy.

## Three things to preserve if you adapt this

**Keep the label set small and the rules closed.** Five labels over a 24-cell station × severity
space is small enough for 0.6B; the catalog's default student is 4B and this works at 0.6B only
because the whole rule system fits on one page.

**Keep the decoys, and keep them uncorrelated.** `units` in the hundreds appears on rows of every
class. The moment a decoy correlates with the answer, the student learns the decoy and the gap
you measured stops meaning what you think it means.

**Do not add arithmetic.** The same lesson as `incident-triage`: this task deliberately has no
numeric threshold. The exception rules are pure lookups, and that is what a 0.6B student can hold
alongside a 30-entry alias table.

**Balance the test set by class, not by cell.** Uniform sampling over the 24 station × severity
cells puts 37.5% of the mass on `mark_and_pass`, which would let a degenerate single-label model
score 0.375 and flatter the base. Balanced 10-per-class, the same model scores 0.20, which is
what it deserves.
