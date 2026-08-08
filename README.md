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

## What makes these tasks work

Every one is built so a base model cannot guess its way through:

- **Invented mappings.** Nothing in pretraining knows that `sso-gw` means `authentication`.
- **An exception rule** that overrides the signal a model would otherwise key on, so reading
  the obvious feature is wrong every time.
- **Decoy fields** — counts, dates, weights — that look meaningful and never affect the answer.

That construction is the point. A task a base model can half-guess produces a gap you cannot
trust, whatever the score says.

The `trail-report-tagging` README is worth reading even if traces are not your starting point:
it is the one that did **not** reach the teacher, and it says why.

## Using them

Each directory is a job input in the shape the platform expects. Submit it unchanged to
reproduce the numbers, or copy one as the skeleton for your own task.

Two of the three ship the generator that produced their data — `generate_input.py` and
`generate_traces.py` — so you can see how the rules, the decoys and the test set were
constructed, and adapt the same shape to your own domain.

**Expect the numbers to move.** Generation and judging both run at non-zero temperature, so a
rerun will not reproduce them to the decimal. Each README gives the range measured across
several runs; treat a difference inside that band as noise.

## Building your own

The workflow these examples were built with lives in the
[building-models skill](https://github.com/distil-labs/building-models-skill), which covers
preparing data, evaluating a teacher, generating synthetic data, training, and deployment.
