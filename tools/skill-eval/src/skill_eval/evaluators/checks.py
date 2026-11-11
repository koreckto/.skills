"""Deterministic checks bound to official assertions."""

import contextlib
import hashlib
import os
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

import anyio
from anyio.lowlevel import checkpoint
from pydantic_evals.evaluators import EvaluationReason, Evaluator

from skill_eval._helpers import to_slug
from skill_eval._workspaces import sanitized_environment
from skill_eval.exceptions import VerifierError
from skill_eval.models import (
    Arm,
    CheckSpec,
    CommandCheck,
    RunObservation,
    SkillCaseInput,
    SkillCaseMetadata,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from anyio import AsyncFile
    from anyio.abc import ByteReceiveStream, Process

    from skill_eval.models import SkillEvaluatorContext

_MAX_VERIFIER_OUTPUT_BYTES = 10 * 1024 * 1024
_VERIFIER_TAIL_BYTES = 8192
_VERIFIER_SPAWN_TIMEOUT_SECONDS = 5.0


@dataclass
class _CapturedStream:
    tail: bytearray = field(default_factory=bytearray)
    total_bytes: int = 0


@dataclass
class FileExists(Evaluator[SkillCaseInput, RunObservation, SkillCaseMetadata]):
    """Check declared output files against the lifecycle's outputs inventory."""

    checks: tuple[CheckSpec, ...]
    """Deterministic checks configured for the case."""

    def evaluate(
        self,
        ctx: "SkillEvaluatorContext",
    ) -> dict[str, EvaluationReason]:
        """Evaluate every file_exists check against the outputs inventory.

        Args:
            ctx (SkillEvaluatorContext):
                Evaluation context containing lifecycle inventory data.

        Returns:
            dict[str, EvaluationReason]:
                File-existence verdicts keyed by assertion text.

        Raises:
            VerifierError:
                If the lifecycle could not inspect generated outputs.
        """
        error = ctx.attributes.get("outputs_inventory_error")
        if error:
            raise VerifierError(f"cannot inspect outputs: {error}")
        inventory = ctx.attributes.get("outputs_inventory") or []
        by_path = {
            str(item.get("path")): item for item in inventory if isinstance(item, dict)
        }
        results: dict[str, EvaluationReason] = {}

        for check in self.checks:
            if check.type != "file_exists":
                continue
            path = PurePosixPath(check.path)
            if path.is_absolute() or ".." in path.parts or "\\" in check.path:
                results[check.assertion] = EvaluationReason(
                    False, f"invalid output path: {check.path}"
                )
                continue
            entry = by_path.get(path.as_posix())
            if entry is None:
                results[check.assertion] = EvaluationReason(
                    False, f"output not found: {check.path}"
                )
                continue
            kind = entry.get("type")
            size = int(entry.get("size") or 0)
            if kind != "file":
                results[check.assertion] = EvaluationReason(
                    False,
                    f"output is not a regular file: {check.path} (type={kind})",
                )
                continue
            if check.non_empty and size == 0:
                results[check.assertion] = EvaluationReason(
                    False, f"output is empty: {check.path}"
                )
                continue
            results[check.assertion] = EvaluationReason(
                True,
                f"found regular file {check.path} ({size} bytes)",
            )

        return results


@dataclass
class VerifyCommand(Evaluator[SkillCaseInput, RunObservation, SkillCaseMetadata]):
    """Invoke the evaluation bundle's standard ``verify.py`` for command checks."""

    checks: tuple[CheckSpec, ...]
    """Deterministic checks configured for the case."""
    bundle_dir: Path
    """Copied evaluation bundle containing the verifier."""
    case_id: str
    """Eval case identifier passed to the verifier."""
    arm: Arm
    """Comparison arm passed to the verifier."""

    async def evaluate(
        self,
        ctx: "SkillEvaluatorContext",
    ) -> dict[str, EvaluationReason]:
        """Run every command check through the bundle verifier.

        Args:
            ctx (SkillEvaluatorContext):
                Evaluation context containing verifier paths and run evidence.

        Returns:
            dict[str, EvaluationReason]:
                Verifier verdicts and output evidence keyed by assertion text.

        Raises:
            VerifierError:
                If the verifier is missing, cannot run, times out or violates its
                contract.
        """
        results: dict[str, EvaluationReason] = {}
        for check in self.checks:
            if check.type != "command":
                continue
            results[check.assertion] = await self._run_check(ctx, check)
        return results

    async def _run_check(
        self,
        ctx: "SkillEvaluatorContext",
        check: CommandCheck,
    ) -> EvaluationReason:
        bundle_dir = self.bundle_dir
        inputs = ctx.inputs
        assertion_hash = hashlib.sha256(check.assertion.encode("utf-8")).hexdigest()[
            :12
        ]
        evidence_dir = (
            inputs.raw_evidence_dir
            / "checks"
            / f"{to_slug(check.assertion)}-{assertion_hash}"
        )
        stdout_path = evidence_dir / "stdout.txt"
        stderr_path = evidence_dir / "stderr.txt"
        verifier = bundle_dir / "verify.py"
        await _prepare_verifier(verifier, evidence_dir)
        argv = [
            sys.executable,
            str(verifier),
            "--workspace",
            str(inputs.workspace_dir),
            "--outputs",
            str(inputs.output_dir),
            "--case",
            self.case_id,
            "--assertion",
            check.assertion,
            "--arm",
            self.arm,
        ]
        process, process_group_id = await _start_verifier_process(
            argv, inputs, verifier
        )
        try:
            try:
                with anyio.fail_after(check.timeout_seconds):
                    stdout_capture, stderr_capture = await _communicate(
                        process, stdout_path, stderr_path
                    )
            except TimeoutError as err:
                raise VerifierError(
                    f"verifier timed out after {check.timeout_seconds:g}s for "
                    f"assertion {check.assertion!r}"
                ) from err
        except BaseException:
            with contextlib.suppress(Exception):
                await _kill_and_reap(process, process_group_id)
            raise
        else:
            # Residual race, accepted in review: the leader was already reaped, so a
            # reused process group id could in theory be signalled.
            await _kill_and_reap(process, process_group_id)

        stdout = _captured_text(stdout_capture)
        stderr = _captured_text(stderr_capture)
        code = process.returncode
        evidence = (
            f"exit={code}; stdout={stdout}; stderr={stderr}; "
            f"full_stdout={stdout_path}; full_stderr={stderr_path}"
        )

        match code:
            case 0:
                if not stdout.strip():
                    raise VerifierError(
                        f"verifier exited 0 with blank stdout for assertion "
                        f"{check.assertion!r}; full output: {stdout_path}"
                    )
                return EvaluationReason(True, evidence)
            case 1:
                return EvaluationReason(False, evidence)
            case 2:
                raise VerifierError(
                    f"verifier reported an internal or contract error for "
                    f"assertion {check.assertion!r}; {evidence}"
                )
            case _:
                raise VerifierError(
                    f"verifier exited with unexpected code {code} for assertion "
                    f"{check.assertion!r}; {evidence}"
                )


# ==================================================================================
# Verifier process helpers
# ==================================================================================


async def _start_verifier_process(
    argv: list[str], inputs: SkillCaseInput, verifier: Path
) -> "tuple[Process, int]":
    process: Process | None = None
    process_group_id: int | None = None

    async def spawn() -> None:
        nonlocal process, process_group_id
        process = await anyio.open_process(
            argv,
            cwd=inputs.workspace_dir,
            env=sanitized_environment(inputs.workspace_dir),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        process_group_id = process.pid

    try:
        try:
            spawn_timed_out = await _shielded_verifier_spawn(spawn)
        except OSError as err:
            raise VerifierError(f"cannot start verifier {verifier}: {err}") from err
        await checkpoint()
    except BaseException:
        if process is not None and process_group_id is not None:
            with contextlib.suppress(Exception):
                await _kill_and_reap(process, process_group_id)
        raise

    if spawn_timed_out or process is None or process_group_id is None:
        if process is not None and process_group_id is not None:
            with contextlib.suppress(Exception):
                await _kill_and_reap(process, process_group_id)
        raise VerifierError(
            f"timed out starting verifier after {_VERIFIER_SPAWN_TIMEOUT_SECONDS:g}s"
        )
    return process, process_group_id


async def _shielded_verifier_spawn(spawn: "Callable[[], Awaitable[None]]") -> bool:
    timed_out = False
    spawn_error: OSError | None = None

    async def child() -> None:
        nonlocal timed_out, spawn_error
        with anyio.move_on_after(_VERIFIER_SPAWN_TIMEOUT_SECONDS, shield=True) as scope:
            try:
                await spawn()
            except OSError as err:
                spawn_error = err
        timed_out = scope.cancel_called

    async with anyio.create_task_group() as tg:
        tg.start_soon(child)
    if spawn_error is not None:
        raise spawn_error
    return timed_out


async def _communicate(
    process: "Process", stdout_path: Path, stderr_path: Path
) -> tuple[_CapturedStream, _CapturedStream]:
    stdout = _CapturedStream()
    stderr = _CapturedStream()
    total_bytes = 0
    overflowed = False

    async with (
        await anyio.open_file(stdout_path, "wb") as stdout_log,
        await anyio.open_file(stderr_path, "wb") as stderr_log,
    ):

        async def _drain(
            stream: "ByteReceiveStream",
            capture: _CapturedStream,
            log: "AsyncFile[bytes]",
        ) -> None:
            nonlocal total_bytes, overflowed
            async for chunk in stream:
                capture.total_bytes += len(chunk)
                remaining = max(0, _MAX_VERIFIER_OUTPUT_BYTES - total_bytes)
                accepted = chunk[:remaining]
                total_bytes += len(accepted)
                _append_tail(capture.tail, accepted)
                if accepted:
                    await log.write(accepted)
                if len(accepted) < len(chunk):
                    overflowed = True
                    tg.cancel_scope.cancel()
                    return

        async with anyio.create_task_group() as tg:
            if process.stdout is not None:
                tg.start_soon(_drain, process.stdout, stdout, stdout_log)
            if process.stderr is not None:
                tg.start_soon(_drain, process.stderr, stderr, stderr_log)
            await process.wait()

    if overflowed:
        raise VerifierError(
            f"verifier output exceeded the {_MAX_VERIFIER_OUTPUT_BYTES}-byte "
            f"combined limit; partial stdout: {stdout_path}; "
            f"partial stderr: {stderr_path}"
        )
    return stdout, stderr


def _captured_text(capture: _CapturedStream) -> str:
    text = capture.tail.decode("utf-8", errors="replace")
    if capture.total_bytes <= len(capture.tail):
        return text
    omitted = capture.total_bytes - len(capture.tail)
    return f"[truncated {omitted} bytes]\n{text}"


def _append_tail(buffer: bytearray, data: bytes) -> None:
    buffer.extend(data)
    if len(buffer) > _VERIFIER_TAIL_BYTES:
        del buffer[:-_VERIFIER_TAIL_BYTES]


async def _prepare_verifier(verifier: Path, evidence_dir: Path) -> None:
    if not await anyio.Path(verifier).is_file():
        raise VerifierError(
            f"verifier is missing from the evaluation bundle: {verifier}"
        )
    await anyio.Path(evidence_dir).mkdir(parents=True, exist_ok=True)


async def _kill_and_reap(process: "Process", process_group_id: int) -> None:
    _kill_group(process_group_id)
    try:
        with anyio.CancelScope(shield=True):
            await process.wait()
    finally:
        # AnyIO's asyncio implementation shields its own pipe cleanup.
        await process.aclose()


def _kill_group(process_group_id: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(process_group_id, signal.SIGKILL)
