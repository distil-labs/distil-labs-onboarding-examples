# Distil Labs onboarding examples

Three complete, worked examples of small models built on the
[distil labs](https://distillabs.ai) platform. Each one is a single directory you submit as-is:
the data, the job description, and the config. There is nothing to generate first, no script to
run, and no input format to choose.

They exist to answer one question — *what does a task that distils well actually look like?* —
because the design of the task matters far more than any setting.

```
         openai.gpt-oss-120b                     Qwen3-0.6B
       .----------------------.              .----------------.
       |                      |  synthetic   |                |
       |       TEACHER        |--- data  --->|     STUDENT    |
       |                      |  + tuning    |                |
       '----------------------'              '----------------'
           solves the task                    runs on every line,
           too big to deploy                  at a fraction of the cost
```

| Example | Task type | Input directory | Input format |
|---|---|---|---|
| [`incident-triage`](incident-triage/) | `question-answering` | `base-input/` | one logfmt log line |
| [`bindery-defect-triage`](bindery-defect-triage/) | `classification` | `base-input/` | one `stn_qa` logfmt line |
| [`trail-report-tagging`](trail-report-tagging/) | `question-answering`, from production traces | `traces-input/` | one first-person trip report |

All three distil `Qwen3-0.6B` from `openai.gpt-oss-120b`.

## How to run one

Submit the example's input directory as a job input. Every example has exactly one input
directory and one way to run it.

## What each one shows

**`incident-triage`** — one raw log line in, one incident record out. A closed rule system with
an alias table, an ordered rule table where first match wins, and one exception rule that
overrides the obvious signal. The clearest illustration of a task a small model learns
completely.

**`bindery-defect-triage`** — one defect report from a book bindery in, one routing label out. A
bindery is a factory that binds printed pages into books. Five classes, and a base model that
scores exactly chance because it collapses to a single label. Shows what classification looks
like when the label boundaries are genuinely unguessable.

**`trail-report-tagging`** — free-text trip reports in, a list of tag codes out, built from
**production traces** rather than a curated dataset. It is shipped as an honest partial
success: tuning beats the production model it replaces but lands well short of the teacher, and
the README explains exactly why.
