"""Official ``evals/evals.json`` support and evaluation bundle handling."""

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_evals import Case, Dataset

from skill_eval.exceptions import ConfigError

if TYPE_CHECKING:
    from skill_eval.models import SkillEvalYaml

_EVAL_DIR_RE = re.compile(r"[^a-zA-Z0-9._-]+")


class EvalEntry(BaseModel):
    """One entry in the ``evals[]`` array."""

    model_config = ConfigDict(extra="allow", frozen=True)

    id: str
    prompt: str = Field(min_length=1)
    expected_output: str = Field(min_length=1)
    files: tuple[str, ...] = ()
    assertions: tuple[str, ...] = ()

    @field_validator("id", mode="before")
    @classmethod
    def _normalize_id(cls, value: object) -> str:
        match value:
            case bool():
                raise TypeError("eval id must not be a boolean")
            case int():
                return str(value)
            case str() if value:
                return value
            case _:
                raise ValueError("eval id must be a non-empty string or integer")

    @field_validator("assertions")
    @classmethod
    def _non_empty_assertions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not assertion.strip() for assertion in value):
            raise ValueError("assertions must not contain empty strings")
        return value


class EvalFile(BaseModel):
    """The ``evals/evals.json`` document."""

    model_config = ConfigDict(extra="allow", frozen=True)

    skill_name: str = Field(min_length=1)
    evals: tuple[EvalEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> "EvalFile":
        ids = [item.id for item in self.evals]
        if len(ids) != len(set(ids)):
            duplicates = sorted({item for item in ids if ids.count(item) > 1})
            raise ValueError(
                f"duplicate eval ids after normalization: {', '.join(duplicates)}"
            )
        return self


class EvalCaseInput(BaseModel):
    """Inputs for inspecting the eval file without running an arm."""

    model_config = ConfigDict(frozen=True)

    case_id: str
    """Eval case identifier."""
    prompt: str
    """Prompt text for the case."""
    fixture_files: tuple[str, ...] = ()
    """Fixture files declared for the case."""


class EvalCaseMetadata(BaseModel):
    """Metadata carried by the public eval file view."""

    model_config = ConfigDict(frozen=True)

    eval_id: str
    """Eval identifier."""
    eval_dir_name: str
    """Filesystem-safe eval directory name."""
    expected_output: str
    """Expected output description from the eval file."""
    assertions: tuple[str, ...] = ()
    """Assertion texts."""
    source_files: tuple[str, ...] = ()
    """Fixture paths declared by the eval file."""


# ==================================================================================
# Dataset loading and validation
# ==================================================================================


def load_eval_file(skill_path: Path) -> EvalFile:
    """Read and validate ``SKILL_PATH/evals/evals.json``.

    Args:
        skill_path (Path):
            Skill directory containing the eval file.

    Returns:
        EvalFile:
            Parsed and validated eval file.

    Raises:
        ConfigError:
            If the dataset is missing, unreadable or invalid.
    """
    eval_file = skill_path / "evals" / "evals.json"
    if not eval_file.is_file():
        raise ConfigError(f"missing official eval dataset: {eval_file}")
    try:
        raw = json.loads(eval_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as err:
        raise ConfigError(f"cannot read {eval_file}: {err}") from err
    try:
        return EvalFile.model_validate(raw)
    except ValueError as err:
        raise ConfigError(f"invalid {eval_file}: {err}") from err


def eval_dir_name(eval_id: str, used: set[str] | None = None) -> str:
    """Return a stable, safe directory name for an eval id.

    Args:
        eval_id (str):
            Eval identifier to sanitize.
        used (set[str], optional):
            Already allocated names used to avoid collisions. Defaults to no collision
            tracking.

    Returns:
        str:
            Safe ``eval-`` prefixed directory name, suffixed when necessary.
    """
    slug = _EVAL_DIR_RE.sub("-", eval_id).strip("-._") or "case"
    name = f"eval-{slug}"
    if used is None:
        return name
    candidate = name
    index = 2
    while candidate in used:
        candidate = f"{name}-{index}"
        index += 1
    used.add(candidate)
    return candidate


def load_eval_dataset(
    skill_path: Path,
) -> Dataset[EvalCaseInput, str, EvalCaseMetadata]:
    """Convert the eval file into an in-memory Pydantic Evals dataset.

    Args:
        skill_path (Path):
            Skill directory containing ``evals/evals.json``.

    Returns:
        Dataset[EvalCaseInput, str, EvalCaseMetadata]:
            Validated eval cases in declaration order.

    Raises:
        ConfigError:
            If the dataset is missing or invalid.
    """
    dataset = load_eval_file(skill_path)
    cases: list[Case[EvalCaseInput, str, EvalCaseMetadata]] = []
    used_names: set[str] = set()

    for item in dataset.evals:
        name = eval_dir_name(item.id, used_names)
        cases.append(
            Case(
                name=name,
                inputs=EvalCaseInput(
                    case_id=item.id,
                    prompt=item.prompt,
                    fixture_files=item.files,
                ),
                expected_output=item.expected_output,
                metadata=EvalCaseMetadata(
                    eval_id=item.id,
                    eval_dir_name=name,
                    expected_output=item.expected_output,
                    assertions=item.assertions,
                    source_files=item.files,
                ),
            )
        )

    return Dataset(name=f"{dataset.skill_name}-official", cases=cases)


def validate_dataset_files(dataset: EvalFile, skill_path: Path) -> list[str]:
    """Validate fixture paths and assertion uniqueness for one eval file.

    Args:
        dataset (EvalFile):
            Eval file to inspect.
        skill_path (Path):
            Skill root that fixture paths must stay within.

    Returns:
        list[str]:
            Duplicate assertion, unsafe path and missing fixture errors.
    """
    errors: list[str] = []
    root = skill_path.resolve()

    for item in dataset.evals:
        seen: set[str] = set()
        for assertion in item.assertions:
            if assertion in seen:
                errors.append(f"eval {item.id!r}: duplicate assertion {assertion!r}")
            seen.add(assertion)
        for fixture in item.files:
            fixture_path = Path(fixture)
            if fixture_path.is_absolute():
                errors.append(
                    f"eval {item.id!r}: fixture path must be relative: {fixture}"
                )
                continue
            if ".." in fixture_path.parts:
                errors.append(
                    f"eval {item.id!r}: fixture path must not contain '..': {fixture}"
                )
                continue
            resolved = (skill_path / fixture_path).resolve()
            try:
                resolved.relative_to(root)
            except ValueError:
                errors.append(
                    f"eval {item.id!r}: fixture escapes the skill root: {fixture}"
                )
                continue
            if not resolved.is_file():
                errors.append(f"eval {item.id!r}: fixture does not exist: {fixture}")

    return errors


# ==================================================================================
# Dataset hashing
# ==================================================================================


def dataset_hash(
    skill_path: Path,
    dataset: EvalFile,
    config: "SkillEvalYaml | None" = None,
) -> str:
    """Hash the official JSON and every resolved fixture for comparability.

    Args:
        skill_path (Path):
            Skill directory containing the dataset and fixtures.
        dataset (EvalFile):
            Validated dataset declaring fixture paths.
        config (SkillEvalYaml, optional):
            Evaluation configuration whose trigger fixtures also require hashing.

    Returns:
        str:
            SHA-256 digest covering the official JSON and fixture contents.
    """
    digest = hashlib.sha256()
    digest.update((skill_path / "evals" / "evals.json").read_bytes())
    fixtures = [fixture for item in dataset.evals for fixture in item.files]
    if config is not None and config.trigger is not None:
        fixtures.extend(
            fixture for item in config.trigger.cases for fixture in item.files
        )
    for fixture in fixtures:
        path = (skill_path / fixture).resolve()
        digest.update(fixture.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def hash_tree(root: Path) -> str:
    """Hash a bundle tree deterministically, excluding generated caches.

    Args:
        root (Path):
            Root of the file tree to hash.

    Returns:
        str:
            SHA-256 digest covering relative paths, file sizes and contents.
    """
    digest = hashlib.sha256()
    excluded_dirs = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in excluded_dirs for part in relative.parts):
            continue
        if path.is_dir():
            continue
        if path.suffix in {".pyc", ".pyo"} or path.name == "feedback.json":
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(path.stat().st_size).encode("ascii"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


# ==================================================================================
# Evaluation bundle
# ==================================================================================


@dataclass(frozen=True, slots=True)
class EvaluationBundle:
    """The self-contained evaluation inputs shared by every arm."""

    root: Path
    content_hash: str
    eval_file: Path
    config_file: Path | None
    verifier: Path | None


def copy_evaluation_bundle(
    skill_path: Path,
    destination: Path,
    config_path: Path | None = None,
) -> EvaluationBundle:
    """Copy ``evals/`` once and hash the copy used by every arm.

    Args:
        skill_path (Path):
            Skill directory containing the source ``evals/`` tree.
        destination (Path):
            New directory for the copied evaluation bundle.
        config_path (Path, optional):
            External configuration to include. Defaults to the bundle's existing config.

    Returns:
        EvaluationBundle:
            Copied bundle paths and content hash.

    Raises:
        ConfigError:
            If inputs are missing or the destination already exists.
    """
    source = skill_path / "evals"
    if not source.is_dir():
        raise ConfigError(f"missing evals directory: {source}")
    if destination.exists():
        raise ConfigError(
            f"evaluation bundle destination already exists: {destination}"
        )

    ignore = shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", "*.pyo")
    shutil.copytree(source, destination, ignore=ignore)
    if config_path is not None and config_path.is_file():
        target = destination / "skill-eval.yaml"
        if config_path.resolve() != (source / "skill-eval.yaml").resolve():
            shutil.copy2(config_path, target)

    eval_file = destination / "evals.json"
    if not eval_file.is_file():
        raise ConfigError(f"evaluation bundle is missing evals.json: {destination}")
    config_file = destination / "skill-eval.yaml"
    verifier = destination / "verify.py"

    return EvaluationBundle(
        root=destination,
        content_hash=hash_tree(destination),
        eval_file=eval_file,
        config_file=config_file if config_file.is_file() else None,
        verifier=verifier if verifier.is_file() else None,
    )
