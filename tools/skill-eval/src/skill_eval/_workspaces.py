"""Per-case workspace lifecycle and output inventory collection."""

import contextlib
import os
import shutil
from typing import TYPE_CHECKING

import anyio
from pydantic_evals.lifecycle import CaseLifecycle
from pydantic_evals.reporting import ReportCaseFailure

from skill_eval._helpers import run_in_thread
from skill_eval.exceptions import ConfigError
from skill_eval.models import RunObservation, SkillCaseInput, SkillCaseMetadata

if TYPE_CHECKING:
    from pathlib import Path

    from skill_eval.models import SkillCaseResult, SkillEvaluatorContext

_IGNORED_SKILL_DIRS = {
    "evals",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
}


async def prepare_case_workspace(inputs: SkillCaseInput) -> None:
    """Create a case workspace and copy its immutable deployment inputs.

    Args:
        inputs (SkillCaseInput):
            Case paths, skill snapshot and fixture source declarations.
    """
    for directory in (
        inputs.workspace_dir,
        inputs.output_dir,
        inputs.raw_evidence_dir,
    ):
        await anyio.Path(directory).mkdir(parents=True, exist_ok=True)
    await anyio.Path(inputs.workspace_dir / ".home").mkdir(exist_ok=True)
    await anyio.Path(inputs.workspace_dir / ".tmp").mkdir(exist_ok=True)

    if inputs.skill_source_path is not None and inputs.skill_name:
        await run_in_thread(
            _copy_skill,
            inputs.skill_source_path,
            inputs.workspace_dir / "skills",
            inputs.skill_name,
        )

    source_root = inputs.fixture_source_root
    for fixture in inputs.fixture_files:
        if source_root is None:
            continue
        source = source_root / fixture
        destination = inputs.workspace_dir / fixture
        await run_in_thread(_copy_fixture, source, destination)


async def reset_case_workspace(inputs: SkillCaseInput) -> None:
    """Remove all attempt artifacts and recreate a clean case workspace.

    Args:
        inputs (SkillCaseInput):
            Case paths and immutable inputs used to repopulate the workspace.
    """
    await run_in_thread(_remove_case_directories, inputs)
    await prepare_case_workspace(inputs)


class EvaluationLifecycle(
    CaseLifecycle[SkillCaseInput, RunObservation, SkillCaseMetadata]
):
    """Create an isolated workspace, then clean it after grading."""

    async def setup(self) -> None:
        """Create the isolated workspace and copy inputs and the skill."""
        await prepare_case_workspace(self.case.inputs)

    async def prepare_context(
        self,
        ctx: "SkillEvaluatorContext",
    ) -> "SkillEvaluatorContext":
        """Collect a stable outputs inventory before evaluators run.

        Args:
            ctx (SkillEvaluatorContext):
                Evaluation context to enrich with the outputs inventory.

        Returns:
            SkillEvaluatorContext:
                The same context with inventory data or an inventory error attribute.
        """
        inputs = self.case.inputs
        try:
            inventory = await run_in_thread(_collect_inventory, inputs.output_dir)
        except OSError as err:
            ctx.attributes["outputs_inventory_error"] = str(err)
            inventory = []
        ctx.attributes["outputs_inventory"] = inventory
        return ctx

    async def teardown(self, result: "SkillCaseResult | None") -> None:
        """Clean up the workspace after a successful scored case.

        Args:
            result (SkillCaseResult | None):
                Completed case result, failed case result, or None when no result
                exists.
        """
        inputs = self.case.inputs
        if result is None or isinstance(result, ReportCaseFailure):
            return
        # Cleanup is best-effort; evidence and declared outputs live outside the
        # workspace.
        with contextlib.suppress(OSError):
            await run_in_thread(shutil.rmtree, inputs.workspace_dir)


def _copy_skill(source: "Path", skills_root: "Path", name: str) -> None:
    root = skills_root.resolve()
    destination = (root / name).resolve()
    if destination.parent != root:
        raise ConfigError(f"skill deployment escapes the workspace: {name!r}")
    if not destination.exists():
        shutil.copytree(
            source,
            destination,
            ignore=shutil.ignore_patterns(*_IGNORED_SKILL_DIRS),
        )


def _remove_case_directories(inputs: SkillCaseInput) -> None:
    for directory in (
        inputs.workspace_dir,
        inputs.output_dir,
        inputs.raw_evidence_dir,
    ):
        if directory.exists():
            shutil.rmtree(directory)


def snapshot_skill(source: "Path", destination: "Path") -> None:
    """Copy a complete skill tree for immutable subsequent evaluation reads.

    Args:
        source (Path):
            Original candidate or baseline skill directory.
        destination (Path):
            New snapshot directory inside the experiment.
    """
    if destination.exists():
        raise ConfigError(f"skill snapshot destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns(
            "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"
        ),
    )


def _copy_fixture(source: "Path", destination: "Path") -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        shutil.copy2(source, destination)


def _collect_inventory(root: "Path") -> list[dict[str, object]]:
    inventory: list[dict[str, object]] = []
    if not root.exists():
        return inventory
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        stat = path.lstat()
        if path.is_symlink():
            inventory.append({"path": relative, "type": "symlink", "size": 0})
        elif path.is_dir():
            continue
        elif path.is_file():
            inventory.append({"path": relative, "type": "file", "size": stat.st_size})
        else:
            inventory.append({"path": relative, "type": "other", "size": stat.st_size})
    return inventory


def sanitized_environment(workspace: "Path") -> dict[str, str]:
    """Build an isolated verifier environment without model credentials.

    Args:
        workspace (Path):
            Case workspace providing isolated home and temporary directories.

    Returns:
        dict[str, str]:
            Sanitized environment with isolated home, temporary and bytecode settings.
    """
    blocked = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
    env = {
        key: value
        for key, value in os.environ.items()
        if not any(marker in key.upper() for marker in blocked)
    }
    env["HOME"] = str(workspace / ".home")
    env["TMPDIR"] = str(workspace / ".tmp")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env
