# distil labs onboarding examples

Three worked examples of small models built on the [distil labs](https://distillabs.ai)
platform. The [onboarding](https://distillabs.ai/docs/onboarding) runs one of them end to end,
from production traffic to a trained model that serves that traffic behind an inference
endpoint. Each example is one directory with the data, the job description and the config.

They show what a task that distils well looks like: the design of the task matters far more
than any setting.

```
        teacher (GLM 5.3)                      student (Qwen3.5)
       .----------------------.              .----------------.
       |                      |  synthetic   |                |
       |       TEACHER        |--- data  --->|     STUDENT    |
       |                      |  + tuning    |                |
       '----------------------'              '----------------'
           solves the task                    runs on every line,
           too big to deploy                  at a fraction of the cost
```

| Example | Task type | Starts from | Teacher | Student |
|---|---|---|---|---|
| [`bindery-defect-triage`](bindery-defect-triage/) | `classification` | a labeled dataset, `base-input/` | `zai.glm-5.3-flash-low-thinking` | `Qwen3.5-0.8B` |
| [`incident-triage`](incident-triage/) | `question-answering` | a labeled dataset, `base-input/` | `zai.glm-5.3-flash-low-thinking` | `Qwen3.5-0.8B` |
| [`trail-report-tagging`](trail-report-tagging/) | `question-answering` | production traffic, `traces-input/` | `zai.glm-5.3-low-thinking` | `Qwen3.5-2B` |

The settings trade a little accuracy for speed: the teachers and students are the fastest ones
that solve each task, and every job runs with 32 parallel LLM requests and a training batch of 8.

## How the examples run

- **`bindery-defect-triage`, `incident-triage`:** create a seed dataset from `base-input/`, then
  teacher evaluation, synthetic data generation and training. The trained model is deployed
  behind an inference endpoint.
- **`trail-report-tagging`:** the full loop. An inference endpoint with `openai/gpt-oss-120b` as
  its fallback receives the production traffic in `traces-input/traces.jsonl`. Its records become
  the traces, a test set and a seed dataset are built from them, and the trained model goes
  behind a new endpoint that serves the same traffic.

## Scripts

| Script | What it does |
|---|---|
| `replay_traffic.py` | Sends the rows of a JSONL file to an inference endpoint, the way an application would. `--client <model_client.py>` sends them through a trained model's own client |
| `records_to_traces.py` | Converts the records from `distil inference-endpoint download-traces` into a trace file |

Both run with `uv run <script> --help`, or with `python3` after `pip install openai`.
