# Language Rules

Typing, functions, data modeling, comprehensions, async code, exceptions, date/time and I/O, testing, security, logging, performance, and suppressions.

## Type annotations

**Applies to.** Function signatures, class attributes, containers, generics, type aliases, and typing-only imports.

**Verified by.** `Ruff: ANN, ANN401, UP006, UP007, UP035, UP040, UP045, UP046, UP047, TC001–TC004, TID251, RUF012`; the rest is `Review`.

- **MUST** annotate mutable class-level state with `ClassVar[T]`, for example `items: ClassVar[list[str]] = []`. (`Ruff: RUF012`)

- **MUST** keep imports used at runtime outside `TYPE_CHECKING`, including base classes, `isinstance` checks, decorators, and framework annotations resolved at runtime. (`Ruff: TC004`; `Review`)

- **MUST** quote forward references and types imported under `TYPE_CHECKING` on Python 3.11–3.13, and for definition-time evaluations across all versions. On Python 3.14+, omit quotes where PEP 649 defers evaluation natively. (`Review`)

- **MUST NOT** use `from __future__ import annotations`. Quote forward references instead. (`Ruff: TID251`)

- **SHOULD** annotate every function parameter and return value. (`Ruff: ANN`)

- **SHOULD** use built-in generics and PEP 604 unions, and import abstract collections from `collections.abc`. (`Ruff: UP006, UP007, UP035, UP045`)

- **SHOULD** move typing-only imports behind `if TYPE_CHECKING:`. (`Ruff: TC001, TC002, TC003`)

