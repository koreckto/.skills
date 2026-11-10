# Changelog

All notable changes to `python-code-style` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this skill adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-11-10

### Changed

- Expanded Google-style docstring layout rules to require argument, return, yield, exception, and attribute descriptions on separate indented lines below their declarations.
- Required every applicable section in public function and method docstrings, reserving summary-only docstrings for names with a leading underscore and for functions in internal modules.
- Extended field documentation to every public field of a public data model, including framework models such as Pydantic.
- Defined internal symbols by their defining boundaries and clarified the naming of callbacks registered by object reference.
- Clarified that a single call or data structure spanning multiple lines is one phase when separating long function bodies with blank lines.

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
