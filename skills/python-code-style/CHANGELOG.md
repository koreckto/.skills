# Changelog

All notable changes to `python-code-style` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this skill adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-11-09

### Added

- Initial release for Python 3.11+ with a shared Ruff rule set.
- Importance-based rule levels with explicit verification tags, including `Review` for rules that need human verification. Ruff checks still gate CI; they do not determine a rule's level.
- Style rules for module layout, imports, naming, formatting, docstrings, comments, code examples, and exports.
- Example formatting guidance: a single blank line between statement-level examples, with two blank lines around top-level definitions and classes.
- Language rules for typing, functions, data modeling, comprehensions, async code, exceptions, date and time handling, testing, security, logging, performance, and suppressions.
- Ruff configuration reference with a rule set map, intentional ignores, per-file ignores, banned API, formatter guidance, and adoption steps.
- Python 3.11–3.15 compatibility matrix, minimum-version detection, and version-gated rule guidance.
- Maintenance model with a change impact map, rule classification, release checklist, review rubric, and drift indicators.
- MIT license.
