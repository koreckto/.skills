---
name: python-code-style
description: Writes, reviews, formats, and lints Python code against shared style and language standards with Ruff. Use when writing, reviewing, refactoring, or modernizing Python code; adding type annotations, docstrings, or unit tests; fixing lint or formatting issues; configuring Ruff in pyproject.toml; or checking Python 3.11+ syntax and version compatibility.
compatibility: Requires Python 3.11+ and Ruff. uv is recommended.
license: MIT
metadata:
  author: Koreckto
  version: "1.1.0"
---

# Python Code Style

Shared defaults for writing and reviewing Python code. The skill covers general style and language rules for source files, tests, samples, and documentation examples. It does not replace project-specific conventions.

## Scope

The skill owns:

- Layout, imports, exports, naming, formatting, docstrings, comments, and code examples.
- Typing, data modeling, functions, pattern matching, comprehensions, async code, exceptions, date, time, and I/O handling, path handling, testing, security, logging, performance, and suppressions.
- Ruff configuration and Python version compatibility for the shared rule set.

It does not own package publishing, release engineering, or project architecture. Keep those in the project's own rules and documents.

## Source of truth and precedence

1. Project rules override the shared defaults. Read them before changing code.
2. The committed tooling configuration decides which checks run and whether CI blocks. It does not change a rule's level.
3. The rule references own the levels and verification tags. The shared defaults cover what the tooling cannot check.

Do not add project-specific rules to this skill directory. Keep project rules in the project and under version control.

## Rule conventions

The level and the verification tag are independent. The level says how strong the obligation is; the verification tag says how a violation is detected. The level never depends on whether a tool can check the rule.

| Level | Meaning | Typical use | Exceptions |
| --- | --- | --- | --- |
| **MUST** | Non-negotiable. A violation is a defect. | security, privacy, data integrity, correctness, resource ownership, compatibility | none; an inline suppression (`# noqa` or `# type: ignore`) is a reported violation and requires fixing the code or recording an explicit project override |
| **MUST NOT** | Prohibited. A violation is a defect. | same | same |
| **SHOULD** (RECOMMENDED) | Strong default. | readability, maintainability, consistency, documentation, test clarity | a specific, documented reason |
| **SHOULD NOT** (NOT RECOMMENDED) | Strong default prohibition. | same | a specific, documented reason |
| **MAY** (OPTIONAL) | Optional. | preference | none |

| Verification tag | Meaning |
| --- | --- |
| `Ruff: CODE` | Ruff lint rule |
| `Format: ruff format` | Formatter |
| `Type check: CODE` | Type checker |
| `Test: <name>` | Test |
| `Check: <command>` | Another deterministic check |
| `Review` | Human review; no automated check, or the check covers only part of the rule |
| `Since: X.Y` | Scope qualifier, not a check |

Rules:

- Every rule names at least one verification tag. `Review` is a verification method, not a level.
- A MUST rule may rely on `Review` when the violation is severe but not mechanically detectable.
- A rule with an automated check and a judgment remainder names both, for example (`Ruff: ANN`; `Review`).
- A SHOULD rule with an automated check fails CI until it is fixed or given a documented exception with a reason.
- A MUST rule has no routine exception. A suppression is a reported violation: list it in review, and fix the code or record a project-specific override in the project rules instead of normalizing the suppression. A SHOULD rule may have a documented exception with a specific reason. A MAY rule needs no justification.
- A check that only warns cannot be the sole verification for a MUST. Pair it with `Review`.
- A verification tag appears in parentheses after the rule sentence. `Since:` is a scope qualifier, not a check; multiple tags are separated with semicolons, for example (`Ruff: ANN`; `Review`; `Since: 3.12`).

