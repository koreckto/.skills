# Language Rules

Typing, data modeling, functions, pattern matching, comprehensions, async code, exceptions, date/time and I/O, path handling, testing, security, logging, performance, and suppressions.

## Model the data

### Type annotations

- **MUST** annotate mutable class-level state with `ClassVar[T]`, for example `items: ClassVar[list[str]] = []`. (`Ruff: RUF012`)

- **MUST** keep imports used at runtime outside `TYPE_CHECKING`, including base classes, `isinstance` checks, decorators, and framework annotations resolved at runtime. (`Ruff: TC004`; `Review`)

- **MUST** quote forward references and types imported under `TYPE_CHECKING` on Python 3.11–3.13, and for definition-time evaluations across all versions. (`Review`)

- **MUST** keep a runtime definition for every `@runtime_checkable` Protocol method; `isinstance()` checks only member presence, so a method defined only inside `TYPE_CHECKING` makes every object pass. (`Review`)

- **MUST NOT** use `from __future__ import annotations`. Quote forward references instead. (`Ruff: TID251`)

- **SHOULD** annotate every function parameter and return value. (`Ruff: ANN`)

- **SHOULD** use built-in generics and PEP 604 unions, and import abstract collections from `collections.abc`. (`Ruff: UP006, UP007, UP035, UP045`)

- **SHOULD** move typing-only imports behind `if TYPE_CHECKING:`. (`Ruff: TC001, TC002, TC003`)

