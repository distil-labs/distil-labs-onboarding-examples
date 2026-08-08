"""Build the bindery-defect-triage job-input directory.

Emits config.yaml, job_description.json, train.jsonl and test.jsonl into the target
directory, in the shape the distil labs platform expects for
`base.task: classification`.
"""

import argparse
import json
import random
from pathlib import Path

# --- The invented rule system -------------------------------------------------------------
# 30 defect aliases map onto 6 canonical stations. The mapping is arbitrary and six of the
# aliases point at a station their surface wording contradicts (marked below), so no model
# can deduce the table.
ALIASES = {
    "folding": ["K4", "QT-2", "ax-run", "dogear", "board-slip"],        # board-slip: reads casing
    "gathering": ["M9", "BR-7", "sigswap", "pin-miss", "foil-void"],    # foil-void: reads stamping
    "gluing": ["V3", "LX-8", "cold-bead", "ribbon-bleed", "head-nib"],  # head-nib: reads trimming
    "trimming": ["H6", "ZP-1", "short-cut", "foredge-wave", "spine-void"],  # spine-void: reads gluing
    "casing": ["D2", "NF-5", "hinge-gap", "case-warp", "crossfold"],    # crossfold: reads folding
    "stamping": ["T7", "WK-4", "blind-shift", "die-crush", "panel-skew"],   # panel-skew: reads folding
}

MISLEADING_ALIASES = ["board-slip", "foil-void", "head-nib", "spine-void", "crossfold", "panel-skew"]

SEVERITIES = ["critical", "major", "minor", "trace"]

CLASSES = [
    "rebind_unit",
    "rework_signature",
    "press_and_hold",
    "mark_and_pass",
    "quarantine_lot",
]

# Decoy field pools. None of these ever changes the label.
OPERATORS = ["RB", "DM", "TS", "KL", "JA", "MW", "PE", "HN", "GV", "OS"]
SHIFTS = ["day", "swing", "night"]

MUTATION_STATION_TOPICS = [
    "defects reported from the folding station",
    "defects reported from the gathering station",
    "defects reported from the gluing station",
    "defects reported from the trimming station",
    "defects reported from the casing station",
    "defects reported from the stamping station",
]

MUTATION_SEVERITY_TOPICS = [
    "lines reported at critical severity",
    "lines reported at major severity",
    "lines reported at minor severity",
    "lines reported at trace severity",
]

TASK_DESCRIPTION = """\
You triage defect lines from the finishing floor of a book bindery. Each input is ONE \
inspection line reported by a QA station. Output exactly one disposition code and nothing \
else: no explanation, no punctuation, no markdown.

Every line carries a defect alias and a severity word. Resolve the alias to its station with \
the alias table, then apply the disposition rules in order.

Alias table (30 aliases, 6 stations). The alias is arbitrary; do not infer the station from \
how the alias reads.
- folding: K4, QT-2, ax-run, dogear, board-slip
- gathering: M9, BR-7, sigswap, pin-miss, foil-void
- gluing: V3, LX-8, cold-bead, ribbon-bleed, head-nib
- trimming: H6, ZP-1, short-cut, foredge-wave, spine-void
- casing: D2, NF-5, hinge-gap, case-warp, crossfold
- stamping: T7, WK-4, blind-shift, die-crush, panel-skew

Severity words, worst first: critical, major, minor, trace.

Disposition rules, checked in order. The FIRST rule that matches decides the answer; stop \
there.
1. Station is stamping -> mark_and_pass. This holds at EVERY severity, including critical \
and major. Stamping is cosmetic foil work on this floor and is never escalated.
2. Station is gluing or casing, and severity is critical or major -> quarantine_lot.
3. Severity is critical -> rebind_unit.
4. Severity is major -> rework_signature.
5. Severity is minor -> press_and_hold.
6. Severity is trace -> mark_and_pass.

Lines arrive in four shapes: a logfmt station line, a bracketed QA line, a free-text \
finishing-floor note, and a JSON line. All four carry the same two decisive fields.

Every other field is bookkeeping and NEVER affects the disposition: lot, run, op, operator, \
press, shift, units, count. A high unit count does not escalate anything.

Example input:
  stn_qa defect=die-crush sev=critical lot=L-4471 op=RB press=3
Example output:
  mark_and_pass
"""

