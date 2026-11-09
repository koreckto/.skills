# Python Version Compatibility

Supported Python version matrix (3.11–3.15), minimum-version detection, Ruff target selection, and compatibility patterns. Individual rules stay in the style and language references and carry a `Since:` tag when they depend on a newer minimum Python version.

## Supported versions

The feature matrix covers every Python version that still receives maintenance support. A project's declared minimum Python version may be higher.

Verified on 2026-11-09 against the Python Developer's Guide status page and the CPython "What's New" documentation.

| Version | Status | First release | End of life |
| --- | --- | --- | --- |
| 3.11 | security | 2022-10-24 | 2027-10 |
| 3.12 | security | 2023-10-02 | 2028-10 |
| 3.13 | security | 2024-10-07 | 2029-10 |
| 3.14 | bugfix | 2025-10-07 | 2030-10 |
| 3.15 | bugfix | 2026-10-09 | 2031-10 |

Python 3.10 reached end of life on 2026-10-01 and is not part of the supported range. Python 3.16 has not been released.

The skill itself requires Python 3.11+ for its examples and the shared Ruff configuration. That is the skill's minimum version, not a constraint on a project's minimum version. A project may declare 3.12, 3.13, or newer.

## Determine the minimum Python version

Use the lowest version the project declares support for, not the version installed locally and not the newest version in CI.

Read, in order:

1. `[project] requires-python` in `pyproject.toml`.
2. Poetry's `[tool.poetry.dependencies] python`.
3. Trove classifiers such as `Programming Language :: Python :: 3.11`.
4. The CI matrix, `tox.ini`, or `noxfile.py`.

Use `.python-version` only as a development hint. It often pins a developer's preferred version, not the minimum supported version. If no minimum version is declared anywhere, ask instead of guessing.

Normalize the result to a major/minor pair. For Ruff, `3.11` maps to `py311`; patch versions do not change the target.

## Ruff target selection

Ruff recommends `[project] requires-python` over `target-version` when a `pyproject.toml` already exists. If `requires-python` is present, omit `target-version` and let Ruff infer the target. If both are present, `target-version` takes precedence.

- If the project has PEP 621 metadata, rely on `requires-python`.
- If the project has no PEP 621 metadata, set `target-version` to the minimum supported version.
- Never leave a copied `target-version` from another project without checking the minimum Python version.
- Ruff's own default target is `py311`. A missing `requires-python` can therefore silently target 3.11.
- `target-version` controls version-aware lint suggestions, not whether a standard-library API exists. Verify APIs against the documentation for the minimum version.
- Keep `requires-python`, the CI matrix, and the Ruff target consistent.

## Feature matrix

The table is cumulative. A project with a 3.11 minimum version may use the 3.11 row, but not 3.12+ features. The "Representative features" column is not exhaustive; verify a specific API against the standard library documentation for the minimum version.

| Minimum version | Ruff target | Representative features available | Not available; use a compatibility layer |
| --- | --- | --- | --- |
| 3.11 | `py311` | PEP 604 unions, built-in generics, `Self`, `StrEnum`, `TaskGroup`, `tomllib`, `except*`, `datetime.UTC` | PEP 695 generics and type aliases, `typing.override`, `typing.TypeIs`, `typing.ReadOnly`, `warnings.deprecated` |
| 3.12 | `py312` | PEP 695 syntax, `typing.override`, `itertools.batched`, `Path.walk`, f-string quote reuse | `TypeIs`, `ReadOnly`, `warnings.deprecated`, `copy.replace`, `Path.full_match` |
| 3.13 | `py313` | `TypeIs`, `ReadOnly`, `warnings.deprecated`, `copy.replace`, `Path.full_match`, `typing.NoDefault` | t-strings, `annotationlib`, `compression.zstd`, `Path.copy` and `Path.move` |
| 3.14 | `py314` | PEP 649/749 deferred annotations, t-strings, `annotationlib`, `compression.zstd`, `Path.copy` and `Path.move`, `concurrent.interpreters` | `frozendict`, `sentinel`, `TypeForm`, lazy imports, comprehension unpacking |
| 3.15 | `py315` | `frozendict`, `sentinel`, `TypeForm`, TypedDict typed extra items, lazy imports, comprehension unpacking, UTF-8 as the default encoding | If any supported version is below 3.15, continue to pass `encoding` explicitly for file I/O |