- **SHOULD** use PEP 695 generics and `type` aliases when the minimum Python version is 3.12 or newer; see the [feature matrix](version-compatibility.md#feature-matrix). (`Ruff: UP040, UP046, UP047`; `Since: 3.12`)

- **SHOULD** annotate class attributes and empty-container initializations (`items: list[str] = []`). (`Review`)

- **SHOULD** use `Final[T]` for constants that must not be rebound, for example `MAX_RETRIES: Final = 3`. (`Review`)

- **SHOULD** annotate a method returning its own instance with `-> Self`, including fluent setters and `__enter__`, for example `def __enter__(self) -> Self`. (`Review`)

- **SHOULD** use `typing_extensions` only when the minimum Python version lacks the feature. Do not use it for features already available in the minimum version. (`Review`)

- **SHOULD** keep `@overload` signatures where the runtime needs them; move typing-only overloads behind `TYPE_CHECKING`. (`Review`)

- **SHOULD NOT** use `Any` in function signatures. Use `object` when any value is acceptable or a `Protocol` when behavior is expected. (`Ruff: ANN401`)

  ```python
  from typing import Any, Protocol


  # Good: object accepts any value
  def log_value(value: object) -> None: ...


  class Reader(Protocol):
      """Describes the behavior the function needs."""

      def read(self) -> bytes: ...


  # Bad: Any hides the contract
  def log_value(value: Any) -> None: ...
  ```

- **MAY** use `Any` at a dynamic boundary after validating and narrowing the value. (`Review`)

**Integrated example.**

```python
# Python 3.11–3.13 (on 3.14+, PEP 649 defers evaluation natively; omit quotes)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from myapp.models import User


def first_user(users: "Iterable[User]") -> "User | None":
    """Returns the first user, or None when the iterable is empty."""
    return next(iter(users), None)
```

**Exceptions.** A framework that resolves annotations at runtime may need a runtime import. Keep the import outside `TYPE_CHECKING` and document the framework behavior. On 3.11, use `TypeVar`, `Generic`, and `TypeAlias` instead of PEP 695 syntax.

## Functions and parameters

**Applies to.** Function design, parameter lists, default values, complexity, and closure behavior.

**Verified by.** `Ruff: ARG, B006, B008, B023, C90, FBT001, FBT002, PLW0603, RET505–RET508`; the rest is `Review`.

- **MUST** bind loop variables explicitly when a closure captures them. (`Ruff: B023`)

  ```python
  # Good: bind the loop variable as a default
  handlers = [lambda item=item: handle(item) for item in items]

  # Bad: every closure sees the last item
  handlers = [lambda: handle(item) for item in items]
  ```

- **MUST NOT** use a mutable object as a default value. Use a `None` sentinel created inside the function, or `field(default_factory=...)` for a dataclass. (`Ruff: B006`)

  ```python
  # Good: create the default inside the function
  def add_item(item: str, items: list[str] | None = None) -> list[str]:
      if items is None:
          items = []
      items.append(item)
      return items


  # Bad: the list is created once and shared
  def add_item(item: str, items: list[str] = []) -> list[str]:
      items.append(item)
      return items
  ```

- **MUST NOT** call a function in a default argument. The value is created once at definition time and shared by every call. (`Ruff: B008`)

- **SHOULD** make boolean parameters keyword-only. (`Ruff: FBT001, FBT002`)

  ```python
  # Bad: positional boolean arguments obscure meaning at the call site
  def render(text: str, cache: bool = True, strip: bool = False) -> str: ...


  render("hello", True, False)


  # Good: keyword-only booleans
  def render(text: str, *, cache: bool = True, strip: bool = False) -> str: ...


  render("hello", cache=True, strip=False)
  ```

- **SHOULD** remove unnecessary `else` blocks after `return`, `raise`, `continue`, or `break`. (`Ruff: RET505, RET506, RET507, RET508`)

- **SHOULD** keep cyclomatic complexity within Ruff's configured maximum. (`Ruff: C90`)

- **SHOULD** remove unused arguments or prefix an intentionally unused argument with `_`. (`Ruff: ARG`)

- **SHOULD** keep each function at one level of abstraction and extract a helper instead of nesting deeply. (`Review`)

- **SHOULD** make optional parameters keyword-only when several are optional. (`Review`)

- **SHOULD** introduce a dataclass, `TypedDict`, or `NamedTuple` parameter object when parameters form a cohesive group or no longer fit on one line. (`Review`)

- **SHOULD** return results instead of writing through mutable arguments. (`Review`)

- **SHOULD** use `nonlocal` only for closure-local state, and keep I/O at the boundaries. (`Review`)

- **SHOULD NOT** use the `global` statement. (`Ruff: PLW0603`)

- **SHOULD NOT** hide a public API signature behind `**kwargs`. Decorators and narrow forwarding wrappers are exempt. (`Review`)

Blank-line conventions inside function bodies are owned by [Style: formatting and line structure](style-rules.md#formatting-and-line-structure).

**Exceptions.** A framework may require a function call in a default, such as a dependency-injection marker. Use a coded suppression and a project-level ignore instead of scattering `# noqa: B008`.

## Data modeling

**Applies to.** Structured values, immutability, validation, and enums.

**Verified by.** `Review`. Datetime construction is owned by [Date, time, and I/O](#date-time-and-io); mutable class state is owned by [Type annotations](#type-annotations).

- **MUST** validate external input once at the boundary, then pass typed data through the rest of the code. (`Review`)

- **SHOULD** use a dataclass, `TypedDict`, or `NamedTuple` for structured internal data, not a bare `dict` or `tuple`. (`Review`)

- **SHOULD** model immutable value objects with `@dataclass(frozen=True, slots=True)`. Use `tuple` and `frozenset` for sequence and set fields. Omit `slots=True` when the object needs `__dict__`, weak references, or a specific pickling or ORM contract. (`Review`)

- **SHOULD** use the built-in `frozendict` when the minimum Python version is 3.15 or newer, or a maintained immutable mapping implementation on earlier versions, for a mapping field of a value object; see the [feature matrix](version-compatibility.md#feature-matrix). `MappingProxyType` is a read-only view, not an equivalent: it is unhashable and reflects mutations of the wrapped mapping. (`Review`; `Since: 3.15`)

- **SHOULD** validate invariants in `__post_init__` or a validator. Keep constructors free of I/O and expensive recomputation. (`Review`)

- **SHOULD** use `Enum` for a closed set of named values. (`Review`)

- **SHOULD** replace a class that only holds static methods with module-level functions, unless a framework requires the class. (`Review`)

**Integrated example.**

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Configures retry behavior for outbound requests."""

    max_attempts: int = 3
    """Maximum number of attempts, including the first."""
    base_delay_seconds: float = 0.5
    """Initial delay before the first retry."""
    retryable_status_codes: tuple[int, ...] = (429, 503)
    """HTTP status codes that allow a retry attempt."""

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            msg = "max_attempts must be at least 1"
            raise ValueError(msg)
        if self.base_delay_seconds < 0:
            msg = "base_delay_seconds must not be negative"
            raise ValueError(msg)
```

**Exceptions.** An ORM or framework may require mutable models or naive datetimes at the storage boundary. Convert at the edge and document the constraint.

## Comprehensions and iteration

**Applies to.** List, set, and dict comprehensions, generator expressions, nested loops, and `zip`.

**Verified by.** `Ruff: C4, FURB, B905`; the rest is `Review`.

- **MUST** pass `strict=` to `zip()` when it is called with two or more iterables or a starred argument. (`Ruff: B905`)

- **SHOULD** fix mechanical comprehension and iteration simplifications reported by `C4` and `FURB`. (`Ruff: C4, FURB`)

- **SHOULD** keep a comprehension to one `for` and at most one `if`. (`Review`)

- **SHOULD** allow a second `for` only to flatten a two-dimensional structure. (`Review`)

- **SHOULD** use `itertools.product` for a parallel Cartesian product, and an explicit loop for a dependent nested loop or multi-step logic. (`Review`)

- **SHOULD** remember that `itertools.product` materializes its inputs. Keep a nested generator for large or infinite streams when streaming matters, and state why. (`Review`)

- **SHOULD** use a generator expression for a large stream when a list is not required. (`Review`)

- **MAY** use a comprehension for a simple transformation or filter. (`Review`)

**Integrated example.**

```python
import itertools

# Good: flatten a two-dimensional structure
flat_matrix = [cell for row in matrix for cell in row]

# Good: parallel Cartesian product
coords = [f(x, y) for x, y in itertools.product(xs, ys)]

# Bad: nested dependent loops and multiple filters
admins = [u.name for g in groups if g.is_active for u in g.users if u.is_admin]
```

**Exceptions.** A comprehension may be less readable than a loop when it has multiple filters or multi-step logic. Use the loop.

## Async and concurrency

**Applies to.** `async def` functions, tasks, cancellation, and resource ownership.

**Verified by.** `Ruff: ASYNC`; the rest is `Review`.

- **MUST** keep blocking I/O and CPU-bound work out of `async def`. Offload it with `asyncio.to_thread` or an executor. (`Ruff: ASYNC`; `Review`)

  ```python
  import asyncio


  async def load(url: str) -> bytes:
      # Bad: blocks the event loop
      return fetch_sync(url)


  async def load_async(url: str) -> bytes:
      # Good: offload blocking work
      return await asyncio.to_thread(fetch_sync, url)
  ```

- **MUST** manage resources with `async with` or a `finally` block. (`Review`)

- **MUST NOT** swallow `CancelledError`; let cancellation propagate, and re-raise it after any cleanup. (`Review`)

- **SHOULD** use `asyncio.TaskGroup` for structured concurrency, and bound waits with `asyncio.timeout`. (`Review`)

  ```python
  import asyncio


  async def fetch_all(urls: list[str], timeout_seconds: float = 10.0) -> list[str]:
      """Fetches every URL concurrently and returns the responses in order."""
      async with asyncio.timeout(timeout_seconds), asyncio.TaskGroup() as group:
          tasks = [group.create_task(fetch(url)) for url in urls]
      return [task.result() for task in tasks]
  ```

- **SHOULD** keep a consistent async or sync boundary; do not mix blocking and async clients in one path. (`Review`)

**Exceptions.** A framework may provide its own task group or cancellation semantics. Follow the framework's contract and document the difference.

## Exceptions

**Applies to.** Raising, catching, chaining, and translating exceptions.

**Verified by.** `Ruff: BLE001, B904, E722, S101, S110, S112, TRY300, TRY301`; the rest is `Review`.

- **MUST** chain a translated exception with `raise NewError(...) from exc`. (`Ruff: B904`)

- **MUST** log the traceback, re-raise, or return a structured failure at a boundary when catching `Exception`. Because `BLE001` checks only logging and re-raising, a boundary handler that returns a failure needs `# noqa: BLE001` with a reason. (`Ruff: BLE001`; `Review`)

- **MUST NOT** use a bare `except:`. (`Ruff: E722`)

- **MUST NOT** swallow an exception silently. Use `contextlib.suppress` for an intentional, narrowly scoped ignore. (`Ruff: S110, S112`; `Review`)

  ```python
  import contextlib

  # Good: explicit, narrow suppression
  with contextlib.suppress(FileNotFoundError):
      path.unlink()

  # Bad: silent swallow
  try:
      path.unlink()
  except FileNotFoundError:
      pass
  ```

- **MUST NOT** use `assert` for input validation in production code. Use `ValueError` or `TypeError`. (`Ruff: S101`)

- **SHOULD** move a return in a `try` block to `else` when the `try` has an `except`. (`Ruff: TRY300`)

- **SHOULD** move a raise out of a `try` block when the same `try` catches it. (`Ruff: TRY301`)

- **SHOULD** catch specific exceptions. Reserve broad catches for process boundaries. (`Review`)

- **SHOULD** keep `try` blocks minimal: place only the raising call inside `try`, and move validations and early raises before it. (`Review`)

- **SHOULD** raise project-specific exception types for errors callers should handle. Do not leak raw `KeyError` or `AttributeError` across an API boundary. (`Review`)

- **SHOULD** keep exception messages at the raise site; `TRY003` is ignored on purpose. (`Review`)

Logging a caught exception with its traceback, and keeping secrets out of messages and logs, are owned by [Security and logging](#security-and-logging).

**Integrated example.**

```python
import json


# Bad: giant try block, broad catch, and lost traceback
def load_bad(url: str) -> Record:
    try:
        raw = fetch_payload(url)
        parsed = json.loads(raw)
        return save_to_db(parsed)
    except Exception:
        raise DatabaseError("Save failed")


# Good: minimal try, specific catch, else return, and chained exception
def load_good(url: str) -> Record:
    raw = fetch_payload(url)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as err:
        raise PayloadFormatError(f"Malformed json from {url}") from err
    else:
        return save_to_db(parsed)
```

**Exceptions.** A genuine internal invariant may use `assert` with `# noqa: S101` and a reason. A non-error control-flow exception may suppress `N818` with a reason.

## Date, time, and I/O

**Applies to.** Datetime construction, UTC storage, text encoding, and temporary files.

**Verified by.** `Ruff: DTZ, S108`; the rest is `Review`. Path handling is owned by [Style: module and package layout](style-rules.md#module-and-package-layout).

- **MUST** construct datetimes with an explicit timezone. (`Ruff: DTZ`)

- **MUST** pass `encoding=` explicitly for text I/O when the minimum Python version is below 3.15. (`Review`)

- **MUST NOT** use `datetime.utcnow()` or a naive `datetime.now()`. (`Ruff: DTZ`)

- **MUST NOT** hardcode a temporary file path. Use `tempfile`. (`Ruff: S108`)

- **SHOULD** parse and store datetimes in UTC, and convert at the edges. (`Review`)

- **SHOULD** use `Path.read_text()` and `Path.write_text()` for simple text files, and a context manager for streams. (`Review`)

- **SHOULD** distinguish text and binary I/O, and pass `newline=` when working with CSV files. (`Review`)

**Integrated example.**

```python
from datetime import UTC, datetime
from pathlib import Path


def event_timestamp() -> datetime:
    """Returns the current UTC timestamp."""
    return datetime.now(UTC)


def read_events(path: str | Path) -> list[str]:
    """Reads non-empty event lines from a UTF-8 text file."""
    text = Path(path).read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line]
```

**Exceptions.** A library may require naive datetimes at its boundary. Convert immediately and document the requirement.

## Testing

**Applies to.** Test naming, structure, assertions, parameterization, isolation, and regression coverage.

**Verified by.** `Ruff: PT`; the rest is `Review`.

- **MUST** keep unit tests isolated: no network, real clock, unseeded randomness, or execution order. Inject or freeze external dependencies. (`Review`)

- **MUST NOT** extend the `tests/**` ignores to production code. (`Review`)

- **SHOULD** fix `PT` findings in pytest tests. (`Ruff: PT`)

- **SHOULD** name tests `test_<behavior>_<condition>_<expected>`; describe the behavior, not a sequence number. (`Review`)

- **SHOULD** organize each test as arrange, act, assert, and verify one behavior per test. (`Review`)

- **SHOULD** use the framework's parameterization for repeated cases, such as `pytest.mark.parametrize` or `subTest`. (`Review`)

- **SHOULD** use the framework's native assertion style: plain `assert` in pytest, `assertEqual` and friends in unittest. (`Review`)

- **SHOULD** assert exception types with `pytest.raises` or `unittest.assertRaises` and match the message when it is part of the contract. (`Review`)

- **SHOULD** add a test that reproduces a defect, and confirm it fails before the fix when practical. (`Review`)

Tests and `conftest.py` ignore `S101`, `S105`, `S106`, `S107`, `S108`, and `S311`; the production rules live in [Exceptions](#exceptions), [Date, time, and I/O](#date-time-and-io), and [Security and logging](#security-and-logging). The test ignores are for obvious dummy values only. `PT009` and `PT027` are ignored globally for unittest projects; see [Intentional ignores](ruff-config.md#intentional-ignores).

**Integrated example.**

```python
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, False), (1, True), (-1, True)],
)
def test_is_ready_returns_false_only_for_zero(value: int, expected: bool) -> None:
    assert is_ready(value) is expected


def test_load_config_raises_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "missing.toml")
```

**Exceptions.** A pytest-only project may re-enable `PT009` and `PT027` to enforce plain `assert` and `pytest.raises`. Keep `tests/**` ignores scoped to tests.

## Security and logging

**Applies to.** Diagnostics, log levels, secret handling, dangerous execution, deserialization, subprocesses, and security-sensitive randomness.

**Verified by.** `Ruff: S, T20, TRY400`; the rest is `Review`.

- **MUST** keep secrets, credentials, and personal data out of logs and exception messages. (`Review`)

- **MUST NOT** use `eval` or `exec` on untrusted input. (`Ruff: S102, S307`)

- **MUST NOT** hardcode any credential, password, token, API key, or personal data. (`Ruff: S105, S106, S107`; `Review`)

- **MUST NOT** use `shell=True` with untrusted input. Pass an argument list, for example `subprocess.run(["ls", path], check=True)`. (`Ruff: S602`)

- **MUST NOT** deserialize untrusted data with `pickle` or `marshal`. Use JSON or a typed parser. (`Ruff: S301, S302`)

- **MUST NOT** use `random` for security-sensitive values; use `secrets.token_urlsafe()`. (`Ruff: S311`)

- **SHOULD** use `logger.exception()` or `exc_info=True` when logging an exception with its traceback. (`Ruff: TRY400`)

  ```python
  import logging

  logger = logging.getLogger(__name__)


  def save_user(user: User) -> None:
      """Persists a user and logs a failure with its traceback."""
      try:
          repository.save(user)
      except DatabaseError:
          logger.exception("Failed to save user %s", user.id)
          raise
  ```

- **SHOULD** use the project's logging facility with appropriate levels and lazy formatting. Do not build messages with f-strings or concatenation. (`Review`)

- **SHOULD** read credentials from the environment or a secret manager. (`Review`)

- **SHOULD** prefer structured parsers, `ast.literal_eval`, or dispatch tables over dynamic execution. (`Review`)

- **SHOULD NOT** use `print` or `pprint` for diagnostics. Use the logging facility, for example `logger.info("x=%s", x)`. (`Ruff: T20`)

Security rules marked SHOULD are strong defaults. A deviation needs a specific, documented security review; convenience or legacy code is not a sufficient reason.

**Exceptions.** A CLI may write intentional output with `print` when the project treats stdout as its interface. Add `# noqa: T201` with a reason and keep diagnostics on the logging facility.

## Performance

**Applies to.** Mechanical performance findings, caching, and measurement.

**Verified by.** `Ruff: PERF`; the rest is `Review`.

- **SHOULD** fix `PERF` findings or suppress them with a coded reason. (`Ruff: PERF`)

- **SHOULD** measure before optimizing. Readability and correctness come first. (`Review`)

- **SHOULD** introduce caching only for repeated expensive work with stable inputs and a clear lifetime or invalidation rule. (`Review`)

- **SHOULD NOT** repeat expensive work or redundant conversions in a hot path. (`Review`)

  ```python
  # Good: build the index once
  index = build_index(users)
  for user in users:
      handle(index[user.id])

  # Bad: rebuild the index on every iteration
  for user in users:
      handle(build_index(users)[user.id])
  ```

- **SHOULD NOT** trade clarity for a micro-optimization without measurement. (`Review`)

- **MAY** use `functools.cache` or `lru_cache` for repeated pure work with stable inputs. (`Review`)

Generator and stream choices are owned by [Comprehensions and iteration](#comprehensions-and-iteration).

**Exceptions.** A measured hot path may justify a less readable implementation. Add a comment with the measurement and keep the optimization local.

## Suppressions

**Applies to.** `# noqa`, type-checker ignores, and project-wide exceptions.

**Verified by.** `Ruff: PGH003, PGH004, RUF100`; the reason is `Review`.

- **MUST** include a specific rule code in every `# noqa` and a specific code in every `# type: ignore`. (`Ruff: PGH003, PGH004`)

  ```python
  # Good: specific code and a reason
  value = parse_legacy(payload)  # type: ignore[arg-type]  # upstream stub is incomplete

  # Good: a narrow lint suppression with a reason
  print(report)  # noqa: T201  # intentional CLI stdout output

  # Bad: no code, no reason
  value = parse_legacy(payload)  # type: ignore
  ```

- **MUST** include a reason after the code. (`Review`)

- **MUST NOT** suppress a security rule without a security review. (`Review`)

- **SHOULD** remove unused suppressions. (`Ruff: RUF100`)

- **SHOULD** prefer fixing the type, introducing a `Protocol`, or changing the shared configuration with a documented reason over adding an inline suppression. (`Review`)

- **SHOULD** use the project's type checker suppression syntax with a code and a reason, such as `# ty:ignore[invalid-argument-type]` or `# pyright: ignore[reportArgumentType]`. (`Review`)

**Exceptions.** A generated file may carry file-level suppressions. Keep the generator and the suppressions in sync.
