---
name: python-code-style
description: Writes, reviews, formats, and lints Python 3.11+ code using the shared Ruff template and non-mechanical review rules. Use when writing, reviewing, refactoring, or modernizing Python code, configuring Ruff in pyproject.toml, or checking Python version compatibility.
compatibility: Requires Python 3.11+ and Ruff. uv is recommended.
license: MIT
metadata:
  author: Koreckto
  version: "1.0.0"
---

# Python Code Style

Shared Python 3.11+ coding standard pairing a strict Ruff template with the design, safety, and review rules that tools cannot check mechanically.

## Precedence and Rule Levels

Project rules (`AGENTS.md`, `CONTRIBUTING.md`, or a project standards file) override these defaults. If a project rule weakens a `MUST`, flag the conflict and ask before applying it.

- **`MUST` / `MUST NOT`**: Non-negotiable defect prevention (security, privacy, correctness, resource safety, compatibility). An inline suppression (`# noqa` or `# type: ignore`) is a reported violation unless recorded as an explicit project override.
- **`SHOULD` / `SHOULD NOT`**: Strong default for clarity, maintainability, and consistency. Deviations require a specific documented reason.
- **`MAY`**: Optional preference.

## Ruff Adoption and Execution

1. Merge `[tool.ruff*]` from [the Ruff template](assets/pyproject.ruff.toml) into the root `pyproject.toml` only when setting up Ruff or updating its configuration. Keep one Ruff configuration per repository, and never mix Black or isort on the same files.
2. Let Ruff infer `target-version` from `[project] requires-python`. Uncomment `target-version` only when PEP 621 metadata is absent, and keep both consistent.
3. Run Ruff on touched files (`uv run ruff`, `uvx ruff`, or `ruff`) unless a full-repository cleanup is explicitly requested, and inspect `--unsafe-fixes` diffs before accepting them:

```bash
ruff check --fix <path/to/touched_file.py>
ruff format <path/to/touched_file.py>
ruff check <path/to/touched_file.py>
ruff format --check <path/to/touched_file.py>
```

Keep these intentional template choices and Ruff blind spots in mind:

- `TID251` bans `from __future__ import annotations`; quote forward references on Python 3.11-3.13 instead.
- Ruff checks import order and placement, not package-boundary import direction (`__init__.py` re-exports vs defining modules).
- `D415` is ignored so non-English docstrings remain valid, leaving terminal punctuation, docstring section layout, summary-only internal exceptions, and public model field docs to review.
- `TRY003` is ignored so exception messages stay at the `raise` site.
- `PT009` and `PT027` are ignored globally so `unittest`-style assertions remain valid.
- `tests/**` and `conftest.py` ignores (`S101`, `S105`-`S108`, `S311`, `ANN`, `ARG`, `D`, `FBT001`, `FBT002`, `TC`) cover obvious dummy test values and fixtures only and must never expand to production code.

## Routing

| Task | Guide |
| :--- | :--- |
| Object terms, module layout, package-boundary imports/exports, naming, formatting remainders, docstrings, comments, code examples | [Style Rules](references/style-rules.md) |
| Non-mechanical typing, data modeling, `sentinel`, functions, pattern matching, comprehensions, async, exceptions, I/O, paths, tests, security, suppressions | [Language Rules](references/language-rules.md) |
| Minimum-version detection, Python 3.11-3.15 feature matrix, compatibility patterns | [Version Compatibility](references/version-compatibility.md) |
| Shared `[tool.ruff*]` ruleset to merge into root `pyproject.toml` | [Ruff Template](assets/pyproject.ruff.toml) |
