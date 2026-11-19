# Changelog

All notable changes to the `python-code-style` skill will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-11-20

### Added

- Core skill entrypoint (`SKILL.md`) defining rule precedence (`MUST` / `MUST NOT`, `SHOULD` / `SHOULD NOT`, `MAY`), Ruff adoption and execution workflow, intentional template choices and blind spots, and task routing.
- Shared Ruff configuration template (`assets/pyproject.ruff.toml`) with `docstring-code-format`, curated lint rules and ignores, scoped `tests/**` and `conftest.py` per-file ignores, `TID251` ban on `from __future__ import annotations`, quoted type-checking annotations, and Google docstring convention.
- Style rules reference (`references/style-rules.md`) covering relative internal/public object classification, module layout and import-time purity, package-boundary `__init__.py` re-exports, naming conventions, formatting remainders, Google-style docstrings and public model field documentation, comments, and code examples.
- Language rules reference (`references/language-rules.md`) covering non-mechanical typing and `TYPE_CHECKING` safety, immutable data modeling (`@dataclass(frozen=True, slots=True)`, `frozendict`, `sentinel`), function and parameter design, structural pattern matching, comprehension budgets, async safety (`TaskGroup`, `timeout`, `to_thread`), exception handling, explicit text I/O encoding, `pathlib` hygiene and traversal protection (`is_relative_to()`), isolated unit testing, security and lazy logging, performance, and coded inline suppressions with reasons.
- Python version compatibility reference (`references/version-compatibility.md`) with minimum-version detection precedence, cumulative Python 3.11-3.15 feature matrix (`py311`-`py315`), and compatibility patterns (`_compat.py` guards, PEP 649 vs. quoted forward references, and version-marked examples).
- MIT License (`LICENSE`).
