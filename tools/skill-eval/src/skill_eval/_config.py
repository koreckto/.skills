"""Skill package validation and ``skill-eval.yaml`` loading."""

from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

import yaml
from pydantic import ValidationError
from skills_ref.parser import read_properties
from skills_ref.validator import validate as validate_skill_frontmatter

from skill_eval._datasets import (
    EvalFile,
    load_eval_file,
    validate_dataset_files,
)
from skill_eval.exceptions import ConfigError
from skill_eval.models import (
    CheckSpec,
    SkillEvalYaml,
    ValidationResult,
)

if TYPE_CHECKING:
    from skill_eval.models import TriggerCase

_DEFAULT_CONFIG_NAME = "skill-eval.yaml"


# ==================================================================================
# Frontmatter and configuration
# ==================================================================================


def read_skill_name(skill_path: Path) -> str:
    """Return the frontmatter name or raise a configuration error.

    Args:
        skill_path (Path):
            Skill directory containing ``SKILL.md``.

    Returns:
        str:
            Declared skill name.

    Raises:
        ConfigError:
            If the frontmatter cannot be read or parsed.
    """
    try:
        return read_properties(skill_path).name
    except Exception as err:
        raise ConfigError(
            f"cannot read SKILL.md frontmatter from {skill_path}: {err}"
        ) from err


def read_baseline_skill_name(skill_path: Path) -> str:
    """Validate baseline frontmatter and return its safe deployment name.

    Args:
        skill_path (Path):
            Baseline skill directory containing ``SKILL.md``.

    Returns:
        str:
            Validated skill name consisting of one safe path component.

    Raises:
        ConfigError:
            If the baseline frontmatter or skill name is invalid.
    """
    errors = validate_skill_frontmatter(skill_path)
    if errors:
        raise ConfigError("invalid baseline skill frontmatter: " + "; ".join(errors))
    name = read_skill_name(skill_path)
    path = PurePosixPath(name)
    if (
        not name
        or name in {".", ".."}
        or path.is_absolute()
        or len(path.parts) != 1
        or "\\" in name
        or "\0" in name
    ):
        raise ConfigError(
            f"baseline skill name must be one safe path component: {name!r}"
        )
    return name


def load_skill_eval_config(
    skill_path: Path,
    config_path: Path | None = None,
    *,
    required: bool = False,
) -> SkillEvalYaml:
    """Load the optional skill-level evaluation configuration.

    Args:
        skill_path (Path):
            Skill directory containing the default evaluation config.
        config_path (Path, optional):
            External configuration path. Defaults to ``evals/skill-eval.yaml``.
        required (bool, optional):
            Whether a missing configuration is an error. Defaults to False.

    Returns:
        SkillEvalYaml:
            Validated evaluation configuration, or defaults when optional config is
            absent.

    Raises:
        ConfigError:
            If the configuration is missing, unreadable or invalid.
    """
    path = (
        config_path
        if config_path is not None
        else skill_path / "evals" / _DEFAULT_CONFIG_NAME
    )
    if not path.is_file():
        if required:
            raise ConfigError(f"missing evaluation config: {path}")
        return SkillEvalYaml()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as err:
        raise ConfigError(f"cannot read {path}: {err}") from err
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must contain a YAML mapping")
    try:
        return SkillEvalYaml.model_validate(raw)
    except ValidationError as err:
        raise ConfigError(f"invalid {path}: {err}") from err


# ==================================================================================
# Evaluation validation
# ==================================================================================


def _validate_check_shape(check: CheckSpec) -> list[str]:
    errors: list[str] = []
    if check.type == "file_exists":
        path = PurePosixPath(check.path)
        if path.is_absolute():
            errors.append(
                f"check {check.case!r}/{check.assertion!r}: "
                "path must be relative to outputs/"
            )
        if ".." in path.parts:
            errors.append(
                f"check {check.case!r}/{check.assertion!r}: path must not contain '..'"
            )
        if any(char in check.path for char in "*?["):
            errors.append(
                f"check {check.case!r}/{check.assertion!r}: "
                "glob patterns are not supported"
            )
        if "\\" in check.path or "\0" in check.path:
            errors.append(
                f"check {check.case!r}/{check.assertion!r}: "
                "path contains an unsupported character"
            )
    return errors


def validate_check_bindings(
    dataset: EvalFile,
    config: SkillEvalYaml,
    skill_path: Path,
) -> list[str]:
    """Validate that checks point at existing official assertions.

    Args:
        dataset (EvalFile):
            Eval file providing eval IDs and assertions.
        config (SkillEvalYaml):
            Evaluation configuration containing deterministic checks.
        skill_path (Path):
            Skill directory used to resolve verifier requirements.

    Returns:
        list[str]:
            Validation errors in configuration declaration order.
    """
    errors: list[str] = []
    assertions_by_case = {item.id: item.assertions for item in dataset.evals}
    seen: set[tuple[str, str]] = set()

    for check in config.checks:
        errors.extend(_validate_check_shape(check))
        assertions = assertions_by_case.get(check.case)
        if assertions is None:
            errors.append(f"check references unknown eval id {check.case!r}")
            continue
        if check.assertion not in assertions:
            errors.append(
                f"check for eval {check.case!r} references an assertion that is "
                f"not present: {check.assertion!r}"
            )
            continue
        key = (check.case, check.assertion)
        if key in seen:
            errors.append(
                f"duplicate check for eval {check.case!r} assertion {check.assertion!r}"
            )
        seen.add(key)
        if check.type == "command":
            verifier = skill_path / "evals" / "verify.py"
            if not verifier.is_file() or verifier.is_symlink():
                errors.append(
                    f"command check for eval {check.case!r} requires a regular "
                    "evals/verify.py"
                )

    return errors


