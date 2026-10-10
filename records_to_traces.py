# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Convert the records written by `distil inference-endpoint download-traces` into a trace file."""

import argparse
import json


def convert(record, source):
    metadata = record.get("metadata") or {}
    if str(metadata.get("status")) != "200":
        return None
    if source and metadata.get("source") != source:
        return None
    request = json.loads(record["input"])
    reply = json.loads(record["output"])["choices"][0]["message"]
    if not reply.get("content") and not reply.get("tool_calls"):
        return None
    assistant = {"role": "assistant", "content": reply.get("content") or ""}
    if reply.get("tool_calls"):
        assistant["tool_calls"] = reply["tool_calls"]
    converted = {"messages": [*request["messages"], assistant]}
    if request.get("tools"):
        converted["tools"] = request["tools"]
    return converted


def main(input_path, output_path, source):
    total = kept = 0
    with open(input_path) as src, open(output_path, "w") as dst:
        for line in src:
            if not line.strip():
                continue
            total += 1
            converted = convert(json.loads(line), source)
            if converted is not None:
                kept += 1
                dst.write(json.dumps(converted, ensure_ascii=False) + "\n")
    print(f"kept {kept} of {total} records")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="the file download-traces wrote")
    parser.add_argument("--output", required=True, help="the trace file to write")
    parser.add_argument("--source", choices=["fallback", "primary"], help="keep only answers from this model")
    args = parser.parse_args()
    main(args.input, args.output, args.source)
