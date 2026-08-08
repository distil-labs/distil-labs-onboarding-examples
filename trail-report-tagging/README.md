# trail-report-tagging

A worked trace directory for a **traces-to-model** build: multi-label tagging expressed as
`question-answering`. Where `incident-triage` starts from a labeled dataset, this one starts
from production traces, so it exercises trace processing, teacher relabelling, and the
original-model baseline that a traces build adds as an extra gate.

It is a **partial success, shipped as one**. Tuning takes `Qwen3-0.6B` from 0.044 to 0.556
and past the production model it replaces, but nowhere near the teacher's 0.889. The reason
is known and documented below.

`traces-input/` is the trace directory as the stages expect it — submit it as-is
as a trace input, unchanged. Regenerate the traces with
`python generate_traces.py --count 500`.

## The task

One free-text trail condition report in, one JSON list of applicable tag codes out:

```
IN:  PATROL NOTE 2026-July 19 | segment length 8.4 mi
     Patrol observed mosquitoes were brutal the entire way. Patrol observed the footbridge
     at the lower crossing is gone entirely. Patrol observed the trailhead lot was full early.
OUT: {"tags": ["BRIDGE_OUT"]}
```

All 48 codes and their definitions live in `task_description`, so teacher, base student and
tuned student see identical information:

| Step | Rule |
|---|---|
| Vocabulary | 48 codes across 4 families — `IMPASSABLE` (8), `OBSTRUCTION` (14), `SEASONAL` (14), `COMFORT` (12) — verbatim only |
| Definitions | Near-neighbours split **only** by definition, never by surface words |
| → `WATER_LOW` | sources are dry, **not** a creek running low |
| → `WATER_CARRY_LONG` | sources are far apart, **not** dry |
| → `RUNOFF_ON_TREAD` | water on the trail, no structure at fault |
| → `DRAIN_BLOCKED` | a failed drainage structure |
| **The override** | any `IMPASSABLE` tag → the answer is **only** the `IMPASSABLE` tags |
| Empty set | nothing applies → `{"tags": []}` |
| Decoys | every report carries a date and a mileage figure; neither ever affects the tags |

The example above is the override working: the bugs and the full car park are both stated
plainly and both correctly dropped. Reports arrive in five registers (trailhead logbook,
first-person trip report, ranger patrol note, crew work report, satellite message), and
judging compares tag **sets**, ignoring order — set equality is the correct metric for
multi-label.

Every threshold is qualitative: `BLOWDOWN_HEAVY` is "climbed over" against
`BLOWDOWN_LIGHT` "stepped over", never a tree count.

## Why a base model fails it

Four independent failure modes, so the gap does not rest on any one rule:

1. **A vocabulary it cannot recall.** 48 arbitrary codes in the prompt. The base model
   invents codes that do not exist — `SNOW_LOAD`, `STILE_JAMMED`, `GULLYING`,
   `WILDFLOWERS_PEEVING`. The teacher does this zero times.
2. **Over-tagging.** The characteristic multi-label failure, and it worsens as the
   vocabulary grows.
3. **The override.** Small models list everything they noticed instead of suppressing.
4. **The empty set.** They reach for the nearest tag rather than returning nothing.

Format is *not* one of them: even the base model gets bare JSON out. That separation is
useful — it says the fix is coverage per code, not prompt or format work.

## Results

45-row generated test set, primary metric `llm-as-a-judge`. Per-tag micro-F1 is computed
from the predictions file; `/metrics` reports exact-set only.

| Model | exact-set | across runs | per-tag F1 |
|---|---|---|---|
| Base `Qwen3-0.6B` | 0.044 | 0.03-0.05 | — |
| Tuned — 512 examples, 1 epoch, batch 1 | 0.422 | — | 0.617 |
| Tuned — 1000 examples, 1 epoch, batch 1 | 0.467 | — | 0.634 |
| Tuned — 512 examples, 3 epochs, batch 1 | 0.511 | — | **0.725** |
| **Tuned — 1000 examples, 4 epochs, batch 8** (shipped config) | **0.556** | 0.48-0.56 | 0.683 |
| Original production model, from the traces | 0.444 | 0.44-0.58 | — |
| Teacher `openai.gpt-oss-120b` | 0.889 | 0.86-0.89 | 0.950 |

The tuned model clears the original-model gate. It does not approach the teacher.

**This example varies more than the other two, and the reason is worth knowing.** Trace
processing regenerates the test set on every run, so each run scores against different rows —
unlike the other examples, which ship a fixed `test.jsonl`. The original-model baseline moves
most of all, because it is measured on that regenerated set. Read the gap between the tuned
model and the baseline *from the same run*; comparing either against a number from a different
run is meaningless here.

Trace processing ~17 min, teacher eval ~4 min, synthgen ~6 min, training ~15 min.

Trace processing yields 20 train / 45 test / 350 unstructured from 500 traces: relabelling
loses 55-60% of traces to a platform-side malformed-request fault. The loss is random rather
than biased — survivors track the source tag-count distribution within a few points — and
relabel accuracy on the survivors is 90-98%.

## Files

| File | Notes |
|---|---|
| `generate_traces.py` | Emits `traces.jsonl` **and** `job_description.json` from one `TAXONOMY` constant |
| `traces-input/traces.jsonl` | 500 traces; legacy answers score 0.61 exact-set before relabelling |
| `traces-input/job_description.json` | The 48-code taxonomy, the four rules, plus judge, synthgen and relabel instructions |
| `traces-input/config.yaml` | `Qwen3-0.6B`, `gpt-oss-120b`, 1000 generated, 4 epochs, batch 8, `output_is_json`, a 6 x 5 mutator grid |

## Four things to know if you adapt this

**48 codes is too many for a 0.6B.** The headline lesson. Taxonomy size and a small student
at a low epoch budget are in direct tension, and ~16 codes would be learnable at this budget.
The platform's recommended default student is 4B-class, with 0.6B a cost-sensitive
choice; this example is evidence for that advice.

**Epochs beat data roughly 6:1.** Three epochs on the same data lifted per-tag F1 by +0.108;
doubling the data at one epoch lifted it by +0.017. Invented codes are the tell — doubling
the data made them *worse* (5 → 7 failures) while tripling the epochs made them better and
reduced the survivors to near-misses of real codes, including `Cairn_MISSING`, which is the
right code with the wrong casing. Repeated passes memorise a vocabulary; more single-pass
examples do not.

**Restate the override in `synthetic_data_generation_instructions`.** Left at defaults here,
which produced a ~10% override violation rate in the generated training data — and override
misses were the one error class that stayed flat (4-5 of 45) across all four training runs
while everything else improved. That is a data-quality ceiling no training lever clears, and
it is the first thing to fix. It needs no re-processing: a `job_description` override on
`POST /training-datasets/from-seed-datasets` reaches synthgen while leaving `task_description`
untouched.

**Never give two tags phrasings built on the same word.** `AVALANCHE_DEBRIS` and
`WASHOUT_MAJOR` were both given a phrasing using a bare "slide", which accounts for 2 of the
teacher's 5 errors and therefore lowers the ceiling everything else distills from. Say
"avalanche" and "landslide" explicitly.
