# /// script
# requires-python = ">=3.10"
# dependencies = ["openai>=1.40"]
# ///
"""Send the rows of a JSONL file to an OpenAI-compatible endpoint, the way an application would."""

import argparse
import importlib.util
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from openai import APIStatusError, OpenAI

KEY_PROPAGATION_SECONDS = 60
RETRY_INTERVAL_SECONDS = 5
PROGRESS_EVERY = 50


def read_requests(path, limit):
    """Returns (messages, expected answer or None) per row."""
    requests = []
    with open(path) as source:
        for line in source:
            if not line.strip():
                continue
            messages = json.loads(line)["messages"]
            expected = None
            if messages and messages[-1]["role"] == "assistant":
                expected = messages[-1].get("content")
                messages = messages[:-1]
            requests.append((messages, expected))
            if limit and len(requests) >= limit:
                break
    return requests


def answer_text(response):
    """The assistant text from a raw chat completion or from model_client's invoke()."""
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        return response.get("content")
    if hasattr(response, "choices"):
        return response.choices[0].message.content
    return getattr(response, "content", None)


def normalize(text):
    if text is None:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except ValueError:
        return text


def matches(answer, expected):
    return expected is not None and normalize(answer) == normalize(expected)


def load_client_class(client_path):
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("model_client", client_path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(Path(client_path).parent))
    spec.loader.exec_module(module)
    return module.DistilLabsLLM


def with_key_retry(call):
    deadline = time.monotonic() + KEY_PROPAGATION_SECONDS
    while True:
        try:
            return call()
        except APIStatusError as error:
            if error.status_code not in (401, 403) or time.monotonic() > deadline:
                raise
            time.sleep(RETRY_INTERVAL_SECONDS)


def make_sender(base_url, api_key, model, client_path):
    if client_path:
        client = load_client_class(client_path)(model, base_url, api_key)

        def send(messages):
            return client.invoke([m for m in messages if m["role"] != "system"])

        return send

    client = OpenAI(base_url=base_url, api_key=api_key)

    def send(messages):
        return client.chat.completions.create(model=model, messages=messages, temperature=0)

    return send


def main(base_url, api_key, model, input_path, limit, concurrency, client_path):
    requests = read_requests(input_path, limit)
    send = make_sender(base_url, api_key, model, client_path)
    ok = failed = matched = 0
    labelled = sum(1 for _, expected in requests if expected is not None)
    last_error = None
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {
            pool.submit(with_key_retry, lambda m=m: send(m)): expected
            for m, expected in requests
        }
        for done, future in enumerate(as_completed(futures), start=1):
            try:
                response = future.result()
                ok += 1
                if matches(answer_text(response), futures[future]):
                    matched += 1
            except Exception as error:
                failed += 1
                last_error = error
            if done % PROGRESS_EVERY == 0:
                print(f"{done} of {len(requests)} sent", flush=True)
    print(f"sent {len(requests)}, ok {ok}, failed {failed}")
    if labelled:
        print(f"matched {matched} of {labelled}")
    if last_error is not None:
        print(f"last error: {last_error}", file=sys.stderr)
    if requests and ok == 0:
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--model", required=True, help="the unique endpoint name")
    parser.add_argument("--input", required=True, help="JSONL file of {\"messages\": [...]} rows")
    parser.add_argument("--limit", type=int, default=0, help="send only the first N rows")
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument(
        "--client",
        help="path to a model's model_client.py; sends each row through it instead of a raw request",
    )
    args = parser.parse_args()
    main(args.base_url, args.api_key, args.model, args.input, args.limit, args.concurrency, args.client)
