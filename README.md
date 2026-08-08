# Distil Labs onboarding examples

Three complete, worked examples of small models built on the
[distil labs](https://distillabs.ai) platform. Each one is a directory you can submit as-is:
the data, the job description, and the config that produced the numbers below.

They exist to answer one question — *what does a task that distils well actually look like?* —
because the shape of the task matters far more than any setting.

| Example | Task type | Base → tuned | Teacher | Pipeline |
|---|---|---|---|---|
| [`incident-triage`](incident-triage/) | `question-answering` | 0.60 → **0.98** | 1.00 | ~21 min |
| [`bindery-defect-triage`](bindery-defect-triage/) | `classification` | 0.20 → **1.00** | 1.00 | ~15 min |
| [`trail-report-tagging`](trail-report-tagging/) | `question-answering`, from production traces | 0.04 → **0.56** | 0.89 | ~42 min |

All three distil `Qwen3-0.6B` from `openai.gpt-oss-120b`.

## What each one shows

**`incident-triage`** — one raw log line in, one incident record out. A closed rule system with
an alias table, an ordered rule table where first match wins, and one exception rule that
overrides the obvious signal. The clearest illustration of a task a small model learns
completely.

**`bindery-defect-triage`** — one defect report in, one routing label out. Five classes, and a
base model that scores exactly chance because it collapses to a single label. Shows what
classification looks like when the label boundaries are genuinely unguessable.

**`trail-report-tagging`** — free-text field reports in, a list of tag codes out, built from
**production traces** rather than a curated dataset. It is shipped as an honest partial
success: tuning beats the production model it replaces but lands well short of the teacher, and
the README explains exactly why.
