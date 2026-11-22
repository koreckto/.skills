# Style Rules

Terms, non-mechanical layout, package-boundary imports and exports, naming, formatting remainders, docstrings, comments, and code examples. Import sorting, unused/wildcard imports, builtin shadowing, `ruff format`, and commented-out code are handled by Ruff.

## Terms: internal and public objects

An *internal object* is a named Python object whose name begins with a leading underscore and is not a dunder name, relative to the scope that contains it (a package, module, class, or function). A *public object* is any object that is not internal relative to the referencing scope. A dunder name begins and ends with two underscores, such as `__init__`, `__all__`, and `__name__`; a dunder name is itself a public object, though an internal package in the path can still make the reference internal.

The classification is relative to the referencing scope. The package root is the project's public package root, such as `myapp`; a module path is relative to it. For an object reference from module A to an object with qualified path B, let C be the nearest common package of A and B, or the top-level namespace when they share none. The object is internal relative to A when any name in B's path below C is an internal object relative to its parent; otherwise it is public relative to A. Use the path where the object is defined; a re-export does not change it. The same object can be internal from one scope and public from another.

| Referencing module | Referenced object | Classification |
| :--- | :--- | :--- |
| `myapp.api.routes` | `myapp._internal.tokens.Token` | internal: nearest common package `myapp`; `_internal` is internal relative to `myapp` |
| `myapp._internal.sessions` | `myapp._internal.tokens.Token` | public: nearest common package `myapp._internal`; `tokens` and `Token` are public relative to it |
| `myapp.api.routes` | `myapp.models.user.User` | public: nearest common package `myapp`; `models`, `user`, and `User` are public |

