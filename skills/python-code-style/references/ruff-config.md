# Ruff Configuration

Shared Ruff settings, rule-to-standard mapping, intentional ignores, and adoption workflow for the root `pyproject.toml` and [`../assets/pyproject.ruff.toml`](../assets/pyproject.ruff.toml).

## Source of truth

- Keep one Ruff configuration per repository.
- Put the configuration in the root `pyproject.toml`. Do not add a separate `ruff.toml` or `.ruff.toml` when `pyproject.toml` already holds the rules.
- Do not override `select` or `ignore` in CI or editor commands. The committed configuration is the source of truth.
- Preserve existing project-specific settings when merging the template.
- If this reference and the committed configuration disagree, the configuration wins. Update the document.

## Levels and checks

The rule references assign every rule a level and a verification tag. This file describes detection, not severity.

- A check can run on a SHOULD rule. The finding still blocks CI until it is fixed or given a documented exception through a coded suppression or a configuration entry that records the reason.
- A MUST rule has no routine exception. A suppression is a reported violation; fix the code or record a project-specific override instead of normalizing the suppression.
- A configuration ignore is not a level change. Removing a rule from `select` or adding it to `ignore` requires the same review as any other project override.

### Suppressions and exceptions

- A Ruff lint rule: `# noqa: CODE  # reason` on the line, or a documented `per-file-ignores` or `ignore` entry in the root `pyproject.toml`.
- `ruff format`: `# fmt: skip` for one statement, `# fmt: off` and `# fmt: on` for a range, or an explicit `exclude` or `extend-exclude` entry. The formatter has no `noqa`.
- A type checker: `# type: ignore[code]  # reason`, or the checker's own form, such as `# ty:ignore[rule]` or `# pyright: ignore[rule]`.
- A `Review`-only rule: record the exception in the project rules or the pull request, with the rule, reason, scope, and follow-up.

A suppression never changes a rule's level. A `MUST` suppression is a reported violation; a `SHOULD` suppression is a documented exception.

## Target version

- Prefer `[project] requires-python`; Ruff infers the target from it.
- If the project has no PEP 621 metadata, set `target-version` to the minimum supported version.
- If both `requires-python` and `target-version` exist, `target-version` wins. Keep them consistent.
- Do not copy a `target-version` from another workspace without checking the project's minimum Python version.
- Ruff's own default target is `py311`. A missing `requires-python` can therefore silently target 3.11.
- `target-version` controls version-aware lint suggestions. It does not prove that a standard-library API exists in the minimum Python version. Verify APIs against the documentation for the minimum version.

The template leaves `target-version` commented out. Uncomment it only when the project has no PEP 621 metadata.

## Template adoption

The template contains only `[tool.ruff*]` sections. Merge those sections into the root `pyproject.toml`; do not copy the file over an existing `pyproject.toml`. For a uv project, prefix Ruff commands with `uv run`, or use `uvx ruff` when Ruff is not a project dependency.

1. Inspect existing `[tool.ruff*]` sections. If none exist, append the template sections.
2. If existing Ruff configuration exists, merge tables without duplicating keys or breaking other tool tables.
3. Run `ruff check` immediately to validate that the TOML parses and the rules resolve.
4. Confirm `requires-python`; otherwise set `target-version` explicitly.
5. Run `ruff check --fix` and `ruff format` on the files being changed.
6. Review the diff, especially for unsafe fixes. Never use `--unsafe-fixes` automatically.
7. Run `ruff check` and `ruff format --check`.
8. If a SHOULD rule is unsuitable, change the project configuration with a documented reason instead of scattering `# noqa` comments. A MUST rule is not made optional by a configuration ignore; record an explicit project-specific override in the project rules.
9. Treat a whole-repository cleanup as a separate, explicit task.

The template intentionally omits `src`. Ruff defaults to `[".", "src"]`, which covers flat and `src` layouts. Add `src` only for a non-standard layout.

## Rule set map

