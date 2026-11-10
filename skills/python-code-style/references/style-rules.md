# Style Rules

Layout, imports, naming, formatting, docstrings, comments, code examples, and exports for Python source files, tests, and documentation.

## Module and package layout

**Applies to.** File structure, member order, import-time behavior, and the `if __name__ == "__main__":` guard.

**Verified by.** `Ruff: PTH, PTH123`; `Review` for import-time behavior. Import placement and order are owned by [Imports](#imports).

- **MUST** keep import time free of I/O, network calls, global state mutation, and business logic. (`Review`)

- **SHOULD** keep module-level code to imports, definitions, constants, type aliases, and the `if __name__ == "__main__":` guard. (`Review`)

- **SHOULD** use `pathlib` for path manipulation and `Path.open()` for file access. (`Ruff: PTH, PTH123`)

- **SHOULD** order members as: module docstring, imports, constants, type aliases, classes, functions, and the entry guard. Package exports are owned by [Public API and exports](#public-api-and-exports). Dependency order wins when a name is evaluated at import time. (`Review`)

- **SHOULD** keep public members before private `_` helpers. Dunder methods keep their conventional placement. (`Review`)

Text-encoding rules are owned by [Date, time, and I/O](language-rules.md#date-time-and-io). Section separator comments are owned by [Comments](#comments).

**Integrated example.**

```python
# Good: definitions only at import time; entry guard at the bottom
from pathlib import Path


def load_config(path: Path) -> dict[str, str]:
    """Loads a configuration file."""
    ...


if __name__ == "__main__":
    load_config(Path("config.toml"))
```

**Exceptions.** A framework that requires import-time registration may execute code at import time. Isolate that code in a dedicated module and document why.

## Imports

**Applies to.** Import order, grouping, absolute and relative imports, aliases, and re-exports.

**Verified by.** `Ruff: I, F401, F403, E402, PLC0415`; the rest is `Review`.

- **SHOULD** order imports with isort. (`Ruff: I`)

- **SHOULD** keep imports at the top level. A function-level import for a circular or optional dependency needs `# noqa: PLC0415` with the reason. (`Ruff: E402, PLC0415`)

- **SHOULD** prefer absolute imports for clarity and refactoring safety. Relative imports within a package are acceptable when they match established project practice and stay consistent across the project. (`Review`)

- **SHOULD NOT** use wildcard imports. (`Ruff: F403`)

- **SHOULD NOT** leave unused imports. (`Ruff: F401`)

- **SHOULD NOT** create a module-level class that shadows an imported class it subclasses or wraps. Use module-qualified access or a private `_Base` alias. (`Review`)

  ```python
  # Good: keep the imported class explicit
  from pathlib import Path as _BasePath


  class Path(_BasePath): ...


  # Bad: the class shadows the imported name
  from pathlib import Path


  class Path(Path): ...
  ```

The shared isort configuration groups `typing_extensions` and `_typeshed` with the standard library; see [Import ordering](ruff-config.md#import-ordering). The ban on `from __future__ import annotations` and the placement of typing-only imports are owned by [Type annotations](language-rules.md#type-annotations).

**Integrated example.**

```python
# Good: standard library, third party, first party; no wildcard
import json
from pathlib import Path

from pydantic import BaseModel

from myapp.models import User
```

**Exceptions.** A generated module may need a wildcard re-export. Isolate it and document the generator.

## Naming

**Applies to.** Modules, packages, classes, functions, variables, constants, type variables, and exceptions.

**Verified by.** `Ruff: N818, A`; the rest is `Review`.

- **SHOULD** end custom exception classes with `Error`. (`Ruff: N818`)

- **SHOULD** use one name for one concept and one verb for one action across the project, especially in public APIs. (`Review`)

- **SHOULD** use PEP 8 casing: `snake_case` for modules, functions, and variables; `PascalCase` for classes; `UPPER_SNAKE_CASE` for constants and enum members. (`Review`)

- **SHOULD** name booleans with a positive predicate (`is_ready`, `has_access`, `enabled`). (`Review`)

- **SHOULD** use plural nouns for collections (`users`) and `<value>_by_<key>` for mappings (`users_by_id`). Do not add `_list` or `_dict`. (`Review`)

- **SHOULD** include units in numeric names (`timeout_seconds`, `size_bytes`). (`Review`)

- **SHOULD** use verb phrases for functions (`load_config`). Alternate constructors use `from_*`; factories use `create_*`, `build_*`, or `make_*`. (`Review`)

- **SHOULD** use nouns or adjectives for properties (`size`, `is_empty`) and `to_*`/`as_*` for converters. (`Review`)

- **SHOULD** use `iter_*` or `iterate_*` for generic iteration, keep one form per project, and prefer a semantic name such as `stream_*` when one fits. (`Review`)

- **SHOULD** omit an `async_` prefix by default. When providing paired sync/async functions, prefix both (`sync_fetch`/`async_fetch`). (`Review`)

- **SHOULD** use singular nouns for classes, adjective names for protocols, and an `Async` prefix for paired async classes. End mixins with `Mixin` and warning classes with `Warning`. (`Review`)

- **SHOULD** write a single abbreviation in uppercase (`HTTPClient`) and treat adjacent abbreviations as words (`HttpUrl`). (`Review`)

- **SHOULD** use `T`, `U`, `V`, or descriptive names for type variables; `KT`/`VT` for mappings; `P` for parameter specs; `Ts` for variadic tuples. (`Review`)

- **SHOULD** use domain names in loops and unpacking: `for user_id, profile in users_by_id.items()`. Use `key`, `value`, `item`, or `index` only for generic containers. Restrict single letters to obvious micro-scopes such as one-line comprehensions. (`Review`)

  ```python
  # Good: domain names make the key and value clear
  for user_id, profile in users_by_id.items():
      send_notification(user_id, profile.email)

  # Bad: single-letter names obscure what k and v represent
  for k, v in users_by_id.items():
      send_notification(k, v.email)
  ```

- **SHOULD** use `e`, `err`, or `exc` consistently for exception variables. (`Review`)

- **SHOULD** use full words in public names. Acronyms are acceptable, written in lowercase in snake_case names (`http_client`). (`Review`)

- **SHOULD** use a leading underscore for internal packages, modules, functions, classes, methods, and module-level variables. (`Review`)

- **SHOULD** determine internal visibility from the symbol's defining boundary: packages without public APIs or cross-package consumers, modules used only in one package, functions, classes, and module globals used only in one module, methods used only in one class, and nested helpers used only in one enclosing function. (`Review`)

- **SHOULD** treat names required by public exports, public type signatures, protocols, or name-based framework dispatch as external contracts rather than internal symbols. (`Review`)

- **SHOULD** treat callbacks registered or passed only by object reference as internal to their defining boundary when their Python names are not external contracts. (`Review`)

- **SHOULD NOT** shadow Python builtins. (`Ruff: A`)

- **SHOULD NOT** use `_flag` or negative boolean names. (`Review`)

- **SHOULD NOT** use `utils`, `helpers`, or `common` as dumping-ground module names. (`Review`)

- **SHOULD NOT** use `__name` for privacy; double underscores trigger name mangling. (`Review`)

- **MAY** use `_` for an intentionally unused value. (`Review`)

**Integrated example.**

```python
# Good: one concept, positive boolean, unit in the name
def fetch_user(user_id: str, *, include_inactive: bool = False) -> User:
    timeout_seconds = 30
    ...


# Good: the registry key is public, but the callback name is internal.
def _sync_user() -> None:
    ...


callbacks = {"sync-user": _sync_user}


# Bad: mixed vocabulary, negative boolean, unitless timeout
def load_account(account_id: str, *, no_cache: bool = False) -> User:
    timeout = 30
    ...
```

**Exceptions.** Framework-imposed names and established public APIs may keep a different name. Record the reason in the project's standards.

## Formatting and line structure

**Applies to.** Formatter output, line length, blank lines, statement layout, and string layout.

**Verified by.** `Format: ruff format`; `Ruff: E, W`; the rest is `Review`.

- **SHOULD** keep the files formatted with `ruff format`. (`Format: ruff format`)

- **SHOULD** keep lines within the configured `line-length`. (`Ruff: E501`)

- **SHOULD** use two blank lines between top-level definitions and one blank line between methods. (`Review`)

- **SHOULD** use a single blank line between major phases in a long function body (roughly 20 lines or more). Keep short functions compact. Treat a single call or data structure spanning multiple lines as one phase. (`Review`)

  ```python
  # Good: phases separated by a single blank line
  def aggregate_metrics(events: list[Event], *, window_seconds: int) -> Metrics:
      if window_seconds <= 0:
          raise ValueError("window_seconds must be positive")

      buckets: dict[int, list[Event]] = {}
      for event in events:
          bucket = int(event.timestamp) // window_seconds
          buckets.setdefault(bucket, []).append(event)

      return Metrics(
          counts={bucket: len(items) for bucket, items in buckets.items()},
          total=sum(event.duration_ms for event in events),
      )
  ```

- **SHOULD** use parentheses for line continuation. (`Review`)

- **SHOULD** write one statement per line. (`Review`)

- **SHOULD** use f-strings for interpolation. In logging calls, use the logging facility's lazy formatting instead. See [Security and logging](language-rules.md#security-and-logging). (`Review`)

- **SHOULD NOT** run Black, isort, or another formatter on the same files. (`Review`)

- **SHOULD NOT** leave trailing whitespace or blank-line whitespace. (`Ruff: W291, W293`)

- **SHOULD NOT** use backslash continuations. (`Review`)

- **SHOULD NOT** use semicolons. (`Review`)

- **MAY** use implicit string concatenation for a long message; keep the fragments aligned. (`Review`)

The template does not set `line-length`, so Ruff's default of 88 applies. A project may set a different value; keep the documentation and the configuration consistent. Long URLs, long string literals, and long comments may need a coded suppression rather than an awkward wrap.

**Exceptions.** Generated code may not match the formatter. Keep it in a separate file and exclude it from formatting and linting explicitly.

## Docstrings

**Applies to.** Public modules, classes, functions, methods, and the public fields of public data models (`@dataclass`, `TypedDict`, `NamedTuple`, or a framework model class with declarative fields). A model is public when it is part of the package's public API under [Naming](#naming). A field is public when its name does not begin with `_` and it is not a `ClassVar`, `model_config`, or another framework configuration attribute.

**Verified by.** `Ruff: D`; `D104`, `D105`, `D107`, and `D415` are ignored; `D417` checks only docstrings with an `Args` section; the rest is `Review`.

- **SHOULD** use the Google docstring convention. (`Ruff: D`)

- **SHOULD** document public modules, classes, functions, and methods. (`Ruff: D`)

- **SHOULD** include every applicable `Args`, `Returns`, `Yields`, and `Raises` section in public function and method docstrings. (`Review`)

- **SHOULD** use a one-line summary, a blank line, and then sections in order: `Args`, `Returns`, `Yields`, `Raises`, `Attributes`. (`Review`)

- **SHOULD** list parameters in signature order as `name (type, optional):` and state defaults in the description. (`Review`)

- **SHOULD** use `name (type):` for `Attributes`, and omit the type when the annotation is adjacent. (`Review`)

- **SHOULD** use `Yields` for generators and omit `Returns` when returning `None`. (`Review`)

- **SHOULD** place each argument, return, yield, exception, and attribute description on a separate line below its declaration, indented one level; continuation lines use the same indentation. (`Review`)

- **SHOULD** document every public field of a public data model; a class summary alone does not document its fields. (`Review`)

- **SHOULD** use a per-field docstring, an `Attributes:` section, or the framework's native field description for framework models such as Pydantic. Keep one style per project. (`Review`)

- **SHOULD** use either imperative mood or declarative sentences consistently across the project, and end sentences with punctuation in the document's language. Keep section headers in English. (`Review`)

- **SHOULD** add an `Examples:` section when usage is not obvious. (`Review`)

- **MAY** write docstrings in the project's language. (`Review`)

Docstring code formatting is owned by [Code examples](#code-examples).

**Integrated example.**

```python
def fetch_users(query: str, *, limit: int = 100) -> list[User]:
    """Fetches matching users from the directory.

    Args:
        query (str):
            Search term matching name or email address.
        limit (int, optional):
            Maximum records to retrieve. Defaults to 100.

    Returns:
        list[User]:
            Matching user records sorted in ascending creation order.

    Raises:
        ConnectionTimeoutError:
            If the remote directory service fails to respond.
    """
```

**Exceptions.** Functions and methods whose names begin with `_` may use a summary-only docstring. A function or method defined in an internal module may also use a summary-only docstring, even when its name has no leading underscore. A module is internal when it is outside the package's public API as defined in [Naming](#naming), for example because its name begins with `_` or it is imported only within its own package. Package docstrings, magic methods, and `__init__` are exempt from the docstring-presence rule.

## Comments

**Applies to.** Inline comments, block comments, TODOs, and section separators.

**Verified by.** `Ruff: ERA001`; the rest is `Review`.

- **SHOULD** use comments only for non-obvious constraints, trade-offs, upstream defects, and reference links. (`Review`)

- **SHOULD NOT** leave commented-out code. Delete `# old_call()` instead of keeping it in the file. (`Ruff: ERA001`)

- **SHOULD NOT** narrate what the code does or restate annotations. (`Review`)

- **SHOULD NOT** leave ownerless `TODO` or `FIXME` markers. Include an issue link or an owner. (`Review`)

- **MAY** use a separator comment with a short noun phrase sparingly in a long module, keeping it within the line limit. (`Review`)

- **MAY** write comments in the project's language. (`Review`)

**Integrated example.**

```python
# Good: explains a non-obvious constraint
# The upstream API returns 200 for a queued job, not for a finished one.
response = client.submit_job(payload)

# Bad: restates the code and leaves an ownerless marker
# Call the API
response = client.submit_job(payload)  # TODO: handle errors
```

**Exceptions.** A comment that quotes a specification or upstream issue may be longer than usual. Keep it accurate and link the source.

## Code examples

**Applies to.** Examples in docstrings, README and documentation files, and tests.

**Verified by.** `Check: markdownlint` MD040 for fenced blocks; `Format: ruff format` for docstring code; the rest is `Review`.

- **MUST NOT** include realistic secrets or personal data in an example. Use placeholders such as `<token>` or `REDACTED`. (`Review`)

- **SHOULD** use a language tag on every fenced code block. (`Check: markdownlint`)

- **SHOULD** format Python code in docstrings with `ruff format`. (`Format: ruff format`)

- **SHOULD** apply the same standards to example code as to production code, except where the example intentionally illustrates a violation. (`Review`)

- **SHOULD** use a `python` fence only for code that parses on the project's minimum Python version, or carry a `# Python 3.x+` marker and show the compatible alternative; see [Version-specific examples](version-compatibility.md#version-specific-examples). Use `text` for pseudo-code, intentionally invalid code, or output. (`Review`)

- **SHOULD** keep examples free of APIs that are unavailable in the minimum Python version unless the example illustrates the version difference, and run or parse examples on the minimum version in CI when a docs check exists. (`Review`)

- **SHOULD** keep each example minimal and focused on one concept or rule. (`Review`)

- **SHOULD** label contrasting examples `# Good` and `# Bad`, and state why the bad one is wrong. (`Review`)

- **SHOULD** treat examples as fragments: include what the example needs, elide unrelated code with `...`, and never contradict the rule being illustrated. (`Review`)

- **SHOULD** include the imports and definitions needed to understand the example, or mark the elision. (`Review`)

- **SHOULD** use `>>>` only for examples that run as doctests. (`Review`)

- **SHOULD NOT** use network, filesystem, clock, randomness, or external services in examples unless the example is about them; use fakes or stubs. (`Review`)

- **SHOULD NOT** add suppressions to a bad example just to keep it in a linted file; move it to documentation or exclude it from the check. (`Review`)

- **MAY** separate statement-level examples with a single blank line. Top-level definitions and classes keep the two blank lines from [Formatting and line structure](#formatting-and-line-structure). (`Review`)

## Public API and exports

**Applies to.** `__all__`, package re-exports, and public and private names.

**Verified by.** `Ruff: F401, F822, RUF022`; the rest is `Review`. Wildcard imports are owned by [Imports](#imports); member ordering is owned by [Module and package layout](#module-and-package-layout).

- **SHOULD** sort `__all__`. (`Ruff: RUF022`)

  ```python
  # Good: explicit, sorted re-exports in a package __init__.py
  from myapp.models import Account, User

  __all__ = ["Account", "User"]
  ```

- **SHOULD** ensure every name in `__all__` is defined and exported. (`Ruff: F401, F822`)

- **SHOULD** declare `__all__` only in a re-exporting package `__init__.py`. Ordinary modules omit it. (`Review`)

- **SHOULD** re-export selected symbols with explicit imports in `__init__.py`. (`Review`)

- **MAY** declare `__all__` in a module that intentionally exposes a stable public surface. (`Review`)

**Exceptions.** Generated re-export modules may need a different layout. Keep the generator and the generated file in sync.
