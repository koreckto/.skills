# Language Rules

Non-mechanical review rules and Ruff blind-spot remainders for typing, data modeling, functions, pattern matching, comprehensions, async code, exceptions, date/time/I/O, paths, testing, security, logging, performance, and suppressions.

## Model the data

### Type annotations

Ruff enforces signature annotations (`ANN`, `ANN401`), `ClassVar` on mutable class defaults (`RUF012`), `TYPE_CHECKING` import moves (`TC001`-`TC003`), modern union/generic syntax (`UP`), and bans `from __future__ import annotations` (`TID251`). Review these gaps manually:

- **MUST** keep imports evaluated at runtime outside `TYPE_CHECKING`, including `get_type_hints`, `get_overloads`, and framework runtime annotation resolution that `TC004` does not detect.
- **MUST** quote forward references and `TYPE_CHECKING`-only types on Python 3.11-3.13, and for definition-time evaluations across all versions; on Python 3.14+, omit quotes where PEP 649 defers evaluation natively.
- **MUST** keep a runtime definition for every `@runtime_checkable` Protocol method; `isinstance()` checks only member presence, so a method defined only inside `TYPE_CHECKING` makes every object pass.
- **SHOULD** create a type alias when the name adds domain meaning that the underlying type does not convey (even when short), or when the type expression is long, nested, repeated, or recursive; **SHOULD NOT** create a short, single-use alias that only restates the underlying type, or use an alias to simulate a distinct type (use `NewType` or a class instead).

  ```python
  # Python 3.12+; on 3.11 declare the alias with TypeAlias.
  # Good: short, but the name carries domain meaning
  type UserId = int

  # Bad: the alias only restates the type
  type String = str
  ```

- **SHOULD** wrap a union annotation that does not fit on one line in parentheses, and format it with one member per line when the union itself spans multiple lines.

  ```python
  from collections.abc import Iterable, Mapping, Sequence


  # Good: parentheses make the union boundary explicit
  def merge(
      sources: (
          Iterable[Mapping[str, object]]
          | Mapping[str, Iterable[object]]
          | Sequence[tuple[str, object]]
          | None
      ),
  ) -> dict[str, object]: ...


  # Bad: the bare continuation hides the union boundary
  def merge(
      sources: Iterable[Mapping[str, object]]
      | Mapping[str, Iterable[object]]
      | Sequence[tuple[str, object]]
      | None,
  ) -> dict[str, object]: ...
  ```

- **SHOULD** annotate class attributes and local empty-container initializations (`items: list[str] = []`), use `Final[T]` for constants that must not be rebound, and annotate a method returning its own instance (`__enter__`, fluent setters) with `-> Self`.
- **SHOULD** use `typing_extensions` only when the minimum Python version lacks the feature, and move typing-only `@overload` signatures behind `TYPE_CHECKING` except when read with `typing.get_overloads()`.
- **SHOULD NOT** use `Any` in variables or class attributes (prefer `object` or a `Protocol`), and **MAY** use `Any` at a dynamic boundary after validating and narrowing the value.

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

**Integrated example.**

```python
# Python 3.11-3.13 (on 3.14+, PEP 649 defers evaluation natively; omit quotes)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from myapp.models.user import User


def first_user(users: "Iterable[User]") -> "User | None":
    """Returns the first user, or None when the iterable is empty."""
    return next(iter(users), None)
```

### Data modeling

- **MUST** validate external input once at the boundary, then pass typed data through the rest of the code.
- **SHOULD** use a dataclass, `TypedDict`, or `NamedTuple` for structured internal data, not a bare `dict` or `tuple`.
- **SHOULD** model immutable value objects with `@dataclass(frozen=True, slots=True)` using `tuple` and `frozenset` fields (omit `slots=True` only when `__dict__`, weak references, or a specific pickling or ORM contract requires it).
- **SHOULD** use the built-in `frozendict` for mapping fields of value objects on minimum Python 3.15+ (or a maintained immutable mapping on older versions), noting that `MappingProxyType` is an unhashable read-only view rather than an immutable copy.
- **SHOULD** validate invariants in `__post_init__` or a validator while keeping constructors free of I/O and expensive recomputation, use `Enum` for closed sets of named values, and replace static-method-only classes with module-level functions unless a framework requires the class.
- **SHOULD** use built-in `sentinel` (3.15+) or `typing_extensions.sentinel` (below 3.15) for sentinel values instead of `object()` or custom classes, bind it to a matching name (`MISSING = sentinel("MISSING")`), and compare with `is`.

  ```python
  # Python 3.15+; on < 3.15, import sentinel from typing_extensions.
  MISSING = sentinel("MISSING")


  def find_value(key: str, default: str | MISSING = MISSING) -> str | MISSING:
      """Looks up a key, distinguishing missing values from None."""
      ...
  ```

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