- **SHOULD** use PEP 695 generics and `type` aliases when the minimum Python version is 3.12 or newer; see the [feature matrix](version-compatibility.md#feature-matrix). (`Ruff: UP040, UP046, UP047`; `Since: 3.12`)

- **SHOULD** omit quotes around annotations on Python 3.14+ where PEP 649 defers evaluation natively, except for expressions evaluated at definition time. (`Ruff: UP037`; `Review`; `Since: 3.14`)

- **SHOULD** create a type alias when the name adds domain meaning that the underlying type does not convey, even when the underlying type is short, or when the type expression is long, nested, repeated, or recursive. (`Review`)

  ```python
  # Python 3.12+; on 3.11 declare the alias with TypeAlias.
  # Good: short, but the name carries domain meaning
  type UserId = int

  # Bad: the alias only restates the type
  type String = str
  ```

- **SHOULD** wrap a union annotation that does not fit on one line in parentheses, and format it with one member per line when the union itself spans multiple lines. (`Format: ruff format`; `Review`)

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

- **SHOULD** annotate class attributes and local empty-container initializations (`items: list[str] = []`). (`Review`)

- **SHOULD** use `Final[T]` for constants that must not be rebound, for example `MAX_RETRIES: Final = 3`. (`Review`)

- **SHOULD** annotate a method returning its own instance with `-> Self`, including fluent setters and `__enter__`, for example `def __enter__(self) -> Self`. (`Review`)

- **SHOULD** use `typing_extensions` only when the minimum Python version lacks the feature. Do not use it for features already available in the minimum version. (`Review`)

- **SHOULD** move typing-only overloads behind `TYPE_CHECKING`, except when code reads them with `typing.get_overloads()`. (`Review`)

- **SHOULD NOT** create a short, single-use type alias that only restates the underlying type without adding domain meaning, or use an alias to simulate a distinct type; use `NewType` or a class when the distinction must be enforced. (`Review`)

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

    from myapp.models.user import User


def first_user(users: "Iterable[User]") -> "User | None":
    """Returns the first user, or None when the iterable is empty."""
    return next(iter(users), None)
```

**Exceptions.** A framework that resolves annotations at runtime may need a runtime import. Keep the import outside `TYPE_CHECKING` and document the framework behavior. On 3.11, use `TypeVar`, `Generic`, and `TypeAlias` instead of PEP 695 syntax.

### Data modeling

- **MUST** validate external input once at the boundary, then pass typed data through the rest of the code. (`Review`)

- **SHOULD** use a dataclass, `TypedDict`, or `NamedTuple` for structured internal data, not a bare `dict` or `tuple`. (`Review`)

- **SHOULD** model immutable value objects with `@dataclass(frozen=True, slots=True)`. Use `tuple` and `frozenset` for sequence and set fields. Omit `slots=True` when the object needs `__dict__`, weak references, or a specific pickling or ORM contract. (`Review`)

- **SHOULD** use the built-in `frozendict` when the minimum Python version is 3.15 or newer, or a maintained immutable mapping implementation on earlier versions, for a mapping field of a value object; see the [feature matrix](version-compatibility.md#feature-matrix). `MappingProxyType` is a read-only view, not an equivalent: it is unhashable and reflects mutations of the wrapped mapping. (`Review`; `Since: 3.15`)

- **SHOULD** validate invariants in `__post_init__` or a validator. Keep constructors free of I/O and expensive recomputation. (`Review`)

- **SHOULD** use `Enum` for a closed set of named values. (`Review`)

- **SHOULD** replace a class that only holds static methods with module-level functions, unless a framework requires the class. (`Review`)

Datetime construction is owned by [Date, time, and I/O](#date-time-and-io); mutable class state is owned by [Type annotations](#type-annotations); field documentation for public data models is owned by [Style: docstrings](style-rules.md#docstrings).

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

## Write the logic

### Functions and parameters

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

### Pattern matching

`match` has been available since Python 3.10, so it is available at every version this skill supports (3.11+).

- **MUST NOT** use a bare name as a `case` pattern to compare against a constant. A bare name is a capture pattern and matches every value; use a literal, a dotted name such as `Color.RED`, an enum member, or a guard. (`Review`)

  ```python
  # Bad: ENTER is a capture pattern, so this case matches every key
  match event:
      case KeyPress(key=ENTER):
          submit()
  ```

- **SHOULD** use `match` and `case` patterns instead of an `if`/`elif` chain when a branch depends on the shape of a value: its type, attributes, container elements, or several related values at once. (`Review`)

- **SHOULD** put a condition on captured values in a guard, for example `case Text(value) if len(value) > 80:`, instead of nesting it in the case body. (`Review`)

- **SHOULD NOT** use `match` for a single condition, a boolean expression, a range check, or a chain that compares one variable with literals; `if`/`elif` is clearer there. (`Review`)

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

- **MUST** pass `strict=` to `zip()` when it is called with two or more iterables or a starred argument. (`Ruff: B905`)

- **SHOULD** fix mechanical comprehension and iteration simplifications reported by `C4` and `FURB`. (`Ruff: C4, FURB`)

- **SHOULD** keep a comprehension to one `for` and at most one `if`. (`Review`)

  ```python
  # Bad: two filters exceed the one-if budget
  admins = [u.name for u in users if u.is_active if u.is_admin]
  ```

- **SHOULD** allow a second `for` only to flatten a two-dimensional structure. (`Review`)

  ```python
  # Good: the second for flattens a two-dimensional structure
  flat_matrix = [cell for row in matrix for cell in row]
  ```

- **SHOULD** use `itertools.product` for a parallel Cartesian product, and an explicit loop for a dependent nested loop or multi-step logic. (`Review`)

  ```python
  import itertools

  # Good: parallel Cartesian product
  coords = [f(x, y) for x, y in itertools.product(xs, ys)]

  # Bad: the inner loop depends on the outer loop; use an explicit loop
  names = [u.name for g in groups if g.is_active for u in g.users]
  ```

- **SHOULD** remember that `itertools.product` materializes its inputs. Keep a nested generator for large or infinite streams when streaming matters, and state why. (`Review`)

- **SHOULD** use a generator expression for a large stream when a list is not required. (`Review`)

- **MAY** use a comprehension for a simple transformation or filter. (`Review`)

**Exceptions.** A comprehension may be less readable than a loop when it has multiple filters or multi-step logic. Use the loop.

## Handle runtime

### Async and concurrency

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

### Exceptions

- **MUST** chain a translated exception with `raise NewError(...) from err`. (`Ruff: B904`)

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

### Date, time, and I/O

- **MUST** construct datetimes with an explicit timezone. (`Ruff: DTZ`)

  ```python
  from datetime import UTC, datetime


  def event_timestamp() -> datetime:
      """Returns the current UTC timestamp."""
      return datetime.now(UTC)
  ```

- **MUST** pass `encoding=` explicitly for text I/O when the minimum Python version is below 3.15. (`Review`)

  ```python
  from pathlib import Path


  def read_events(path: str | Path) -> list[str]:
      """Reads non-empty event lines from a UTF-8 text file."""
      text = Path(path).read_text(encoding="utf-8")
      return [line for line in text.splitlines() if line]
  ```

- **MUST NOT** use `datetime.utcnow()` or a naive `datetime.now()`. (`Ruff: DTZ`)

- **MUST NOT** hardcode a temporary file path. Use `tempfile`. (`Ruff: S108`)

- **SHOULD** parse and store datetimes in UTC, and convert at the edges. (`Review`)

- **SHOULD** use `Path.open()` in a context manager for streams, and `Path.read_text()` or `Path.write_text()` for simple text files. (`Ruff: PTH123`; `Review`)

- **SHOULD** distinguish text and binary I/O, and pass `newline=` when working with CSV files. (`Review`)

Path composition and normalization are owned by [Paths](#paths).

**Exceptions.** A library may require naive datetimes at its boundary. Convert immediately and document the requirement.

### Paths

- **SHOULD** use `pathlib.Path` instead of `os.path` for path operations. (`Ruff: PTH`)

- **SHOULD** use one segment per `/` operand when composing a path from controlled segments: `base / "config" / "defaults.toml"`. (`Review`)

- **SHOULD** pass a sequence of segments to `joinpath(*segments)` when the segments are already a sequence; do not build the path with a loop or `reduce`. (`Review`)

- **SHOULD** keep a path received as one external value whole: pass it to `Path(value)` or use it as a single `/` operand; do not split it into segments only to rejoin them. (`Review`)

- **SHOULD** call `expanduser()` once at the input boundary for a human-entered path that may start with `~`, before `resolve()`, which does not expand `~`; use `Path.home()` for the current user's home. (`Ruff: PTH111`; `Review`)

- **SHOULD** use `resolve()` when a path must be canonical for comparison, deduplication, or a cache key, or when a symlink target is required; pass `strict=True` when the path must exist. (`Ruff: PTH100`; `Review`)

- **SHOULD NOT** compose a path with `os.path.join`, string concatenation, or an f-string that embeds a separator. (`Ruff: PTH118`; `Review`)

- **SHOULD NOT** use `absolute()` to obtain a canonical path; it does not expand `~`, collapse `..`, or resolve symlinks. Use it only when preserving the path as written, including symlinks and `..`, is required. (`Review`)

Path containment is owned by [Security and logging](#security-and-logging).

## Verify and secure

### Testing

- **MUST** keep unit tests isolated: no network, real clock, unseeded randomness, or execution order. Inject or freeze external dependencies. (`Review`)

- **MUST NOT** extend the `tests/**` ignores to production code. (`Review`)

- **SHOULD** fix `PT` findings in pytest tests. (`Ruff: PT`)

- **SHOULD** name tests `test_<behavior>_<condition>_<expected>`; describe the behavior, not a sequence number. (`Review`)

- **SHOULD** organize each test as arrange, act, assert, and verify one behavior per test. (`Review`)

- **SHOULD** use the framework's parameterization for repeated cases, such as `pytest.mark.parametrize` or `subTest`. (`Review`)

  ```python
  import pytest


  @pytest.mark.parametrize(
      ("value", "expected"),
      [(0, False), (1, True), (-1, True)],
  )
  def test_is_ready_returns_false_only_for_zero(value: int, expected: bool) -> None:
      assert is_ready(value) is expected
  ```

- **SHOULD** use the framework's native assertion style: plain `assert` in pytest, `assertEqual` and friends in unittest. (`Review`)

- **SHOULD** assert exception types with `pytest.raises` or `TestCase.assertRaises` and match the message when it is part of the contract. (`Review`)

  ```python
  from pathlib import Path

  import pytest


  def test_load_config_raises_for_missing_file(tmp_path: Path) -> None:
      with pytest.raises(FileNotFoundError):
          load_config(tmp_path / "missing.toml")
  ```

- **SHOULD** add a test that reproduces a defect, and confirm it fails before the fix when practical. (`Review`)

Tests and `conftest.py` ignore `S101`, `S105`, `S106`, `S107`, `S108`, and `S311`; the production rules live in [Exceptions](#exceptions), [Date, time, and I/O](#date-time-and-io), and [Security and logging](#security-and-logging). The test ignores are for obvious dummy values only. `PT009` and `PT027` are ignored globally for unittest projects; see [Intentional ignores](ruff-config.md#intentional-ignores).

**Exceptions.** A pytest-only project may re-enable `PT009` and `PT027` to enforce plain `assert` and `pytest.raises`. Keep `tests/**` ignores scoped to tests.

### Security and logging

- **MUST** keep secrets, credentials, and personal data out of logs and exception messages. (`Review`)

- **MUST** keep an externally supplied path under its base directory before using it to access the filesystem; an absolute value replaces the base and `..` escapes it. Resolve both the base and the candidate and require `is_relative_to()`. (`Review`)

  ```python
  from pathlib import Path

  base = Path("/srv/data").resolve()
  user_value = "reports/2026.csv"
  candidate = (base / user_value).resolve()
  if not candidate.is_relative_to(base):
      raise ValueError("path escapes the base directory")
  ```

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

### Performance

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

### Suppressions

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
