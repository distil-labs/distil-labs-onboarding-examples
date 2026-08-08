# incident-triage

A worked job-input directory for a `question-answering` build, sized so the whole pipeline
runs in about 21 minutes on the fast path (about 35 with the prescribed smoke runs). A base
`Qwen3-0.6B` fails the task; 512 synthetic examples and one epoch take it to the teacher's
score.

`base-input/` is the input directory as the stages expect it — submit it as-is
as a job input, unchanged.

## The task

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

Inputs arrive in four log formats (logfmt, bracketed, syslog, JSON line), and every line
carries an event `count` that is decorative — it never affects the answer.

## Why a base model fails it

Three independent failure modes, which is what makes the gap robust:

1. **Unguessable mappings.** Nothing in pretraining says `sso-gw` means `authentication`.
2. **An exception rule.** Rule 1 overrides the level, so a FATAL authentication line is S2,
   not S1. A model reading the level is wrong every time.
3. **Format discipline.** Small models wrap JSON in prose and markdown fences.

The test set over-samples exactly these cases: authentication at FATAL and INFO, and
high-count lines on components where the count does not matter.

## Results

50-row test set, primary metric `llm-as-a-judge`:

| Model | llm-as-a-judge | across runs |
|---|---|---|
| Base `Qwen3-0.6B` | 0.60 | 0.58-0.68 |
| **Tuned `Qwen3-0.6B`** | **0.98** | 0.98-1.00 |
| Teacher `openai.gpt-oss-120b` | 1.00 | 1.00 |

The tuned student reaches the teacher within a row: 49/50 against the teacher's 50/50.

**Expect variation.** Generation and judging both run at non-zero temperature, so a rerun of
this directory will not reproduce these numbers to the decimal — the third column is the range
measured across five runs. On 50 rows one point is 0.02, so a 0.04 difference is two rows and
inside the noise.

**Epochs rise with batch size.** This config trains at `per_device_train_batch_size: 8`, which
divides the optimizer-step count by eight, so it also sets `num_train_epochs: 4`. At one epoch
the same data reaches only 0.88. If you raise the batch size further, raise the epochs with
it.

Timings, one measured run: teacher eval 2.9 min, synthgen 4.3 min, training 13.5 min — about
21 minutes on the fast path. Adding the prescribed smoke runs takes it to about 35 minutes of
job time.

## Files

| File | Notes |
|---|---|
| `base-input/config.yaml` | `Qwen3-0.6B`, `gpt-oss-120b`, 512 generated, 4 epochs at batch 8, `output_is_json`, a component × level mutator grid |
| `base-input/job_description.json` | the rule table, the input spec, and the judge criteria |
| `base-input/train.jsonl` | 20 seed rows |
| `base-input/test.jsonl` | 50 test rows |

The 24-cell mutator grid is wider than a 64-example smoke can populate, so read its coverage on
the full run rather than the smoke.

## Two things to preserve if you adapt this

**Keep the task narrow.** The catalog's default student is 4B; 0.6B works here only because
this is a small closed rule system.

**Do not add arithmetic.** An earlier version escalated authentication to S1 above a count of
5000. The student plateaued at 0.86 with 6 of its 7 errors on that one rule — it could hold
the exception or the numeric comparison, but not both. Removing the threshold while keeping
the override took it to 1.00. The teacher scored 1.0 throughout, so the ceiling was never the
problem.