## Write the logic

### Functions and parameters

- **SHOULD** keep each function at one level of abstraction (extract helpers instead of nesting deeply), return results instead of mutating arguments, and keep I/O at boundaries.
- **SHOULD** make optional parameters keyword-only when several are optional, avoid positional booleans at call sites where clarity suffers (`FBT003` is not enabled), and introduce a `dataclass`, `TypedDict`, or `NamedTuple` parameter object when parameters form a cohesive group or no longer fit on one line.
- **SHOULD** use `nonlocal` only for closure-local state.
- **SHOULD NOT** hide a public API signature behind `**kwargs` (decorators and narrow forwarding wrappers exempt).

### Pattern matching

- **MUST NOT** use a bare name as a `case` pattern to compare against a constant; a bare name is a capture pattern and matches every value, so use a literal, a dotted name (`Color.RED`), an enum member, or a guard.

  ```python
  # Bad: ENTER is a capture pattern, so this case matches every key
  match event:
      case KeyPress(key=ENTER):
          submit()
  ```

- **SHOULD** use `match` and `case` patterns instead of an `if`/`elif` chain when a branch depends on the shape of a value (type, attributes, container elements, or related values at once).
- **SHOULD** put a condition on captured values in a guard (`case Text(value) if len(value) > 80:`) instead of nesting it in the case body.
- **SHOULD NOT** use `match` for a single condition, a boolean expression, a range check, or a chain comparing one variable with literals (`if`/`elif` is clearer).

**Integrated example.**

```python
# Good: match dispatches on shape, matches a dotted constant, and uses a guard
match event:
    case Click(x=x, y=y):
        handle_click(x, y)
    case KeyPress(key=Key.ENTER):
        submit()
    case KeyPress(key=key) if len(key) == 1:
        handle_key(key)
    case _:
        raise TypeError(type(event))

# Bad: isinstance chain handles ENTER as an ordinary key and repeats extraction
if isinstance(event, Click):
    handle_click(event.x, event.y)
elif isinstance(event, KeyPress):
    handle_key(event.key)
else:
    raise TypeError(type(event))
```

### Comprehensions and iteration

- **SHOULD** keep a comprehension to one `for` and at most one `if`.

  ```python
  # Bad: two filters exceed the one-if budget
  admins = [u.name for u in users if u.is_active if u.is_admin]
  ```

- **SHOULD** allow a second `for` only to flatten a two-dimensional structure.

  ```python
  # Good: the second for flattens a two-dimensional structure
  flat_matrix = [cell for row in matrix for cell in row]
  ```

- **SHOULD** use `itertools.product` for a parallel Cartesian product (remembering it materializes inputs, so keep a nested generator for large or infinite streams and state why), generator expressions for large streams when a list is not required, and an explicit loop for dependent nested loops or multi-step logic.

  ```python
  import itertools

  # Good: parallel Cartesian product
  coords = [f(x, y) for x, y in itertools.product(xs, ys)]

  # Bad: the inner loop depends on the outer loop; use an explicit loop
  names = [u.name for g in groups if g.is_active for u in g.users]
  ```

## Handle runtime

### Async and concurrency

- **MUST** keep custom blocking I/O and CPU-bound work out of `async def` by offloading with `asyncio.to_thread` or an executor (`ASYNC` flags only known stdlib, Trio, and AnyIO calls).

  ```python
  import asyncio


  async def load(url: str) -> bytes:
      # Bad: blocks the event loop
      return fetch_sync(url)


  async def load_async(url: str) -> bytes:
      # Good: offload blocking work
      return await asyncio.to_thread(fetch_sync, url)
  ```

- **MUST** manage resources with `async with` or a `finally` block.
- **MUST NOT** swallow `asyncio.CancelledError`; let cancellation propagate, and re-raise it after any cleanup.
- **SHOULD** use `asyncio.TaskGroup` for structured concurrency, bound waits with `asyncio.timeout`, and keep a consistent async or sync boundary without mixing blocking and async clients in one path.

  ```python
  import asyncio


  async def fetch_all(urls: list[str], timeout_seconds: float = 10.0) -> list[str]:
      """Fetches every URL concurrently and returns the responses in order."""
      async with asyncio.timeout(timeout_seconds), asyncio.TaskGroup() as group:
          tasks = [group.create_task(fetch(url)) for url in urls]
      return [task.result() for task in tasks]
  ```

### Exceptions

- **MUST** log the traceback, re-raise, or return a structured failure at a boundary when catching `Exception` (returning a failure needs `# noqa: BLE001` with a reason, whereas a logged handler must not add it); never swallow exceptions silently (for example catching and returning `None` without handling or explicit `contextlib.suppress`).
- **SHOULD** catch specific exceptions (reserving broad catches for process boundaries), keep `try` blocks minimal around only the raising call (moving validations and early raises outside), raise project-specific exception types across API boundaries rather than leaking raw `KeyError` or `AttributeError`, and keep exception messages at the `raise` site (`TRY003` is ignored).

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