| Family | Area | Section |
| --- | --- | --- |
| `A` | names that shadow builtins | [Style: naming](style-rules.md#naming) |
| `ANN` | function annotations | [Language: type annotations](language-rules.md#type-annotations) |
| `ARG` | unused arguments | [Language: functions and parameters](language-rules.md#functions-and-parameters) |
| `ASYNC` | blocking calls in async code | [Language: async and concurrency](language-rules.md#async-and-concurrency) |
| `B` | common bugs and dubious constructs | [Language: functions](language-rules.md#functions-and-parameters), [exceptions](language-rules.md#exceptions), [comprehensions](language-rules.md#comprehensions-and-iteration) |
| `BLE` | blind `except` clauses | [Language: exceptions](language-rules.md#exceptions) |
| `C4` | comprehension style | [Language: comprehensions and iteration](language-rules.md#comprehensions-and-iteration) |
| `C90` | cyclomatic complexity | [Language: functions and parameters](language-rules.md#functions-and-parameters) |
| `D` | docstring structure | [Style: docstrings](style-rules.md#docstrings) |
| `DTZ` | timezone-aware datetimes | [Language: date, time, and I/O](language-rules.md#date-time-and-io) |
| `E`, `W` | pycodestyle errors and warnings | [Style: formatting](style-rules.md#formatting-and-line-structure), [imports](style-rules.md#imports), [exceptions](language-rules.md#exceptions) |
| `ERA` | commented-out code | [Style: comments](style-rules.md#comments) |
| `F` | unused imports, undefined names, exports | [Style: imports](style-rules.md#imports), [exports](style-rules.md#public-api-and-exports) |
| `FBT001`, `FBT002` | boolean positional arguments | [Language: functions and parameters](language-rules.md#functions-and-parameters) |
| `FURB` | modernizations and simplifications | [Language: comprehensions and iteration](language-rules.md#comprehensions-and-iteration) |
| `I` | import ordering | [Style: imports](style-rules.md#imports) |
| `N818` | exception name suffix | [Style: naming](style-rules.md#naming) |
| `PERF` | performance anti-patterns | [Language: performance](language-rules.md#performance) |
| `PGH003`, `PGH004` | blanket suppressions | [Language: suppressions](language-rules.md#suppressions) |
| `PLC0415` | imports outside the top level | [Style: imports](style-rules.md#imports) |
| `PLW0603` | `global` statement | [Language: functions and parameters](language-rules.md#functions-and-parameters) |
| `PT` | pytest style | [Language: testing](language-rules.md#testing) |
| `PTH` | path handling | [Language: paths](language-rules.md#paths), [Language: date, time, and I/O](language-rules.md#date-time-and-io) |
| `RET` | return style | [Language: functions and parameters](language-rules.md#functions-and-parameters) |
| `RUF` | Ruff-specific rules | [RUF012](language-rules.md#type-annotations), [RUF022](style-rules.md#public-api-and-exports), [RUF100](language-rules.md#suppressions) |
| `S` | security checks | [Language: security and logging](language-rules.md#security-and-logging), [exceptions](language-rules.md#exceptions), [I/O](language-rules.md#date-time-and-io) |
| `T20` | `print` and `pprint` | [Language: security and logging](language-rules.md#security-and-logging) |
| `TC` | typing-only imports | [Language: type annotations](language-rules.md#type-annotations) |
| `TID251` | banned API | [Language: type annotations](language-rules.md#type-annotations), [Banned API](#banned-api) |
| `TRY` | exception-handling style | [Language: exceptions](language-rules.md#exceptions), [security and logging](language-rules.md#security-and-logging) |
| `UP` | modern Python syntax | [Language: type annotations](language-rules.md#type-annotations), [Version compatibility](version-compatibility.md) |

`N818` is enabled individually; the rest of the `N` family is not. `PGH003`, `PGH004`, `PLC0415`, `FBT001`, `FBT002`, and `PLW0603` are enabled individually. `FBT003` is not enabled.

## Intentional ignores

The template ignores the following rules on purpose:

| Rule | Why |
| --- | --- |
| `D104` | A package `__init__.py` may have no docstring. |
| `D105` | Magic methods have conventional behavior and do not need a docstring. |
| `D107` | The class docstring covers `__init__`. |
| `D415` | It accepts only ASCII `.`, `?`, and `!`; non-English punctuation would fail. |
| `PT009` | It rejects unittest-style `assertEqual`; unittest projects remain valid. |
| `PT027` | It rejects `unittest.assertRaises`; unittest projects remain valid. |
| `RUF001` | It flags ambiguous Unicode in strings; non-English text is allowed. |
| `RUF002` | It flags ambiguous Unicode in docstrings; non-English text is allowed. |
| `RUF003` | It flags ambiguous Unicode in comments; non-English text is allowed. |
| `TRY003` | It rejects multi-word messages at the raise site; keep messages there. |

Do not remove an intentional ignore without updating the owning rule section and the project rationale. Do not add a global ignore for a single awkward file; use a scoped per-file ignore or a coded suppression.

## Per-file ignores

The template keeps exceptions local to tests:

- `tests/**`: `ANN`, `ARG`, `D`, `FBT001`, `FBT002`, `TC`, `S101`, `S105`, `S106`, `S107`, `S108`, `S311`.
- `conftest.py`: `ANN`, `ARG`, `D`, `FBT001`, `FBT002`, `TC`, `S101`, `S105`, `S106`, `S107`, `S108`, `S311`.

`FBT001`, `FBT002`, and `TC` are ignored in tests and `conftest.py` so parametrized boolean arguments and pytest fixture annotations do not require keyword-only signatures or `TYPE_CHECKING` blocks. The `S105`, `S106`, and `S107` test ignores are for obvious dummy passwords only; they never permit real credentials or personal data. `S108` and `S311` are ignored because tests commonly use temporary paths and non-cryptographic randomness.

Do not extend these ignores to production code. Add a new ignore only with a comment explaining why the rule is inappropriate for those files.

## Banned API

The template bans `__future__.annotations` through `TID251`:

```toml
[tool.ruff.lint.flake8-tidy-imports.banned-api]
"__future__.annotations".msg = "Do not use `from __future__ import annotations`; use quoted annotations or target-native syntax."
```

Use quoted forward references instead. The related settings are intentional:

```toml
[tool.ruff.lint]
future-annotations = false

[tool.ruff.lint.flake8-type-checking]
quote-annotations = true
```

`quote-annotations` makes `TC` quote imports that it moves into `TYPE_CHECKING` on Python 3.11–3.13. On Python 3.14+, PEP 649 defers annotations natively, `TC` does not quote them, and `UP037` removes unneeded quotes. Quote manually when you move an import or an overload yourself on Python 3.11–3.13. `TC004` moves an import out of `TYPE_CHECKING` when it is used at runtime, but it does not catch `get_type_hints`, `get_overloads`, or framework annotation resolution. Keep those imports at runtime manually.

## Import ordering

`typing_extensions` and `_typeshed` are treated as standard-library imports:

```toml
[tool.ruff.lint.isort]
extra-standard-library = ["_typeshed", "typing_extensions"]
```

Keep that grouping; do not move compatibility imports into the third-party block.

Absolute imports are recommended for clarity and refactoring safety. Relative imports within a package are permitted when they match established project practice and stay consistent across the project. `TID252` is not enabled in the template. A project that requires strict absolute imports can enable `TID252` and configure:

```toml
[tool.ruff.lint.flake8-tidy-imports]
ban-relative-imports = "all"  # or "parents"
```

`PLC0415` flags imports outside the top level; a function-level import for a circular or optional dependency needs `# noqa: PLC0415` with a reason. `E402` keeps module-level imports before other code.

## Naming

`N818` is enabled individually; the rest of the `N` family is not. `N806` would conflict with local `UPPER_SNAKE_CASE` constants. `N818` requires custom `Exception` subclasses to end with `Error`; it does not check `BaseException` or `Warning` subclasses. A non-error control-flow exception may suppress `N818` with a reason.

The semantic naming conventions carry `Review` in [Style: naming](style-rules.md#naming). This includes defining-boundary analysis for internal symbols and distinguishing object-reference callbacks from names required by an external contract.

## Typing

- `ANN` checks function signatures only. Class attribute and empty-container annotations carry `Review`.
- `ANN401` rejects `Any` in function signatures. `Any` in variables and class attributes carries `Review`.
- `RUF012` requires `ClassVar` for mutable class defaults. `ClassVar` elsewhere, `Final`, and `Self` carry `Review`.
- `UP006`, `UP007`, `UP035`, and `UP045` enforce built-in generics, PEP 604 unions, and `collections.abc` imports.
- `UP040`, `UP046`, and `UP047` enforce PEP 695 only at a 3.12+ target. A 3.11 target cannot use PEP 695 syntax.
- `TID251` bans `from __future__ import annotations`; see [Banned API](#banned-api).
- `TC001`–`TC003` move typing-only imports into `TYPE_CHECKING`; `TC004` moves them out when they are used at runtime. `TC` does not check `@overload` placement; it is `Review`. `quote-annotations = true` quotes imports moved by `TC` on Python 3.11–3.13; on 3.14+, PEP 649 defers evaluation and `UP037` removes quotes. Quote manually when moving an import or overload yourself on Python 3.11–3.13.
- `PGH003` and `PGH004` require codes on `type: ignore` and `noqa`; reasons are a separate `Review` rule.

## Docstrings

The template uses the Google convention:

```toml
[tool.ruff.lint.pydocstyle]
convention = "google"
```

`D104`, `D105`, `D107`, and `D415` are ignored globally. `D415` is ignored because it accepts only ASCII `.`, `?`, and `!`; non-English punctuation such as `。` or `？` would fail. Terminal punctuation is `Review`. `D400` and `D401` are disabled by the Google convention, so declarative first lines are allowed.

`D417` checks completeness only when a docstring contains an `Args` section, and it recognizes the English header. Keep section headers in English. Attribute docstrings are not checked by Ruff; documenting every public field of a public data model is `Review`. Use a per-field docstring, an `Attributes:` section, or the framework's native field description. Keep one style per project.

Ruff does not enforce separate-line indentation for argument, return, yield, exception, or attribute descriptions; that layout is `Review`. Requiring every applicable section for public functions and methods, reserving summary-only docstrings for `_` names and functions in internal modules, and documenting public model fields are also `Review`.

Docstring content language is determined by the project, not by this configuration.

## Exception handling

- `S110` and `S112` check typed exceptions because the template sets `check-typed-exception = true`. An intentional ignore uses `contextlib.suppress(SpecificError)`, not `except ...: pass` or `continue`.
- `BLE001` allows `except Exception` when the handler logs the exception with its traceback (`exception()` or `exc_info=True`) or re-raises. Because `BLE001` does not recognize a boundary handler that translates an exception into a structured failure return, that handler needs `# noqa: BLE001` with a reason; a logged handler must not add it, because `RUF100` flags an unused `noqa`.
- `TRY003` is ignored because it rejects multi-word messages at the raise site. `TRY300` moves returns to `else`; `TRY301` moves raises out of a `try` that catches them.
- `S101` flags `assert` in production code; tests and `conftest.py` ignore it. A genuine internal invariant needs `# noqa: S101` with a reason.
- `E722` flags bare `except:`; `B904` requires `raise ... from exc` inside an exception handler.
- `TRY400` flags `logger.error` inside an exception handler; use `logger.exception()` or `exc_info=True` when logging the traceback.

## Security and logging

- `S105`, `S106`, and `S107` catch common hardcoded password patterns, but not every token, key, or personal-data value. Because they match by identifier name, a non-secret constant (such as a header name or OAuth token type) may need `# noqa: S105` with a reason after verifying no secret is present. The `tests/**` and `conftest.py` ignores are only for obvious dummy values.
- `S102` and `S307` ban `eval` and `exec`; `S301` and `S302` ban `pickle` and `marshal`; `S602` bans `shell=True`; `S311` flags non-cryptographic random use; `S108` flags hardcoded temporary paths.
- `T20` bans `print` and `pprint` (`T201` and `T203`). A CLI that intentionally writes to stdout needs a coded `# noqa: T201` with a reason.
- The logging facility is project-specific: standard `logging`, loguru, or structlog are all acceptable. Ruff does not enforce lazy formatting; it carries `Review`.

## Formatter

`ruff format` is the formatter. The only configured formatting option is:

```toml
[tool.ruff.format]
docstring-code-format = true
```

Do not run Black, isort, or another formatter alongside Ruff on the same files. The template does not set `line-length`; Ruff's default is 88. A project may set a different value, but `E501` still enforces the configured limit.

Do not enable lint rules that conflict with the formatter, such as `COM812` or `ISC001`, without checking Ruff's compatibility guidance.

## Common conflicts

- `target-version` and `requires-python` disagree: `target-version` wins. Keep them consistent.
- `E501` fires on a long URL, string literal, or comment: refactor when practical, otherwise add `# noqa: E501` with a reason.
- `RUF100` reports an unused `noqa`: remove the suppression. Do not silence `RUF100`.
- `BLE001` and `TRY400` interact: a handler that logs with traceback does not need `# noqa: BLE001`; adding it triggers `RUF100`.
- `T20` fires on intentional CLI output: add `# noqa: T201` with a reason.
- `S101` fires in a test file outside `tests/**`: move the test or add a scoped per-file ignore; do not ignore `S101` globally.
- `FBT001`/`FBT002` fire on a framework signature that requires a positional boolean: use a project-level ignore or a coded suppression.
- `PT009`/`PT027` are ignored globally for unittest projects. A pytest project can re-enable them.
- `D415` is ignored, so non-English terminal punctuation does not fail. `D417` still checks an existing `Args` section.
- `PGH003`/`PGH004` require a code, not a reason. The reason is a separate `MUST` rule verified by `Review`.
- `--unsafe-fixes` can change behavior. Never apply it without inspecting the diff.
- A whole-repository `ruff check --fix` can rewrite unrelated files. Use focused paths unless the user asks for a full cleanup.