A feature listed as unavailable in the minimum version may be available through `typing_extensions` or a third-party backport. Use the backport only when the minimum version lacks the feature. Do not use it for features already available in the minimum version.

## Compatibility patterns

### Use version guards for APIs, not syntax

`sys.version_info` can select an import or a standard-library API:

```python
import sys

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override
```

The parser still parses the entire file. Newer syntax such as the `type` statement or PEP 695 generic parameters cannot be hidden in a false branch; it fails on the older interpreter before the branch runs.

### Centralize backports

Put version-dependent imports in one module, for example `_compat.py`, and import from there:

```python
# _compat.py
import sys

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

__all__ = ["override"]
```

Keep the compatibility layer small. Remove a branch when the minimum Python version no longer needs it.

### Do not use future annotations

The shared Ruff configuration bans `from __future__ import annotations`. On Python 3.11–3.13, quote forward references where the runtime needs them; on Python 3.14+, PEP 649 defers evaluation natively, and `UP037` removes quotes:

```python
# Python 3.11–3.13 (on 3.14+, omit quotes)
class Node:
    def link(self, other: "Node") -> None:
        self.other = other
```

Quote only references that are not defined at annotation-evaluation time. Quoting every annotation is noise.

### Keep runtime imports at runtime

Imports that are evaluated at runtime, such as base classes, `isinstance` checks, decorators, and framework annotation resolution, stay outside `TYPE_CHECKING`. `TC004` catches direct runtime uses, but not `get_type_hints`, `get_overloads`, or framework resolution. See [Type annotations](language-rules.md#type-annotations).

### Version-specific examples

Examples in documentation follow the same version policy as production code; see [Style: code examples](style-rules.md#code-examples) for the rules. When an example demonstrates syntax or an API that requires a newer minimum Python version, mark it with `# Python 3.x+` (without a colon so `ERA001` does not treat it as commented-out code) and show the 3.11-compatible alternative:

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

## Version-gated rules

Use `Since:` when a rule depends on a newer minimum Python version. The tag means:

- The rule applies only when the project's minimum Python version is at least the stated version.
- On an older minimum version, use the documented alternative.
- The verification tag still describes the check; `Since:` is a scope qualifier, not a replacement for the check.

For example, the type annotation section records the PEP 695 rule with `Ruff: UP040, UP046, UP047` and `Since: 3.12`, and the data modeling section records the `frozendict` rule with `Review` and `Since: 3.15`.

Do not scatter version claims through the references. Keep the feature data in this file and the `Since:` scope tags next to the rules.

## End-of-life maintenance

When a Python version reaches end of life:

1. Remove it from `requires-python`, the CI matrix, and the Ruff target.
2. Remove compatibility shims that existed only for that version.
3. Re-run the full test matrix.
4. Update this file with a new verification date.
5. Update the changelog if the supported range changes.

If a project still declares an end-of-life version, do not silently treat it as supported. Flag it and recommend an upgrade; keep the project's declared minimum version only if the project explicitly requires it.

## Sources

- [Python Developer's Guide: versions](https://devguide.python.org/versions/)
- [Python "What's New" documentation](https://docs.python.org/3/whatsnew/)
- [Ruff: target version](https://docs.astral.sh/ruff/settings/#target-version)
- [typing_extensions](https://typing-extensions.readthedocs.io/)

The support table and feature matrix are time-sensitive. Update the verification date whenever the file changes.
