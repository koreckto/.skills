"""Template for a skill-level ``evals/verify.py``.

Copy this file into ``skills/<name>/evals/verify.py`` and implement the
assertion-specific checks. Exit 0 with non-empty stdout for PASS, exit 1 for
an assertion FAIL, and let the top-level handler turn unexpected exceptions
into exit 2.
"""

# ruff: noqa: T201  # verifier stdout protocol.

import argparse
import traceback
from pathlib import Path


def _main() -> int:
    """Run the template verifier and return its process exit code."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, help="Absolute workspace path.")
    parser.add_argument("--outputs", required=True, help="Absolute outputs path.")
    parser.add_argument("--case", required=True, help="Normalized official eval id.")
    parser.add_argument(
        "--assertion", required=True, help="Exact official assertion text."
    )
    parser.add_argument("--arm", default="with_skill")
    args = parser.parse_args()

    outputs = Path(args.outputs)
    if args.assertion == "The expected output file exists and is non-empty.":
        target = outputs / "example.txt"
        if not target.is_file() or target.stat().st_size == 0:
            print(f"FAIL: {target} is missing or empty")
            return 1
        print(f"PASS: {target} exists with {target.stat().st_size} bytes")
        return 0

    print(f"FAIL: unsupported assertion: {args.assertion}")
    return 1


if __name__ == "__main__":
    try:
        exit_code = _main()
    except Exception as exc:
        traceback.print_exc()
        raise SystemExit(2) from exc
    raise SystemExit(exit_code)