CLASSES_DESCRIPTION = {
    "rebind_unit": (
        "Rule 3. Severity is critical and the station is folding, gathering or trimming. "
        "Not for stamping (rule 1 takes it) and not for gluing or casing (rule 2 takes them)."
    ),
    "rework_signature": (
        "Rule 4. Severity is major and the station is folding, gathering or trimming. "
        "Not for stamping (rule 1) and not for gluing or casing (rule 2)."
    ),
    "press_and_hold": (
        "Rule 5. Severity is minor and the station is anything except stamping. Gluing and "
        "casing land here at minor severity because rule 2 only fires at critical or major."
    ),
    "mark_and_pass": (
        "Rule 1 or rule 6. Any stamping line at any severity, including critical and major; "
        "or a trace-severity line from any station except stamping."
    ),
    "quarantine_lot": (
        "Rule 2. Station is gluing or casing and severity is critical or major. This "
        "outranks rules 3 and 4, so a critical gluing line is quarantined, not rebound."
    ),
}

SYNTHGEN_INSTRUCTIONS = """\
Generate realistic single inspection lines from a book bindery finishing floor. Vary the four \
input shapes evenly: the logfmt station line (stn_qa defect=... sev=... lot=... op=... \
press=...), the bracketed QA line ([BINDERY-QA] defect=<...> severity=<...> :: lot ... \
shift=... units=...), the free-text finishing-floor note, and the JSON line. Draw defect \
aliases only from the 30 in the alias table and severities only from the four severity words.

Hard constraints on the generated input text:
- NEVER name the station (folding, gathering, gluing, trimming, casing, stamping) in the \
input. The alias is the only clue to it.
- NEVER name a disposition code in the input.
- Vary the bookkeeping fields widely: lot ids, operator initials, press numbers, shifts and \
unit counts, including counts in the hundreds. They are decoys and must never correlate with \
the answer.
"""

CONFIG_YAML = """\
base:
  task: classification
  student_model_name: Qwen3-0.6B
  teacher_model_name: openai.gpt-oss-120b
  # Throughput only.
  llm_num_parallel_requests: 64

evaluation:
  # 5 classes, and configuration.md says classification uses at least one few-shot example
  # per class, so the teacher sees one of each.
  num_few_shot_examples: 5

tuning:
  # Batch 8 divides the optimizer-step count by 8, so the epochs rise with it (both shipped
  # examples run 4 epochs at batch 8).
  num_train_epochs: 4
  per_device_train_batch_size: 8
  per_device_eval_batch_size: 8

synthgen:
  generation_target: 512
  generation_iteration_size: 128
  # The disposition rules key off station and severity only, so the mutator grid forces
  # exactly those two dimensions: every station is generated at every severity. Without this
  # the teacher under-produces the combinations that make the exception rules visible
  # (stamping at critical, gluing and casing at critical), and the student falls back to
  # reading the severity word alone.
  basic_mutators_to_use: []
  mutation_topics:
%(mutation_topics)s
"""


def disposition(station: str, severity: str) -> str:
    """The ordered rule table; first match wins."""
    if station == "stamping":
        return "mark_and_pass"
    if station in ("gluing", "casing") and severity in ("critical", "major"):
        return "quarantine_lot"
    if severity == "critical":
        return "rebind_unit"
    if severity == "major":
        return "rework_signature"
    if severity == "minor":
        return "press_and_hold"
    return "mark_and_pass"


