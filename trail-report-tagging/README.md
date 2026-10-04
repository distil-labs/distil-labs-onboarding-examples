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
refuses to return an empty list, and it ignores the suppression rule. Its traffic is the input to
this example: the traces go in, the teacher relabels them, and a 2B student is trained to replace
the service that produced them.

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

A worked trace directory for a build that starts from production traffic: multi-label tagging
expressed as `question-answering`. The onboarding runs it as the full loop:

1. An inference endpoint with `openai/gpt-oss-120b` as its fallback stands in for the production
   service. `replay_traffic.py` sends it the 500 reports in `traces-input/traces.jsonl`: that file
   is the production traffic.
2. `distil inference-endpoint download-traces` fetches the records, and `records_to_traces.py`
   turns them into a trace file, uploaded with `traces-input/config.yaml` and
   `traces-input/job_description.json`.
3. `distil traces expand-test-set` relabels 200 traces into the test set and scores the
   production model on it. That score is the floor the student must beat.
4. Trace processing turns 200 of the remaining traces into the seed dataset, then teacher
   evaluation, synthetic data generation (1000 rows) and training follow.
5. The trained `Qwen3.5-2B` is deployed behind a new endpoint, with `openai/gpt-oss-120b` as
   fallback, and the same traffic goes through it.

The test set is fixed once step 3 has built it, so every later score in the loop is read on the
same rows. Relabelling keeps almost every trace.

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

**Expect variation between runs.** Relabelling, generation and judging all run at non-zero
temperature, so two runs do not score the same to the decimal. Compare the student with the
production model's score from the same test set.

## Files

| File | Notes |
|---|---|
| `traces-input/traces.jsonl` | 500 production calls: a trip report and the production service's answer. The onboarding replays these through an endpoint |
| `traces-input/job_description.json` | The 48-code taxonomy, the four rules, plus judge, generation and relabelling instructions |
| `traces-input/config.yaml` | `Qwen3.5-2B`, `zai.glm-5.3-low-thinking` as teacher, judge and relabelling teacher, 1000 generated, 4 epochs at batch 8, `output_is_json`, one `report_topic` mutator, a 200-row test set from traces |

## Five things to know if you adapt this

**48 codes need a larger student.** Taxonomy size and a small student at a low epoch budget are
in direct tension: a 0.6B student lands well short of the teacher on this taxonomy, which is why
this example trains a 2B one. The platform's recommended default student is 4B-class.

**Epochs beat data.** Repeated passes over the same data commit a vocabulary to memory, and more
single-pass examples do not. Invented codes are the tell: more epochs reduce them to near-misses
of real codes, such as `Cairn_MISSING`, the right code with the wrong casing.

**Check the override in the generated rows.** `synthetic_data_generation_instructions` restates
the IMPASSABLE override, and the large teacher applies it. Count the generated rows that carry an
IMPASSABLE tag and any other tag: override misses are a data-quality ceiling that no training
setting clears. Fix them in the generation instructions, or correct the rows and upload the
training data again.

**Never give two tags phrasings built on the same word.** `AVALANCHE_DEBRIS` and
`WASHOUT_MAJOR` were both given a phrasing using a bare "slide", which cost the teacher
several rows and therefore lowered the ceiling everything else distills from. Say "avalanche"
and "landslide" explicitly.

**Keep one input register.** Every report is a first-person trip report. Mixing registers
spreads a fixed generation budget across formats instead of across the 48 codes, and code
coverage is the binding constraint here.
