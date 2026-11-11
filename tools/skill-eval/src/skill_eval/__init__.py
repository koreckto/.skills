"""Agent Skills evaluation tool."""

from functools import cache
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    __version__: str


__all__ = ["__version__"]


@cache
def _package_version() -> str:
    try:
        return version("skill_eval")
    except PackageNotFoundError:
        return "0.0.0+unknown"


def __getattr__(name: str) -> str:
    if name == "__version__":
        return _package_version()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