Tool-specific suppression and exception forms are in [Suppressions and exceptions](references/ruff-config.md#suppressions-and-exceptions).

## Non-negotiables

This list is a navigation aid. The normative rules and their verification tags live in the linked sections.

- Never place secrets, credentials, tokens, or personal data in code, tests, examples, docs, logs, or exception messages. See [Security and logging](references/language-rules.md#security-and-logging), [Code examples](references/style-rules.md#code-examples).
- Never run `eval` or `exec` on untrusted input, deserialize untrusted data with `pickle` or `marshal`, use `shell=True` with untrusted input, or use `random` for security-sensitive values. See [Security and logging](references/language-rules.md#security-and-logging).
- Never use a bare `except:` or swallow an exception silently; chain a translated exception. See [Exceptions](references/language-rules.md#exceptions).
- Never use `assert` for input validation in production code. See [Exceptions](references/language-rules.md#exceptions).
- Never use a bare name as a `case` pattern to compare against a constant; it captures every value. See [Pattern matching](references/language-rules.md#pattern-matching).
- Never use a mutable default, a call in a default, or mutable class-level state without `ClassVar`; bind loop variables captured by a closure. See [Functions and parameters](references/language-rules.md#functions-and-parameters), [Type annotations](references/language-rules.md#type-annotations).
- Never block the event loop; never swallow `CancelledError`; release async resources. See [Async and concurrency](references/language-rules.md#async-and-concurrency).
- Use timezone-aware datetimes; pass `strict=` to a multi-iterable `zip()`; pass `encoding=` for text I/O below 3.15. See [Date, time, and I/O](references/language-rules.md#date-time-and-io), [Comprehensions and iteration](references/language-rules.md#comprehensions-and-iteration).
- Validate external input at the boundary; keep import time free of I/O and global mutation. Keep runtime imports at runtime, and quote forward references that are not defined when the annotation is evaluated (or omit quotes on 3.14+ where PEP 649 defers evaluation). See [Data modeling](references/language-rules.md#data-modeling), [Style: module and package layout](references/style-rules.md#module-and-package-layout), [Type annotations](references/language-rules.md#type-annotations).
- Keep an externally supplied path under its base directory; resolve both the base and the candidate before `is_relative_to()`. See [Paths](references/language-rules.md#paths), [Security and logging](references/language-rules.md#security-and-logging).
- Keep tests isolated from network, real time, unseeded randomness, and execution order. See [Testing](references/language-rules.md#testing).
- Give every suppression a code and a reason; never suppress a security rule without a security review. See [Suppressions](references/language-rules.md#suppressions).
- Run Ruff only on the files being changed unless a whole-repository cleanup is explicitly requested. See [Workflow](#workflow).

## Priorities

When rules conflict, apply them in this order:

1. Correctness and safety.
2. Readability and maintainability.
3. Consistency with the project.
4. Measured performance.
5. Minimal diff.

A lower priority never justifies a MUST violation. If a project rule weakens a MUST rule, flag the conflict and ask before applying it.

## Routing

| Task | Read |
| --- | --- |
| Layout, imports, exports | [Style: module and package layout](references/style-rules.md#module-and-package-layout), [Style: imports](references/style-rules.md#imports), [Style: exports](references/style-rules.md#public-api-and-exports) |
| Naming | [Style: naming](references/style-rules.md#naming) |
| Formatting and line structure | [Style: formatting and line structure](references/style-rules.md#formatting-and-line-structure) |
| Docstrings and comments | [Style: docstrings](references/style-rules.md#docstrings), [Style: comments](references/style-rules.md#comments) |
| Code examples | [Style: code examples](references/style-rules.md#code-examples) |
| Type annotations, generics, `TYPE_CHECKING` | [Language: type annotations](references/language-rules.md#type-annotations) |
| Functions, parameters, data models | [Language: functions and parameters](references/language-rules.md#functions-and-parameters), [Language: data modeling](references/language-rules.md#data-modeling) |
| Multi-branch dispatch, `match` statements | [Language: pattern matching](references/language-rules.md#pattern-matching) |
| Comprehensions and async code | [Language: comprehensions and iteration](references/language-rules.md#comprehensions-and-iteration), [Language: async and concurrency](references/language-rules.md#async-and-concurrency) |
| Exceptions | [Language: exceptions](references/language-rules.md#exceptions) |
| Date, time, files, text I/O | [Language: date, time, and I/O](references/language-rules.md#date-time-and-io) |
| Path composition, normalization, containment | [Language: paths](references/language-rules.md#paths), [Language: security and logging](references/language-rules.md#security-and-logging) |
| Tests | [Language: testing](references/language-rules.md#testing) |
| Security, logging, performance, suppressions | [Language: security and logging](references/language-rules.md#security-and-logging), [Language: performance](references/language-rules.md#performance), [Language: suppressions](references/language-rules.md#suppressions) |
| Ruff configuration, rule codes, ignores | [Ruff configuration](references/ruff-config.md) |
| Python versions and syntax availability | [Version compatibility](references/version-compatibility.md) |
| Project-specific rules | [Project-specific standards](#project-specific-standards) |

## Workflow

1. Read the project rules. Check `AGENTS.md`, `CONTRIBUTING.md`, and any standards file the user names. Apply them before the shared defaults.
2. Determine the minimum Python version. Read `[project] requires-python`, then Poetry metadata, classifiers, and the CI matrix. Use `.python-version` only as a development hint. If no minimum version is declared, ask; do not guess.
3. Check or adopt the Ruff configuration. Use the project's committed Ruff configuration when one exists. Merge the `[tool.ruff*]` sections from [`assets/pyproject.ruff.toml`](assets/pyproject.ruff.toml) into the root `pyproject.toml` only when setting up Ruff for a new project or when the user asks to configure or update Ruff. Read [Ruff configuration](references/ruff-config.md) before changing existing settings.
4. Apply the defaults. Read [Style rules](references/style-rules.md) and [Language rules](references/language-rules.md) for a writing or review task. For version-specific syntax or APIs, read [Version compatibility](references/version-compatibility.md).
5. Run Ruff on the touched files. Choose the runner once:
   - uv project with Ruff in its dependencies: `uv run ruff`.
   - uv project without Ruff in its dependencies: `uvx ruff`.
   - No uv: `ruff`.

   ```bash
   # Focused change (default)
   uv run ruff check --fix <path/to/touched_file.py>
   uv run ruff format <path/to/touched_file.py>
   uv run ruff check <path/to/touched_file.py>
   uv run ruff format --check <path/to/touched_file.py>
   ```

   Drop `uv run` for a direct `ruff` invocation, or replace it with `uvx ruff` when Ruff is not a project dependency. Fix violations in the code rather than suppressing them. Review fixes before accepting them. Never use `--unsafe-fixes` without manual inspection. Run a whole-repository cleanup only when the user explicitly asks for it.
6. Validate with the checklist below.

## Review pass

For a full review, check in this order:

1. MUST rules: secrets, dangerous execution, exception handling, async safety, data integrity, compatibility.
2. Behavior and boundaries: input validation, data flow, exceptions.
3. Concurrency: async correctness, cancellation, blocking calls.
4. API: naming, types, docstrings, compatibility.
5. Tests: behavior, isolation, regression coverage.
6. Tooling: Ruff, suppressions, configuration consistency.

Do not approve a MUST violation unless an explicit project override is approved and recorded in the project rules. Report every suppressed MUST, even when a project-specific override approved it. For each SHOULD deviation, require a recorded reason. Treat repeated deviations as a signal to update the project rules, not as a silent exception.

## Project-specific standards

A project may define its own Python rules in `AGENTS.md`, `CONTRIBUTING.md`, a dedicated standards file, client-specific rule files, or any file the user names. There is no required path, format, or section layout.

- Apply project rules where they differ from the shared defaults; if a project rule weakens a MUST rule, flag the conflict and ask before applying it.
- If no project rules exist, use the shared defaults. Do not create a standards file unless the user asks.

## Gotchas

- A Ruff check does not make a rule a MUST, and a missing check does not make it optional. Use `Review` when only a person can verify the rule.
- A suppressed MUST is still a reported violation. Fix the code or record a project-specific override instead of treating `# noqa` as an exception.
- A copied `target-version` can silently target the wrong Python version. Prefer `requires-python`; if both exist, `target-version` wins.
- `target-version` does not prove that a standard-library API exists in the minimum Python version. Verify APIs against the documentation for the minimum version.
- Newer syntax cannot be made compatible with an older interpreter by wrapping it in `sys.version_info`. The parser reads the whole file.
- `from __future__ import annotations` is banned by `TID251`. On Python 3.11–3.13, use quoted annotations for forward references and for types imported under `TYPE_CHECKING`. On Python 3.14+, annotations are deferred natively (PEP 649); omit quotes unless evaluated at definition time.
- The `tests/**` per-file ignores apply only to tests. Do not extend them to production code.
- Do not run `ruff check --fix .` across an existing repository unless explicitly requested. Use focused file arguments.
- Never use `--unsafe-fixes` without manually inspecting the diff.
- Do not enable lint rules that conflict with `ruff format`, such as `COM812` or `ISC001`.
- `N818` flags every custom `Exception` subclass that lacks the `Error` suffix. A non-error control-flow exception may suppress it with a reason.
- `S110` and `S112` check typed exceptions because the template sets `check-typed-exception = true`. Use `contextlib.suppress(SpecificError)` for an intentional ignore.
- `BLE001` accepts `except Exception` when the handler logs the exception with its traceback or re-raises. A boundary handler that translates an exception into a structured failure return needs `# noqa: BLE001` with a reason. A logged handler must not add it, because `RUF100` flags an unused suppression.
- `TRY003` is ignored on purpose: it rejects multi-word messages at the raise site. Keep exception messages at the raise site.
- `UP040`, `UP046`, and `UP047` only fire at a 3.12+ target. On 3.11, use `TypeVar`, `Generic`, and `TypeAlias`.
- `TC004` catches direct runtime uses such as `isinstance`, base classes, and decorators. It does not catch `get_type_hints`, `get_overloads`, or framework annotation resolution; keep those imports at runtime manually.
- `D415` is ignored because it accepts only ASCII `.`, `?`, and `!`. Terminal punctuation in non-English docstrings is `Review`.
- `D417` checks only docstrings that contain an `Args` section. A public function without one can still be under-documented.
- Ruff does not enforce the internal-module docstring exception or public model field documentation; both are `Review`.
- `PT009` and `PT027` are ignored globally so unittest-style assertions remain valid. A pytest project can re-enable them.
- `FBT001` and `FBT002` check definitions only. `FBT003` is not enabled, so a positional boolean at a call site is `Review`.

## Task validation

Before finishing a coding task:

- [ ] Project rules were read and applied; no project rules were written into the skill directory.
- [ ] Review-only rules relevant to the change were checked against their stated conditions.
- [ ] MUST violations are fixed or recorded as an explicit project override; every SHOULD deviation has a documented reason.
- [ ] Every suppressed MUST is listed in the review report with a follow-up action.
- [ ] `requires-python` is declared and matches the version used for decisions.
- [ ] Ruff `target-version` and `requires-python` are consistent (and Ruff configuration lives in the root `pyproject.toml` when configured or updated in this task).
- [ ] `ruff check` and `ruff format --check` pass on the affected files.
- [ ] No bare `# noqa` or `# type: ignore`; every suppression has a code and a reason.
- [ ] No secrets, credentials, tokens, or personal data appear in code, tests, examples, docs, logs, or exception messages.
- [ ] Async code has no blocking calls, and cancellation is not swallowed.
- [ ] Datetimes are timezone-aware; text I/O specifies `encoding=` below 3.15.
- [ ] Paths expand `~` at the input boundary; canonical checks use `resolve()`, and externally supplied paths are contained.
- [ ] Public APIs have Google-style docstrings and complete annotations, and public model fields are documented, or a recorded reason.
- [ ] Tests cover the changed behavior and are isolated.
- [ ] Naming, functions, data, exceptions, and security follow the references.
- [ ] Syntax and APIs match the declared minimum Python version, and tests pass on the available supported Python versions.

## References

| File | Contents | Read when |
| --- | --- | --- |
| [`style-rules.md`](references/style-rules.md) | layout, imports, exports, naming, formatting, docstrings, comments, code examples | writing or reviewing code |
| [`language-rules.md`](references/language-rules.md) | typing, data modeling, functions, pattern matching, comprehensions, async, exceptions, date and time, I/O, paths, testing, security, performance, suppressions | writing or reviewing code |
| [`ruff-config.md`](references/ruff-config.md) | rule set map, target version, per-file ignores, banned API, formatter | configuring or troubleshooting Ruff |
| [`version-compatibility.md`](references/version-compatibility.md) | support matrix, minimum-version detection, compatibility patterns, end of life | choosing syntax or APIs, or setting the minimum Python version |

Maintenance: [MAINTENANCE.md](MAINTENANCE.md) — for maintainers only; not part of the coding workflow.
