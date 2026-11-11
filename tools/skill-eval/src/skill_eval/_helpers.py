"""Shared helper module."""

import functools
import json
import re
from typing import TYPE_CHECKING

import anyio
from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


async def write_json(path: "Path", value: object) -> None:
    """Write UTF-8 JSON with stable formatting."""
    target = anyio.Path(path)
    await target.parent.mkdir(parents=True, exist_ok=True)
    await target.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _read_json(path: "Path") -> object:
    """Read a JSON document or raise a clear error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise ValueError(f"invalid JSON document {path}: {err}") from err


def read_json_model[ModelT: BaseModel](
    path: "Path", model_type: type[ModelT]
) -> ModelT:
    """Read and validate a JSON document against a Pydantic model."""
    try:
        return model_type.model_validate(_read_json(path))
    except ValidationError as err:
        raise ValueError(f"invalid JSON document {path}: {err}") from err


_SLUG_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def to_slug(value: str, *, fallback: str = "item") -> str:
    """Convert user text into a safe path component."""
    cleaned = _SLUG_RE.sub("-", value).strip("-._")
    return cleaned[:80] or fallback


def tail_text(text: str, limit: int = 8192) -> str:
    """Keep the last ``limit`` UTF-8 bytes without splitting a code point."""
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text
    tail = encoded[-limit:].decode("utf-8", errors="replace")
    return f"[truncated {len(encoded) - limit} bytes]\n{tail}"


async def run_in_thread[**P, T](
    func: "Callable[P, T]", /, *args: P.args, **kwargs: P.kwargs
) -> T:
    """Run a blocking callable in the AnyIO worker thread pool."""
    return await anyio.to_thread.run_sync(functools.partial(func, *args, **kwargs))
