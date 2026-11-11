"""Deterministic verifier used by the sample evaluation fixture."""

# ruff: noqa: T201  # verifier stdout protocol.

import argparse
import json
import traceback
from pathlib import Path


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--outputs", required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--assertion", required=True)
    parser.add_argument("--arm", default="with_skill")
    args = parser.parse_args()

    outputs = Path(args.outputs)
    if args.assertion == "result.json is valid JSON.":
        path = outputs / "result.json"
        if not path.is_file():
            print(f"missing {path}")
            return 1
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            print(f"invalid JSON: {exc}")
            return 1
        print(f"valid JSON object: {value!r}")
        return 0
    print(f"unsupported assertion: {args.assertion}")
    return 1


if __name__ == "__main__":
    try:
        exit_code = _main()
    except Exception as exc:
        traceback.print_exc()
        raise SystemExit(2) from exc
    raise SystemExit(exit_code)