def _trigger_fixture_error(case_id: str, fixture: str, root: Path) -> str | None:
    path = PurePosixPath(fixture)
    if path.is_absolute() or ".." in path.parts:
        return (
            f"trigger case {case_id!r}: fixture path must be relative and stay inside "
            "the skill"
        )
    if not path.parts or path.parts[0] != "evals":
        return f"trigger case {case_id!r}: fixture must be inside evals/: {fixture}"
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return f"trigger case {case_id!r}: fixture escapes the skill root: {fixture}"
    try:
        resolved.relative_to((root / "evals").resolve())
    except ValueError:
        return f"trigger case {case_id!r}: fixture must stay inside evals/: {fixture}"
    if not resolved.is_file():
        return f"trigger case {case_id!r}: fixture does not exist: {fixture}"
    return None


def _trigger_polarity_errors(cases: "tuple[TriggerCase, ...]") -> list[str]:
    errors: list[str] = []
    if not any(case.should_trigger for case in cases):
        errors.append("trigger.cases needs at least one should_trigger=true case")
    if not any(not case.should_trigger for case in cases):
        errors.append("trigger.cases needs at least one should_trigger=false case")
    return errors


def validate_trigger_config(config: SkillEvalYaml, skill_path: Path) -> list[str]:
    """Validate trigger cases and their fixture paths.

    Args:
        config (SkillEvalYaml):
            Evaluation configuration containing the optional trigger suite.
        skill_path (Path):
            Skill root that fixture paths must stay within.

    Returns:
        list[str]:
            Trigger configuration and fixture validation errors.
    """
    if config.trigger is None:
        return []
    errors: list[str] = []
    if config.trigger.decoy_skills:
        errors.append("decoy_skills is not supported in the MVP; keep it empty")
    if not config.trigger.cases:
        errors.append("trigger.cases must not be empty when trigger is configured")
        return errors

    root = skill_path.resolve()
    seen: set[str] = set()

    for case in config.trigger.cases:
        if case.id in seen:
            errors.append(f"duplicate trigger case id: {case.id!r}")
        seen.add(case.id)
        for fixture in case.files:
            error = _trigger_fixture_error(case.id, fixture, root)
            if error is not None:
                errors.append(error)

    errors.extend(_trigger_polarity_errors(config.trigger.cases))
    return errors


# ==================================================================================
# Package validation
# ==================================================================================


def validate_skill(
    skill_path: Path, config_path: Path | None = None
) -> ValidationResult:
    """Validate the package, official dataset, fixtures, config and checks.

    The validation runs without model calls.

    Args:
        skill_path (Path):
            Skill directory to validate.
        config_path (Path, optional):
            External evaluation configuration. Defaults to the skill's config.

    Returns:
        ValidationResult:
            Validation status, resolved skill identity, errors and warnings.
    """
    skill_path = skill_path.resolve()
    errors: list[str] = []
    warnings: list[str] = []
    skill_name: str | None = None

    if not skill_path.exists() or not skill_path.is_dir():
        return ValidationResult.from_errors(
            skill_path, [f"skill path is not a directory: {skill_path}"]
        )
    errors.extend(validate_skill_frontmatter(skill_path))
    if errors:
        return ValidationResult.from_errors(skill_path, errors, warnings)
    try:
        skill_name = read_skill_name(skill_path)
    except ConfigError as err:
        return ValidationResult.from_errors(skill_path, [str(err)])

    try:
        dataset = load_eval_file(skill_path)
    except ConfigError as err:
        errors.append(str(err))
        return ValidationResult.from_errors(skill_path, errors, warnings, skill_name)

    if dataset.skill_name != skill_name:
        errors.append(
            f"evals.json skill_name {dataset.skill_name!r} does not match "
            f"SKILL.md name {skill_name!r}"
        )
    errors.extend(validate_dataset_files(dataset, skill_path))

    try:
        config = load_skill_eval_config(
            skill_path, config_path, required=config_path is not None
        )
    except ConfigError as err:
        errors.append(str(err))
        return ValidationResult.from_errors(skill_path, errors, warnings, skill_name)

    errors.extend(validate_check_bindings(dataset, config, skill_path))
    errors.extend(validate_trigger_config(config, skill_path))
    if not config.checks and not any(item.assertions for item in dataset.evals):
        warnings.append(
            "no assertions and no deterministic checks: runs will be ungraded"
        )

    return ValidationResult.from_errors(skill_path, errors, warnings, skill_name)
