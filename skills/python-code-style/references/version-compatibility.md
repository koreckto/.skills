# Python Version Compatibility

Minimum-version detection, Python 3.11-3.15 feature matrix, and compatibility patterns. Verified on 2026-11-09 against Python release status and CPython What's New documentation.

## Minimum Version and Ruff Target

Determine the project's lowest supported Python version (not the local interpreter or newest CI version) in order:

1. `[project] requires-python` in `pyproject.toml`.
2. `[tool.poetry.dependencies] python`.
3. Trove classifiers (`Programming Language :: Python :: 3.x`).
4. CI matrix, `tox.ini`, or `noxfile.py`.

Treat `.python-version` only as a development hint; ask instead of guessing when no minimum version is declared. If a project declares Python 3.10 or older (3.10 reached EOL on 2026-10-01), flag it and recommend upgrading unless the project explicitly requires it.

Prefer `[project] requires-python` so Ruff infers `target-version` automatically (Ruff defaults to `py311` if undeclared, and `target-version` overrides `requires-python` if both exist). Never copy `target-version` blindly, and remember that `target-version` controls syntax and lint rules only; always verify whether a standard-library API exists in the declared minimum version.

## Feature Matrix (3.11-3.15)

The table is cumulative; projects may use features from their minimum version row and earlier:

| Minimum version | Ruff target | Key available features | Unavailable (use alternative or backport) |
| :--- | :--- | :--- | :--- |
| 3.11 | `py311` | PEP 604 unions, built-in generics, `Self`, `StrEnum`, `TaskGroup`, `tomllib`, `except*`, `datetime.UTC` | PEP 695 generics/type aliases, `override`, `TypeIs`, `ReadOnly`, `warnings.deprecated` |
| 3.12 | `py312` | PEP 695 syntax (`type X`, `def f[T]`), `typing.override`, `itertools.batched`, `Path.walk`, f-string quote reuse | `TypeIs`, `ReadOnly`, `warnings.deprecated`, `copy.replace`, `Path.full_match` |
| 3.13 | `py313` | `TypeIs`, `ReadOnly`, `warnings.deprecated`, `copy.replace`, `Path.full_match`, `typing.NoDefault` | t-strings, `annotationlib`, `compression.zstd`, `Path.copy`, `Path.move` |
| 3.14 | `py314` | PEP 649/749 deferred annotations, t-strings, `annotationlib`, `compression.zstd`, `Path.copy`, `Path.move` | `frozendict`, `sentinel`, `TypeForm`, lazy imports, comprehension unpacking |
| 3.15 | `py315` | `frozendict`, `sentinel`, `TypeForm`, TypedDict extra items, lazy imports, comprehension unpacking, UTF-8 default encoding | Pass `encoding=` explicitly whenever any supported version is below 3.15 |

## Compatibility Patterns

- **Version guards are for APIs, never syntax**: Use `sys.version_info` only to select imports or standard-library APIs (centralized in a small `_compat.py` module, using `typing_extensions` only when the minimum version lacks the feature, and removing shims once the minimum advances). Python parses the entire file before running branches, so newer syntax breaks older interpreters even inside a false `sys.version_info` branch.

  ```python
  # _compat.py
  import sys

  if sys.version_info >= (3, 12):
      from typing import override
  else:
      from typing_extensions import override

  __all__ = ["override"]
  ```

- **No future annotations (`TID251`)**: On Python 3.11-3.13, quote forward references and `TYPE_CHECKING`-only types where needed at definition time; on Python 3.14+, omit quotes where PEP 649 defers evaluation natively.

  ```python
  # Python 3.11-3.13 (on 3.14+, omit quotes)
  class Node:
      def link(self, other: "Node") -> None:
          self.other = other
  ```

- **Version-specific documentation examples**: Mark examples requiring a newer Python version with `# Python 3.x+` (no colon so `ERA001` does not treat it as commented-out code) and show the 3.11-compatible alternative nearby.

  ```python
  # Python 3.12+ (PEP 695)
  def first[T](items: list[T]) -> T:
      """Returns the first item."""
      return items[0]
  ```

  ```python
  # Compatible alternative (3.11)
  from typing import TypeVar

  T = TypeVar("T")


  def first(items: list[T]) -> T:
      """Returns the first item."""
      return items[0]
  ```