These terms classify names and references; [Naming](#naming) decides when an object should be internal, and [Public API and exports](#public-api-and-exports) decides which public objects external consumers may import directly.

## Organize the module

### Module and package layout

- **MUST** keep import time free of I/O, network calls, global state mutation, and business logic. Isolate framework-required import registration in a dedicated module and document why.
- **SHOULD** keep module-level code to imports, definitions, constants, type aliases, and the `if __name__ == "__main__":` guard.
- **SHOULD** order top-level members as: module docstring, imports, public or module-wide constants, type aliases, classes, functions, and the entry guard (dependency order wins when a name is evaluated at import time), keeping public members before internal `_` helpers while placing narrowly scoped internal constants and helpers near their callers and keeping dunder methods in their conventional placement.
- **SHOULD** keep implementation details—such as regexes, lookup mappings, fixed sets, and local thresholds used by only one function, method, or class—in that narrowest local or class scope rather than hoisting them to module level (Python compiles literal `in {...}` and `in (...)` tests as constant `frozenset`/`tuple` bytecode and caches top-level `re` patterns).
- **SHOULD** promote a value to a module-level constant only when it is part of the module's public contract, carries independent domain or configuration meaning shared across multiple functions or classes, or avoids non-trivial repeated construction in a measured hot path.
- **SHOULD** prefix a module-only constant with `_` (`_UPPER_SNAKE_CASE`), and place an internal constant used by only one or two adjacent definitions immediately above its callers rather than hoisting it to the top of the module.

  ```python
  import re


  # Good: single-caller set stays local
  def is_supported_scheme(scheme: str) -> bool:
      """Returns whether the URI scheme is supported."""
      return scheme in {"http", "https"}


  # Good: shared internal pattern sits right above its callers
  _SLUG_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


  def is_valid_slug(value: str) -> bool:
      """Returns whether the value is a normalized slug."""
      return _SLUG_PATTERN.fullmatch(value) is not None


  def extract_slugs(text: str) -> list[str]:
      """Extracts all slug tokens from the text."""
      return _SLUG_PATTERN.findall(text)
  ```

  ```python
  import re
  
  # Bad: single-caller or narrowly scoped details hoisted and exposed as public module constants
  SUPPORTED_SCHEMES = {"http", "https"}
  SLUG_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


  def is_supported_scheme(scheme: str) -> bool:
      """Returns whether the URI scheme is supported."""
      return scheme in SUPPORTED_SCHEMES


  def is_valid_slug(value: str) -> bool:
      """Returns whether the value is a normalized slug."""
      return SLUG_PATTERN.fullmatch(value) is not None


  def extract_slugs(text: str) -> list[str]:
      """Extracts all slug tokens from the text."""
      return SLUG_PATTERN.findall(text)
  ```

- **MAY** use a scoped utility module (`utils.py`, `helpers.py`, `_utils.py`, `_helpers.py`, or `common.py`) within a package or subpackage to group small, cohesive shared helpers that do not warrant dedicated modules; do not mechanically reject those module names or fragment a package into single-function files just to avoid them.
- **SHOULD NOT** turn a utility module into an unbounded, cross-domain dumping ground that mixes unrelated responsibilities or pulls in heavy cross-layer dependencies; extract a domain-named module only when a cohesive responsibility grows large enough to stand on its own.

**Integrated example.**

```python
"""Loads configuration for the application."""

# Good: definitions only at import time; entry guard at the bottom
from pathlib import Path


def load_config(path: Path) -> dict[str, str]:
    """Loads a configuration file."""
    ...


if __name__ == "__main__":
    load_config(Path("config.toml"))
```

### Imports

- **SHOULD** prefer absolute imports for clarity and refactoring safety; relative imports within a package are acceptable when they match established project practice and stay consistent across the project.
- **SHOULD NOT** create a module-level class that shadows an imported class it subclasses or wraps. Use module-qualified access or an internal `_Base` alias.

  ```python
  # Good: keep the imported class explicit
  from pathlib import Path as _BasePath


  class Path(_BasePath): ...


  # Bad: the class shadows the imported name
  from pathlib import Path


  class Path(Path): ...
  ```

### Public API and exports

For these rules, the target package is the nearest first-party package boundary that owns the defining module: the containing package for a module, or the package itself for a definition in an `__init__.py`. A module is inside a target package when that package is its containing package or an ancestor package; a subpackage is a separate target package for its own members, so a parent or sibling package is outside that subpackage. A re-export does not change the defining module. When the rule requires the target package's `__init__.py` re-export, the name must be re-exported there; importing a submodule through the package namespace does not satisfy the rule. The rules apply to runtime and `TYPE_CHECKING` imports in production code; unit tests may import the defining module or internal object under test directly. The package `__init__.py` may import defining modules to build its re-exports.

- **MUST** import a first-party object from outside its target package through the target package's `__init__.py` re-export, unless the object is public relative to the importing module.
- **MUST NOT** import an object through an `__init__.py` re-export when the importing module is inside the target package. Import the defining module directly.
- **SHOULD** declare `__all__` only in a re-exporting package `__init__.py` (re-exporting selected objects with explicit imports), or **MAY** declare it in a module that intentionally exposes a stable public surface; ordinary modules omit it.

**Integrated example.**

```python
# The examples assume myapp/_internal/__init__.py re-exports Token from myapp._internal.tokens.

# myapp/api/routes.py -> myapp._internal.tokens.Token
from myapp._internal import Token  # Good: target-package facade
from myapp._internal.tokens import Token  # Bad: internal reference from outside the target package

# myapp/_internal/sessions.py -> myapp._internal.tokens.Token
from myapp._internal.tokens import Token  # Good: defining module from inside the package
from myapp._internal import Token  # Bad: package re-export from inside

# myapp/api/routes.py -> myapp.models.user.User
from myapp.models.user import User  # Good: public object relative to myapp.api.routes

# scripts/seed.py, outside myapp
from myapp._internal import Token  # Good: target-package facade
```

## Name and format

### Naming

Ruff checks only `N818` (`Error` suffix on `Exception` subclasses) and builtin shadowing (`A`); review these naming rules manually:

- **SHOULD** use one name for one concept and one verb for one action across the project, especially in public APIs.
- **SHOULD** use PEP 8 casing: `snake_case` for modules, functions, and variables; `PascalCase` for classes; `UPPER_SNAKE_CASE` for constants and enum members.
- **SHOULD** name booleans with a positive predicate (`is_ready`, `has_access`, `enabled`).

  ```python
  # Good: the flag states the positive condition
  def fetch_user(user_id: str, *, include_inactive: bool = False) -> User: ...
  ```

- **SHOULD** use plural nouns for collections (`users`) and `<value>_by_<key>` for mappings (`users_by_id`) without `_list` or `_dict` suffixes.
- **SHOULD** include units in numeric names (`timeout_seconds`, `size_bytes`).

  ```python
  # Good: the name carries the unit
  timeout_seconds = 30

  # Bad: the unit is implicit
  timeout = 30
  ```

- **SHOULD** use verb phrases for functions (`load_config`), `from_*` for alternate constructors, `create_*`/`build_*`/`make_*` for factories, nouns or adjectives for properties (`size`, `is_empty`), `to_*`/`as_*` for converters, `iter_*` or `iterate_*` consistently (preferring `stream_*` when it fits), and omit `async_` unless providing paired sync/async functions (`sync_fetch`/`async_fetch`).
- **SHOULD** use singular nouns for classes, adjective names for protocols, `Async` for paired async classes, `*Mixin` for mixins, `*Warning` for warnings, uppercase for single abbreviations (`HTTPClient`), word casing for adjacent abbreviations (`HttpUrl`), and standard type-variable names (`T`, `U`, `V`, `KT`, `VT`, `P`, `Ts`).
- **SHOULD** use domain names in loops and unpacking (reserving `key`/`value`/`item`/`index` for generic containers and single letters for obvious micro-scopes), and use `e`, `err`, or `exc` consistently for exception variables.

  ```python
  # Good: domain names make the key and value clear
  for user_id, profile in users_by_id.items():
      send_notification(user_id, profile.email)

  # Bad: single-letter names obscure what k and v represent
  for k, v in users_by_id.items():
      send_notification(k, v.email)
  ```

- **SHOULD** use full words in public names (lowercase acronyms in `snake_case`, such as `http_client`).
- **SHOULD** make an object internal by prefixing its name with a single leading underscore when it is used only within its defining boundary: a package outside the project's public API, a module in a public package used only within that package, a function, class, or module-level constant/global used only in one module (`_UPPER_SNAKE_CASE` for internal constants), or a method or attribute used only in one class (submodules shared inside an internal package do not need an extra leading underscore).
- **SHOULD** treat names required by public exports, public type signatures, protocols, or name-based framework dispatch as external contracts rather than internal objects.
- **SHOULD** treat callbacks registered or passed only by object reference as internal to their defining boundary when their Python names are not external contracts.

  ```python
  # Good: the registry key is public, but the callback name is internal.
  def _sync_user() -> None: ...


  callbacks_by_command = {"sync-user": _sync_user}
  ```

- **SHOULD NOT** use `_flag` or negative boolean names.

  ```python
  # Good: the name states the positive condition
  cache_enabled: bool = True

  # Bad: the negation and the `_flag` suffix hide the condition
  no_cache: bool = False
  cache_flag: bool = True
  ```

- **SHOULD NOT** use `__name` for privacy (double underscores trigger name mangling); **MAY** use `_` for an intentionally unused value.

### Formatting and line structure

- **SHOULD** use a single blank line between major phases in a long function body (roughly 20 lines or more), keeping short functions compact and treating a single call or data structure spanning multiple lines as one phase.

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

- **SHOULD** use f-strings for interpolation outside logging calls (logging calls use lazy formatting instead).
- **SHOULD NOT** run Black, isort, or another formatter alongside `ruff format`, and **MAY** use implicit string concatenation for long messages with aligned fragments.

## Document and exemplify

### Docstrings

For these rules, a data model (`@dataclass`, `TypedDict`, `NamedTuple`, or a framework model class with declarative fields) is public when it is part of the package's public API under [Public API and exports](#public-api-and-exports). A field is public when it is a public object relative to the model class under [Terms](#terms-internal-and-public-objects) and is not a `ClassVar`, `model_config`, or another framework configuration attribute.

- **SHOULD** include every applicable `Args`, `Returns`, `Yields`, and `Raises` section in public function and method docstrings, ordered after a one-line summary and a blank line as: `Args`, `Returns`, `Yields`, `Raises`, `Attributes`.
- **SHOULD** list parameters in signature order as `name (type, optional):` with defaults in the description, use `name (type):` for `Attributes`, use `Yields` for generators, omit `Returns` when returning `None`, and declare `Returns`/`Yields` entries as `type:` and `Raises` entries as `ExceptionType:`.
- **SHOULD** place each argument, return, yield, exception, and attribute description on a separate line below its declaration, indented one level (continuation lines use the same indentation).
- **SHOULD** document every public field of a public data model (a class summary alone does not document its fields) using a per-field docstring or the framework's native field description (such as Pydantic), keeping one style per project.
- **SHOULD** use imperative mood or declarative sentences consistently across the project, end sentences with punctuation in the document's language (`D415` is ignored), keep section headers in English, add an `Examples:` section when usage is not obvious, and **MAY** write docstrings in the project's language.

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
    ...
```

**Exceptions.** Functions and methods that are internal objects may use a summary-only docstring. A function or method defined in a module that is internal relative to the package root may also use a summary-only docstring when the function, method, or owning class is not re-exported as part of a public package's API.

### Comments

- **SHOULD** use comments only for non-obvious constraints, trade-offs, upstream defects, and reference links, and **MAY** write comments in the project's language.
- **SHOULD NOT** narrate what the code does, restate annotations, or leave ownerless `TODO` or `FIXME` markers (include an issue link or an owner).
- **MAY** use a separator comment with a short noun phrase sparingly to mark distinct logical sections in a long module, keeping it within the line limit.

  ```python
  # ==================================================================================
  # Section topic
  # ==================================================================================
  ```

**Integrated example.**

```python
# Good: explains a non-obvious constraint
# The upstream API returns 200 for a queued job, not for a finished one.
response = client.submit_job(payload)

# Bad: restates the code and leaves an ownerless marker
# Call the API
response = client.submit_job(payload)  # TODO: handle errors
```

### Code examples

- **MUST NOT** include realistic secrets or personal data in an example; use placeholders such as `<token>` or `REDACTED`.
- **SHOULD** apply the same standards to example code as to production code (except where intentionally illustrating a violation), keeping each example minimal, focused, and complete enough to understand or elided with `...`.
- **SHOULD** use a `python` fence only for code that parses on the project's minimum Python version (or carry a `# Python 3.x+` marker without a colon and show the compatible alternative nearby, avoiding APIs unavailable in the minimum version), and use `text` for pseudo-code, intentionally invalid code, or output.
- **SHOULD** label contrasting examples `# Good` and `# Bad` with why the bad one is wrong, use `>>>` only for doctests, and use fakes or stubs instead of real network, filesystem, clock, or randomness calls unless demonstrating them.
- **SHOULD NOT** add suppressions to a bad example just to keep it in a linted file (move it to documentation or exclude it), and **MAY** separate statement-level examples with a single blank line while keeping two blank lines around top-level definitions and classes.
