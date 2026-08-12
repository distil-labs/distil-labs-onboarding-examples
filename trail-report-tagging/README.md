# trail-report-tagging

## What it does

A trail condition tagging service. It reads one free-text field report written by somebody who
walked a section of trail and returns the standard condition tags that apply, as a JSON list.
Tagged reports can be searched, mapped and rolled up; the raw prose cannot.

## Why this needs a model

This one is a language task outright, and no rule replaces it. The tags turn on meaning rather
than on words. "The sources are dry" is `WATER_LOW`; "the sources are far enough apart that you
have to carry" is `WATER_CARRY_LONG`. The two share no keyword, and a reporter writing in their
own words uses neither phrasing twice. Every threshold is qualitative as well: heavy blowdown is
timber you climb over, light blowdown is timber you step over, and no tree count decides it.

The question is therefore not whether to use a model but which one. There is already a
production service doing this job, and it is wrong often enough to matter — it over-tags, it
refuses to return an empty list, and it ignores the suppression rule. Its logged traffic is the
input to this example: the traces go in, the teacher relabels them, and a 0.6B student is
trained to replace the service that produced them.

```
                            /\
                       /\  /  \           /\
                  /\  /  \/    \     /\  /  \
             /\  /  \/          \___/  \/    \  /\
       _____/  \/                               \/  \_____

                        .---------------.
                        |   TRAIL  7    |
                        |   bridge  X   |
                        '-------+-------'
       - - - - - - - - - - - - -+- - - - - - - - - - - - -

        "The footbridge at the lower crossing is gone entirely."
                                |
                                v
                      {"tags": ["BRIDGE_OUT"]}
```

## The task in detail

A worked trace directory for a **traces-to-model** build: multi-label tagging expressed as
`question-answering`. Where `incident-triage` starts from a labeled dataset, this one starts
from production traces, so it exercises trace processing, teacher relabelling, and the
original-model baseline that a traces build adds as an extra gate.

It is a **partial success, shipped as one**. Tuning lifts `Qwen3-0.6B` past the production
model it replaces, but leaves it well short of the teacher. The reason is known and
documented below.

`traces-input/` is the whole example. Submit it as a trace input, unchanged. There is nothing
to generate first and no input format to choose.

One free-text trail condition report in, one JSON list of applicable tag codes out:

```
IN:  Trip report, 2026-July 19. We covered 8.4 miles out and back. Mosquitoes were brutal
     the entire way. The footbridge at the lower crossing is gone entirely. The trailhead
     lot was full early.
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
plainly and both correctly dropped. Judging compares tag **sets**, ignoring order — set
equality is the correct metric for multi-label.

Every input is a first-person trip report, and no other register appears:

```
Trip report, <date>. We covered <n> miles out and back. <one sentence per condition, in the
reporter's own words, mixed with incidental detail that carries no tag>
```

The date and the mileage figure are decorative — neither ever affects the tags.

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

**This example varies more than the other two, and the reason is worth knowing.** Trace
processing regenerates the test set on every run, so each run scores against different rows —
unlike the other examples, which ship a fixed `test.jsonl`. The original-model baseline moves
most of all, because it is measured on that regenerated set. Read the gap between the tuned
model and the baseline *from the same run*; comparing either against a number from a different
run is meaningless here.

Relabelling loses well over half the traces to a platform-side malformed-request fault, so 500
traces yield a small train split and a test split of a few dozen rows. The loss is random
rather than biased: the survivors track the source tag-count distribution closely.

## Files

| File | Notes |
|---|---|
| `traces-input/traces.jsonl` | 500 traces, each one a trip report with the legacy service's answer |
| `traces-input/job_description.json` | The 48-code taxonomy, the four rules, plus judge, synthgen and relabel instructions |
| `traces-input/config.yaml` | `Qwen3-0.6B`, `gpt-oss-120b`, 1000 generated, 4 epochs, batch 8, `output_is_json`, a 6-topic mutator list |

Three files, one directory, nothing to run first.

## Five things to know if you adapt this

**48 codes is too many for a 0.6B.** The headline lesson. Taxonomy size and a small student
at a low epoch budget are in direct tension, and ~16 codes would be learnable at this budget.
The platform's recommended default student is 4B-class, with 0.6B a cost-sensitive
choice; this example is evidence for that advice.

**Epochs beat data by a wide margin.** Tripling the epochs on the same data lifted per-tag F1
several times more than doubling the data at one epoch did. Invented codes are the tell —
doubling the data made them worse, while tripling the epochs made them better and reduced the
survivors to near-misses of real codes, such as `Cairn_MISSING`, which is the right code with
the wrong casing. Repeated passes memorise a vocabulary; more single-pass examples do not.

**Restate the override in `synthetic_data_generation_instructions`.** It is left at defaults
here, and a measurable share of generated rows carrying an IMPASSABLE tag violate the override
themselves. Override misses are then the one error class that stays flat across training runs
while everything else improves. That is a data-quality ceiling no training lever clears, and it
is the first thing to fix. It needs no re-processing: a `job_description` override on
`POST /training-datasets/from-seed-datasets` reaches synthgen while leaving `task_description`
untouched.

**Never give two tags phrasings built on the same word.** `AVALANCHE_DEBRIS` and
`WASHOUT_MAJOR` were both given a phrasing using a bare "slide", which cost the teacher
several rows and therefore lowered the ceiling everything else distills from. Say "avalanche"
and "landslide" explicitly.

**Keep one input register.** Every report is a first-person trip report. Mixing registers
spreads a fixed generation budget across formats instead of across the 48 codes, and code
coverage is the binding constraint here.
