# Changelog

All notable changes to `python-code-style` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this skill adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-11-10

### Added

- Added pattern matching rules: prefer `match` and `case` for structural dispatch over `if`/`elif` chains, keep `if`/`elif` for simple conditions, and forbid bare-name capture patterns used as constant comparisons.
- Added type annotation rules for when to create a type alias, prioritizing domain meaning over type length and distinguishing aliases from `NewType`.
- Added a type annotation formatting rule for wrapping a union annotation that does not fit on one line in parentheses with one member per line.
- Added path composition rules: one segment per `/` operand, `joinpath(*segments)` for dynamic sequences, whole external paths as one value, and no `os.path.join`, concatenation, or f-string separators.
- Added path normalization rules for `expanduser()`, `resolve()`, and `absolute()`, plus containment validation for externally supplied paths.

### Changed

- Expanded Google-style docstring layout rules to require argument, return, yield, exception, and attribute descriptions on separate indented lines below their declarations.
- Required every applicable section in public function and method docstrings, reserving summary-only docstrings for names with a leading underscore and for functions in internal modules.
- Extended field documentation to every public field of a public data model, including framework models such as Pydantic.
- Defined internal symbols by their defining boundaries and clarified the naming of callbacks registered by object reference.
- Clarified that a single call or data structure spanning multiple lines is one phase when separating long function bodies with blank lines.
- Moved the repository versioning and deprecation policy to the root `AGENTS.md`; no rule changes.
- Grouped the style and language references under category headings that follow the writing workflow; moved `Public API and exports` and `Data modeling` into their matching groups; no rule changes.
- Moved path handling from module layout to the new `Paths` section and the `Path.open()` rule to Date, time, and I/O; no rule level changes.

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
