# incident-triage

## What it does

An alert triage service. It reads one raw log line from a monitoring pipeline and returns one
incident record: how serious the event is, which system it belongs to, whether to wake somebody
up, and how long to suppress the duplicates that follow.

## Why this needs a model

The severity policy is a fixed table, so a script could apply it — if the input were already
parsed. It is not. Lines are free text written by whoever owns the service, they name that
service by one of 37 informal aliases, and the message body is prose. A regex pipeline over
that breaks every time a team renames a service or rewords a message, and it breaks silently.

A frontier model reads these lines correctly first time, but it is the wrong thing to run in
this position. Alerts arrive continuously, each line needs an answer in milliseconds, and the
per-call cost is paid thousands of times an hour, forever. This example moves that ability into
a 0.8B student: small enough to sit inside the alerting path, cheap enough to run on every line.

```
    2026-08-05T14:22:11Z WARN auth-svc msg="token refresh failed" count=847
                                  |
                                  v
                  .-------------------------------.
                  |  [!]  PAGE ONCALL             |
                  |-------------------------------|
                  |    severity            S2     |
                  |    component  authentication  |
                  |    suppress        30 min     |
                  |_______________________________|
                  |  o o o    [===============]   |
                  '-------------------------------'
```

## The task in detail

A worked job-input directory for a `question-answering` build. An untrained `Qwen3.5-0.8B`
fails the task; the config distils it from `zai.glm-5.3-flash-low-thinking` on 512 synthetic
examples.

`base-input/` is the whole example. Create the seed dataset from it unchanged. There is nothing
to generate first and no input format to choose.

One raw log line in, one incident record out:

```
IN:  2026-08-05T14:22:11Z WARN auth-svc pod=auth-7f9 msg="token refresh failed" count=847
OUT: {"severity": "S2", "component": "authentication", "action": "page_oncall", "suppress_minutes": 30}
```

The rules are invented, so no model can know them in advance:

| Step | Rule |
|---|---|
| Component | 37 service aliases map to 6 canonical components |
| Severity | ordered table, **first match wins** |
| → Rule 1 | `authentication` → **S2 always**, overriding the level |
| → Rule 2 | `database`/`payments` at ERROR or FATAL → S1 |
| → Rules 3-6 | FATAL→S1, ERROR→S2, WARN→S3, INFO→S4 |
| Action | S1/S2→`page_oncall`, S3→`ticket`, S4→`log_only` |
| Suppress | S1→0, S2→30, S3→120, S4→0 |

Every input is a single logfmt line, and no other format appears:

```
<iso timestamp> <LEVEL> <alias> msg="<message>" count=<n>
```

The `count` is decorative — it never affects the answer.

## Why a base model fails it

Three independent failure modes, which is what makes the gap robust:

1. **Unguessable mappings.** Nothing in pretraining says `sso-gw` means `authentication`.
2. **An exception rule.** Rule 1 overrides the level, so a FATAL authentication line is S2,
   not S1. A model reading the level is wrong every time.
3. **Output format discipline.** The input is uniform, but the output is JSON, and small
   models wrap JSON in prose and markdown fences.

The test set over-samples exactly these cases: authentication at FATAL and INFO, and
high-count lines on components where the count does not matter.

**Two mutators cover the rule table.** `component` and `level` generate every component at
every level, so the exception cases (authentication at FATAL, database and payments at ERROR)
appear often enough to learn. `synthetic_data_generation_instructions` restates that only
authentication is fixed at S2, so an ingest ERROR line is S2 by rule 4.

**Expect variation between runs.** Generation and judging both run at non-zero temperature, so
two runs of this directory will not score the same to the decimal. On 50 rows one row is 0.02,
so a 0.04 difference is two rows and inside the noise.

## Files

| File | Notes |
|---|---|
| `base-input/config.yaml` | `Qwen3.5-0.8B`, `zai.glm-5.3-flash-low-thinking` as teacher and judge, 512 generated, 4 epochs at batch 8, `output_is_json`, `component` and `level` mutators |
| `base-input/job_description.json` | the rule table, the input spec, and the judge criteria |
| `base-input/train.jsonl` | 20 seed rows |
| `base-input/test.jsonl` | 50 test rows |

Four files, one directory, nothing to run first.

## Three things to know if you adapt this

**Keep the task narrow.** The catalog's default student is 4B; 0.8B works here because this is
a small closed rule system.

**Keep one input format.** A mixed-format input set makes the student spend capacity on
parsing rather than on the rule table, and it gives you no way to tell a parsing error apart
from a rule error when you read the failures.

**Do not add arithmetic.** A rule such as "authentication above a count of 5000 is S1" asks
the student to hold an exception and a numeric comparison together, and a small student holds
one of the two. Keep the rules to lookups and orderings.