def cells_by_class() -> dict[str, list[tuple[str, str]]]:
    """Every (station, severity) cell, grouped by the label it produces."""
    grouped: dict[str, list[tuple[str, str]]] = {name: [] for name in CLASSES}
    for station in ALIASES:
        for severity in SEVERITIES:
            grouped[disposition(station, severity)].append((station, severity))
    return grouped


def render_logfmt(alias: str, severity: str, rnd: random.Random, lot: str) -> str:
    return (
        f"stn_qa defect={alias} sev={severity} lot={lot} "
        f"op={rnd.choice(OPERATORS)} press={rnd.randint(1, 6)}"
    )


def render_bracketed(alias: str, severity: str, rnd: random.Random, lot: str) -> str:
    return (
        f"[BINDERY-QA] defect=<{alias}> severity=<{severity}> :: lot {lot} "
        f"shift={rnd.choice(SHIFTS)} units={rnd.randint(2, 940)}"
    )


def render_note(alias: str, severity: str, rnd: random.Random, lot: str) -> str:
    opener = rnd.choice(
        [
            "Finishing floor note",
            "QA walk note",
            "Bindery inspection note",
            "Line check",
        ]
    )
    return (
        f"{opener}: run {lot} came back with a {alias} at {severity} severity; "
        f"{rnd.randint(2, 940)} units affected, operator {rnd.choice(OPERATORS)}."
    )


def render_json(alias: str, severity: str, rnd: random.Random, lot: str) -> str:
    return json.dumps(
        {
            "defect": alias,
            "severity": severity,
            "lot": lot,
            "units": rnd.randint(2, 940),
            "op": rnd.choice(OPERATORS),
            "press": rnd.randint(1, 6),
        }
    )


RENDERERS = [render_logfmt, render_bracketed, render_note, render_json]


def build_row(station: str, severity: str, alias: str, renderer, rnd: random.Random,
              lot: str) -> dict:
    text = renderer(alias, severity, rnd, lot)
    return {
        "messages": [
            {"role": "user", "content": text},
            {"role": "assistant", "content": disposition(station, severity)},
        ]
    }


def station_of(alias: str) -> str:
    for station, aliases in ALIASES.items():
        if alias in aliases:
            return station
    raise KeyError(alias)


def build_split(rows_per_class: int, lot_prefix: int, seed: int,
                exception_weight: int) -> list[dict]:
    """Sample rows_per_class examples for each of the 5 labels.

    exception_weight biases cell choice toward the cells the exception rules own — stamping
    at critical/major, and gluing/casing at critical/major — so the test split over-samples
    exactly what a base model gets wrong.
    """
    rnd = random.Random(seed)
    grouped = cells_by_class()
    rows: list[dict] = []
    lot_counter = lot_prefix

    for label in CLASSES:
        cells = grouped[label]
        weights = []
        for station, severity in cells:
            is_exception = station == "stamping" and severity in ("critical", "major")
            is_exception = is_exception or (
                station in ("gluing", "casing") and severity in ("critical", "major")
            )
            weights.append(exception_weight if is_exception else 1)
        for index in range(rows_per_class):
            station, severity = rnd.choices(cells, weights=weights, k=1)[0]
            alias = rnd.choice(ALIASES[station])
            renderer = RENDERERS[index % len(RENDERERS)]
            lot_counter += rnd.randint(1, 9)
            rows.append(
                build_row(station, severity, alias, renderer, rnd, f"L-{lot_counter}")
            )
    rnd.shuffle(rows)
    return rows


