# bindery-defect-triage

## What it does

A bindery is a factory that binds printed pages into finished books. The finishing floor is
where that happens, and a quality station there types one inspection line for every batch it
stops.

This is the defect triage service that reads those lines. One inspection line goes in, and one
disposition code comes out: what happens to the affected books. Rebind them, rework the
signature, press and hold, quarantine the lot, or mark and pass.

## Why this needs a model

The routing rules are a closed table, so a lookup would do — if the input were already parsed
and the vocabulary never moved. Neither holds. The defect names are the plant's own shorthand,
30 of them, and six read like a station they do not belong to: `spine-void` is a trimming
defect, not a gluing one. A hand-written lookup returns nothing the first time an operator
types an alias nobody added to it, and nothing is the most expensive answer on a production
line.

The floor also constrains where the model can run. Inspection lines arrive all shift, the
machine that reads them sits on the plant network, and per-line calls to a hosted frontier
model are neither fast enough nor cheap enough at that volume. A 0.6B student is small enough
to run beside the line.

```
         ___     ___     ___     ___     ___     ___
        |:::|   |:::|   |:::|   |:::|   |:::|   |:::|
        |:::|   |:::|   |:::|   |:::|   |:::|   |:::|
        |___|   |___|   |___|   |___|   |___|   |___|
     ======================================================>
                          ^
                    .-----+-----.
                    |  Q A  [*] |
                    '-----------'
       stn_qa defect=panel-skew sev=major lot=L-12083 units=807
                          |
                          v
                     mark_and_pass
```

## The task in detail

A worked job-input directory for a `classification` build — the only example of that task type
in this repo. A base `Qwen3-0.6B` collapses to a single label and scores chance; the config
distils it from `openai.gpt-oss-120b` on 512 synthetic examples.

`base-input/` is the whole example. Submit it as a job input, unchanged. There is nothing to
generate first and no input format to choose.

One QA inspection line in, one disposition label out:

```
IN:  stn_qa defect=panel-skew sev=major lot=L-12083 op=RB shift=swing press=3 units=807
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

Every input is a single logfmt line, and no other format appears:

```
stn_qa defect=<alias> sev=<severity> lot=<lot> op=<initials> shift=<shift> press=<n> units=<n>
```

Only `defect` and `sev` decide the answer. `lot`, `op`, `shift`, `press` and `units` are all
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
   `rebind_unit` is not a taxonomy anything has seen, so nothing anchors severity to a code. The
   characteristic base-model failure is to pick **one** label and apply it to all 50 rows —
   exactly chance on a 5-way balanced set.

The test set is balanced 10 per class and over-samples exactly these cases: stamping at critical
and major, gluing and casing at critical and major, and the contradictory aliases.

**Check the synthetic data before you train.** Classification labels are cheap to audit: re-derive
every generated label from the rule table and count the disagreements. Also count rows whose input
text names a station, which `synthetic_data_generation_instructions` forbids. That defect rate is
the one worth watching if you adapt this.

**Expect variation between runs.** Generation runs at non-zero temperature, so two runs of this
directory will not produce the dataset row-for-row. Classification is scored by exact label match
rather than by a judge, so the score is less noisy than the `llm-as-a-judge` examples. On 50 rows
one row is 0.02.

## Files

| File | Notes |
|---|---|
| `base-input/config.yaml` | `Qwen3-0.6B`, `gpt-oss-120b`, 512 generated, 4 epochs at batch 8, a station × severity mutator grid, `num_few_shot_examples: 5` |
| `base-input/job_description.json` | the alias table, the ordered rule table, the input spec, and `classes_description` for the 5 labels |
| `base-input/train.jsonl` | 30 seed rows, 6 per class |
| `base-input/test.jsonl` | 50 test rows, 10 per class |

Four files, one directory, nothing to run first.

The mutator grid has 24 cells (6 stations × 4 severities), which is wider than a 64-example smoke
run can populate, so read its coverage on the full run rather than the smoke.

Note there is no `llm_as_a_judge_instructions`: it is not valid for classification and the create
fails with it. Classification is judged by label accuracy.

## Five things to know if you adapt this

**Keep the label set small and the rules closed.** Five labels over a 24-cell station × severity
space is small enough for 0.6B; the catalog's default student is 4B and this works at 0.6B only
because the whole rule system fits on one page.

**Keep one input format.** Every line is `stn_qa`. A mixed-format input set makes the student
spend capacity on parsing rather than on the alias table, and it leaves you unable to tell a
parsing error apart from a rule error when you read the failures.

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