### Date, time, and I/O

- **MUST** pass `encoding=` explicitly for text I/O when the minimum Python version is below 3.15.

  ```python
  from pathlib import Path


  def read_events(path: str | Path) -> list[str]:
      """Reads non-empty event lines from a UTF-8 text file."""
      text = Path(path).read_text(encoding="utf-8")
      return [line for line in text.splitlines() if line]
  ```

- **SHOULD** parse and store datetimes in UTC and convert at the edges (converting immediately and documenting if a library requires naive datetimes), use `Path.open()` in a context manager for streams and `Path.read_text()`/`Path.write_text()` for simple text files, distinguish text and binary I/O, and pass `newline=""` for CSV files.

### Paths

- **SHOULD** use one segment per `/` operand when composing a path from controlled segments (`base / "config" / "defaults.toml"`), pass a sequence of segments to `joinpath(*segments)` instead of a loop or `reduce`, and keep a path received as one external value whole (`Path(value)` or single `/` operand without splitting and rejoining).
- **SHOULD** call `expanduser()` once at the input boundary for a human-entered path that may start with `~`, before `resolve()` (which does not expand `~`); use `Path.home()` for the current user's home.
- **SHOULD** use `resolve()` when a path must be canonical for comparison, deduplication, or a cache key, or when a symlink target is required (pass `strict=True` when the path must exist).
- **SHOULD NOT** compose a path with string concatenation or an f-string that embeds a separator, or use `absolute()` to obtain a canonical path (it does not expand `~`, collapse `..`, or resolve symlinks; use it only when preserving the path as written is required).

## Verify and secure

### Testing

- **MUST** keep unit tests isolated from network access, real clocks, unseeded randomness, and execution order by injecting or freezing external dependencies.
- **MUST NOT** extend `tests/**` or `conftest.py` Ruff ignores to production code; use the `S105`-`S107` test ignores for obvious dummy values only.
- **SHOULD** name tests `test_<behavior>_<condition>_<expected>`, organize each test as arrange, act, assert verifying one behavior, use framework parameterization (`pytest.mark.parametrize` or `subTest`), use native assertions, assert exception types with `pytest.raises` or `TestCase.assertRaises` (matching messages when part of the contract), and add a failing regression test before fixing a defect when practical.

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

### Security and logging

- **MUST** keep secrets, credentials, tokens, API keys, and personal data out of code, tests, logs, and exception messages (`S105`-`S107` only match password-named identifiers).
- **MUST** keep an externally supplied path under its base directory before using it to access the filesystem; an absolute value replaces the base and `..` escapes it, so resolve both the base and the candidate and require `is_relative_to()`.

  ```python
  from pathlib import Path

  base = Path("/srv/data").resolve()
  user_value = "reports/2026.csv"
  candidate = (base / user_value).resolve()
  if not candidate.is_relative_to(base):
      raise ValueError("path escapes the base directory")
  ```

- **SHOULD** use the project's logging facility with appropriate levels and lazy formatting (never build log messages with f-strings or concatenation), read credentials from the environment or a secret manager, and prefer structured parsers, `ast.literal_eval`, or dispatch tables over dynamic execution.

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

### Performance

- **SHOULD** measure before optimizing (do not trade clarity for unmeasured micro-optimizations), introduce caching (`functools.cache` or `lru_cache`) only for repeated pure work with stable inputs and a clear lifetime or invalidation rule, and avoid repeating expensive work or redundant conversions in a hot path.

  ```python
  # Good: build the index once
  index = build_index(users)
  for user in users:
      handle(index[user.id])

  # Bad: rebuild the index on every iteration
  for user in users:
      handle(build_index(users)[user.id])
  ```

### Suppressions

- **MUST** include a reason after every coded `# noqa` and type-checker ignore (`PGH003`/`PGH004` verify only the code).
- **MUST NOT** suppress a security rule (`S*`) without a security review, or treat an inline suppression as a routine exception to a `MUST` rule.
- **SHOULD** prefer fixing the type, introducing a `Protocol`, or changing shared configuration with a documented reason over adding an inline suppression, and use the project's type-checker syntax with a code and a reason (`# ty:ignore[...]`, `# pyright: ignore[...]`).

  ```python
  # Good: specific code and a reason
  value = parse_legacy(payload)  # type: ignore[arg-type]  # upstream stub is incomplete

  # Good: a narrow lint suppression with a reason
  print(report)  # noqa: T201  # intentional CLI stdout output

  # Bad: no code, no reason
  value = parse_legacy(payload)  # type: ignore
  ```