def force_misleading_aliases(rows: list[dict], seed: int, lot_prefix: int) -> list[dict]:
    """Guarantee every misleading alias appears in the split at an exception-relevant severity."""
    rnd = random.Random(seed + 977)
    lot_counter = lot_prefix + 5000
    extra = []
    for position, alias in enumerate(MISLEADING_ALIASES):
        station = station_of(alias)
        severity = ["critical", "major"][position % 2]
        lot_counter += rnd.randint(3, 19)
        extra.append(
            build_row(
                station,
                severity,
                alias,
                RENDERERS[position % len(RENDERERS)],
                rnd,
                f"L-{lot_counter}",
            )
        )
    # Replace rows that carry the same label so the class balance is preserved.
    out = list(rows)
    for row in extra:
        label = row["messages"][1]["content"]
        for index, existing in enumerate(out):
            if existing["messages"][1]["content"] == label and existing not in extra:
                out[index] = row
                break
    return out


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def check(train: list[dict], test: list[dict]) -> None:
    """The validation checklist from data-preparation/overview.md, run locally first."""
    train_keys = {json.dumps(row, sort_keys=True) for row in train}
    test_keys = {json.dumps(row, sort_keys=True) for row in test}
    overlap = train_keys & test_keys
    assert not overlap, f"train/test share {len(overlap)} identical rows"
    for split_name, rows in (("train", train), ("test", test)):
        assert rows, f"{split_name} is empty"
        for row in rows:
            for message in row["messages"]:
                assert message["content"].strip(), f"empty content in {split_name}"
            label = row["messages"][1]["content"]
            assert label in CLASSES, f"unknown label {label!r}"
            assert len(json.dumps(row)) <= 30000, "row longer than validation_max_total_length"
    train_labels = {row["messages"][1]["content"] for row in train}
    test_labels = {row["messages"][1]["content"] for row in test}
    assert train_labels == test_labels == set(CLASSES), (
        f"label sets differ: train={sorted(train_labels)} test={sorted(test_labels)} "
        f"classes={sorted(CLASSES)}"
    )
    counts = {label: sum(1 for r in train if r["messages"][1]["content"] == label)
              for label in CLASSES}
    assert min(counts.values()) >= 4, f"a class has fewer than 4 train rows: {counts}"


def main(out_dir: str, train_per_class: int, test_per_class: int, seed: int) -> None:
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)

    train = build_split(train_per_class, lot_prefix=1000, seed=seed, exception_weight=3)
    test = build_split(test_per_class, lot_prefix=7000, seed=seed + 1, exception_weight=4)
    test = force_misleading_aliases(test, seed=seed, lot_prefix=7000)
    check(train, test)

    write_jsonl(target / "train.jsonl", train)
    write_jsonl(target / "test.jsonl", test)

    job_description = {
        "task_description": TASK_DESCRIPTION,
        "classes_description": CLASSES_DESCRIPTION,
        "synthetic_data_generation_instructions": SYNTHGEN_INSTRUCTIONS,
    }
    (target / "job_description.json").write_text(
        json.dumps(job_description, indent=2) + "\n"
    )

    topic_block = "\n".join(
        ["    - " + "\n".join(["  - " + t for t in MUTATION_STATION_TOPICS]).lstrip()]
    )
    lines = []
    for pool in (MUTATION_STATION_TOPICS, MUTATION_SEVERITY_TOPICS):
        for index, topic in enumerate(pool):
            prefix = "    - - " if index == 0 else "      - "
            lines.append(prefix + topic)
    topic_block = "\n".join(lines)
    (target / "config.yaml").write_text(CONFIG_YAML % {"mutation_topics": topic_block})

    print(f"wrote {target}/")
    for name in ("config.yaml", "job_description.json", "train.jsonl", "test.jsonl"):
        print(f"  {name}")
    print(f"train rows: {len(train)}  test rows: {len(test)}")
    for label in CLASSES:
        tr = sum(1 for r in train if r["messages"][1]["content"] == label)
        te = sum(1 for r in test if r["messages"][1]["content"] == label)
        print(f"  {label:<18} train={tr:>3} test={te:>3}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--train-per-class", type=int, default=6)
    parser.add_argument("--test-per-class", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260808)
    args = parser.parse_args()
    main(
        out_dir=args.out_dir,
        train_per_class=args.train_per_class,
        test_per_class=args.test_per_class,
        seed=args.seed,
    )
