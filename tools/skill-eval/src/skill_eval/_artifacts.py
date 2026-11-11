"""Official artifact layout, repeat aggregation and experiment summaries."""

import secrets
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import mean, stdev
from typing import TYPE_CHECKING, Literal, Never, NotRequired, TypedDict

from skill_eval._helpers import write_json

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from skill_eval.models import (
        ExperimentConfig,
        ExperimentStatus,
        RunObservation,
        SkillReportCase,
    )


class AssertionResult(TypedDict):
    """One assertion entry in ``grading.json``."""

    text: str
    passed: bool | None
    evidence: str
    error: NotRequired[bool]


class GradingTotals(TypedDict):
    """Assertion totals accumulated across cases."""

    passed: int
    failed: int
    errors: int
    total: int


class GradingSummary(GradingTotals):
    """Aggregate grading fields written for one case."""

    pass_rate: float | None


class GradingDocument(TypedDict):
    """Typed ``grading.json`` payload."""

    assertion_results: list[AssertionResult]
    summary: GradingSummary
    errors: list[str]


class TimingDocument(TypedDict):
    """Typed ``timing.json`` payload."""

    total_tokens: int | None
    duration_ms: float | None


class ArmMetrics(TypedDict):
    """Pass, duration and token metrics for one arm."""

    pass_rate: float | None
    duration_ms: float | None
    total_tokens: float | int | None


class MetricDocument(TypedDict):
    """Descriptive statistics for one numeric metric."""

    mean: float | None
    stddev: float | None
    min: float | None
    max: float | None
    n: int


class ArmBenchmarkDocument(TypedDict):
    """Metric summaries for one arm."""

    pass_rate: MetricDocument
    time_seconds: MetricDocument
    tokens: MetricDocument


class BenchmarkDocument(TypedDict):
    """Typed benchmark payload, including aggregate fields when present."""

    run_summary: dict[str, ArmBenchmarkDocument]
    delta: dict[str, float | None]
    iterations: NotRequired[int]
    stddev_method: NotRequired[Literal["sample"]]


type BenchmarkPayload = BenchmarkDocument | dict[Never, Never]


class IterationRecord(TypedDict):
    """Internal results retained from one completed iteration."""

    iteration_index: int
    iteration_dir: "Path"
    repeat_index: int
    arms: dict[str, ArmMetrics]
    complete: bool
    errors: tuple[str, ...]
    grading_totals: GradingTotals
    candidate_grading_totals: GradingTotals


class IterationSummaryDocument(TypedDict):
    """One iteration entry in ``summary.json``."""

    iteration_dir: str
    iteration_index: int
    repeat_index: int
    arms: dict[str, ArmMetrics]


class ExperimentSummaryDocument(TypedDict):
    """Typed ``summary.json`` payload."""

    schema_version: Literal[1]
    status: "ExperimentStatus"
    experiment_dir: str
    iterations: list[IterationSummaryDocument]
    benchmark: BenchmarkPayload
    pass_rate: float | None
    message: str | None


@dataclass(frozen=True, slots=True)
class IterationManifestData:
    """Values needed to write one iteration manifest."""

    experiment_id: str
    iteration_index: int
    iteration_dir: "Path"
    repeat_index: int
    skill_name: str
    dataset_hash: str
    bundle_hash: str
    target_model: str
    judge_model: str
    runner: str
    mode: str
    sandbox: str
    telemetry: str
    complete: bool


class IterationManifestDocument(TypedDict):
    """Typed per-iteration manifest payload."""

    schema_version: Literal[1]
    experiment_id: str
    iteration_index: int
    iteration_dir: str
    repeat_index: int
    skill_name: str
    dataset_hash: str
    evaluation_bundle_hash: str
    target_model: str
    judge_model: str
    runner: str
    mode: str
    sandbox: str
    telemetry: str
    complete: bool


@dataclass(frozen=True, slots=True)
class ExperimentManifestData:
    """Values needed to write the experiment manifest."""

    experiment_id: str
    skill_path: "Path"
    skill_name: str
    dataset_hash: str
    bundle_hash: str
    config: "ExperimentConfig"
    runner: str
    case_ids: tuple[str, ...]
    iteration_map: dict[int, str]
    status: "ExperimentStatus"
    complete: bool


class ExperimentManifestDocument(TypedDict):
    """Typed experiment manifest payload."""

    schema_version: Literal[1]
    experiment_id: str
    created_at: str
    skill_path: str
    skill_name: str
    dataset_hash: str
    evaluation_bundle_hash: str
    suite: str
    runner: str
    target_model: str
    judge_model: str
    mode: str
    baseline: str
    repeat: int
    concurrency: int
    timeout_seconds: float
    sandbox: str
    telemetry: str
    gates: dict[str, float | None]
    case_ids: list[str]
    iteration_map: dict[str, str]
    status: "ExperimentStatus"
    complete: bool


# ==================================================================================
# Filesystem helpers
# ==================================================================================


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _utc_timestamp() -> str:
    """Return the UTC timestamp used in experiment ids."""
    return _utc_now().strftime("%Y%m%dT%H%M%SZ")


def _try_create_directory(path: "Path") -> bool:
    """Create one directory and report whether this process created it."""
    try:
        path.mkdir()
    except FileExistsError:
        return False
    return True


def create_experiment_dir(experiments_root: "Path") -> tuple[str, "Path"]:
    """Atomically create a unique experiment directory.

    Args:
        experiments_root (Path):
            Directory under which experiment directories are allocated.

    Returns:
        tuple[str, Path]:
            Experiment identifier and newly created directory.

    Raises:
        RuntimeError:
            If a unique directory cannot be allocated after 20 attempts.
    """
    experiments_root.mkdir(parents=True, exist_ok=True)
    for _ in range(20):
        experiment_id = f"{_utc_timestamp()}-{secrets.token_hex(3)}"
        path = experiments_root / experiment_id
        if _try_create_directory(path):
            return experiment_id, path
    raise RuntimeError("could not allocate a unique experiment directory")


def allocate_iteration(skill_workspace: "Path") -> tuple[int, "Path"]:
    """Allocate the next free iteration directory without overwriting history.

    Args:
        skill_workspace (Path):
            Skill-specific workspace containing numbered iterations.

    Returns:
        tuple[int, Path]:
            Allocated one-based iteration index and directory.
    """
    skill_workspace.mkdir(parents=True, exist_ok=True)
    index = 1
    while True:
        path = skill_workspace / f"iteration-{index}"
        try:
            path.mkdir()
        except FileExistsError:
            index += 1
            continue
        return index, path


def copy_outputs(workspace_dir: "Path", output_dir: "Path") -> list[str]:
    """Copy the agent's ``outputs/`` tree into the artifact directory.

    Args:
        workspace_dir (Path):
            Agent workspace containing the source ``outputs/`` tree.
        output_dir (Path):
            Destination directory for preserved outputs.

    Returns:
        list[str]:
            Warnings about missing or incomplete output content.
    """
    source = workspace_dir / "outputs"
    warnings: list[str] = []
    if not source.is_dir():
        warnings.append("agent did not create an outputs/ directory")
        return warnings
    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, output_dir, dirs_exist_ok=True, symlinks=True)
    return warnings


# ==================================================================================
# Grading and timing documents
# ==================================================================================


def grading_document(
    assertions: tuple[str, ...],
    report_case: "SkillReportCase | None",
    errors: list[str] | None = None,
) -> GradingDocument:
    """Build ``grading.json`` in the official assertion order.

    Args:
        assertions (tuple[str, ...]):
            Assertion texts in official declaration order.
        report_case (SkillReportCase | None):
            Completed report case, or None when execution failed before grading.
        errors (list[str], optional):
            Infrastructure or evaluator errors to include. Defaults to an empty list.

    Returns:
        GradingDocument:
            Assertion results and aggregate grading summary.
    """
    errors = errors or []
    results = getattr(report_case, "assertions", {}) if report_case is not None else {}
    assertion_results: list[AssertionResult] = []
    passed = failed = error_count = 0

    for assertion in assertions:
        result = results.get(assertion)
        if result is None:
            error_count += 1
            assertion_results.append(
                {
                    "text": assertion,
                    "passed": None,
                    "evidence": "not graded: evaluator did not return a result",
                    "error": True,
                }
            )
            continue
        value = bool(result.value)
        evidence = result.reason or ""
        if value and not evidence.strip():
            value = False
            evidence = "empty evidence cannot be a PASS"
        if value:
            passed += 1
        else:
            failed += 1
        assertion_results.append(
            {
                "text": assertion,
                "passed": value,
                "evidence": evidence,
            }
        )

    total = len(assertions)
    graded = passed + failed
    summary: GradingSummary = {
        "passed": passed,
        "failed": failed,
        "total": total,
        "pass_rate": (passed / graded) if graded else None,
        "errors": error_count,
    }

    return {
        "assertion_results": assertion_results,
        "summary": summary,
        "errors": errors,
    }


def timing_document(
    report_case: "SkillReportCase | None",
    observation: "RunObservation | None",
) -> TimingDocument:
    """Build the official timing sidecar.

    Args:
        report_case (SkillReportCase | None):
            Report case providing task duration when available.
        observation (RunObservation | None):
            Runner observation providing token usage when available.

    Returns:
        TimingDocument:
            Token count and task duration fields in official artifact form.
    """
    usage = getattr(observation, "usage", None)
    tokens = getattr(usage, "total_tokens", None) if usage is not None else None
    duration_ms = None
    if report_case is not None:
        duration = getattr(report_case, "task_duration", None)
        if duration is not None:
            duration_ms = round(float(duration) * 1000, 3)
    return {"total_tokens": tokens, "duration_ms": duration_ms}


# ==================================================================================
# Benchmark aggregation
# ==================================================================================


def _metric(values: list[float | int]) -> MetricDocument:
    if not values:
        return {"mean": None, "stddev": None, "min": None, "max": None, "n": 0}
    numeric = [float(value) for value in values]
    return {
        "mean": mean(numeric),
        "stddev": stdev(numeric) if len(numeric) > 1 else None,
        "min": min(numeric),
        "max": max(numeric),
        "n": len(numeric),
    }


def _arm_benchmark(values: "Sequence[ArmMetrics]") -> ArmBenchmarkDocument:
    return {
        "pass_rate": _metric(
            [value["pass_rate"] for value in values if value["pass_rate"] is not None]
        ),
        "time_seconds": _metric(
            [
                value["duration_ms"] / 1000
                for value in values
                if value["duration_ms"] is not None
            ]
        ),
        "tokens": _metric(
            [
                value["total_tokens"]
                for value in values
                if value["total_tokens"] is not None
            ]
        ),
    }


def _benchmark_delta(
    run_summary: "Mapping[str, ArmBenchmarkDocument]",
) -> dict[str, float | None]:
    delta: dict[str, float | None] = {}
    if "with_skill" not in run_summary:
        return delta
    baseline_key = (
        "without_skill"
        if "without_skill" in run_summary
        else "old_skill"
        if "old_skill" in run_summary
        else None
    )
    if baseline_key:
        for metric in ("pass_rate", "time_seconds", "tokens"):
            left = run_summary["with_skill"][metric]["mean"]
            right = run_summary[baseline_key][metric]["mean"]
            delta[metric] = (
                (left - right) if left is not None and right is not None else None
            )
    return delta


def benchmark_document(arms: "Mapping[str, ArmMetrics]") -> BenchmarkDocument:
    """Build an official-shaped benchmark for one iteration.

    Args:
        arms (Mapping[str, ArmMetrics]):
            Aggregated pass rate, duration and token metrics by arm.

    Returns:
        BenchmarkDocument:
            Per-arm metric summaries and candidate-to-baseline deltas.
    """
    run_summary = {arm: _arm_benchmark([values]) for arm, values in arms.items()}
    return {"run_summary": run_summary, "delta": _benchmark_delta(run_summary)}


def aggregate_benchmarks(
    iterations: "Sequence[IterationRecord]",
) -> BenchmarkDocument:
    """Aggregate per-iteration arm metrics into the experiment sidecar.

    Args:
        iterations (Sequence[IterationRecord]):
            Completed iteration records containing per-arm metrics.

    Returns:
        BenchmarkDocument:
            Aggregated arm statistics, deltas and iteration metadata.
    """
    arm_names = sorted({arm for iteration in iterations for arm in iteration["arms"]})
    run_summary: dict[str, ArmBenchmarkDocument] = {}
    for arm in arm_names:
        values = [
            iteration["arms"][arm]
            for iteration in iterations
            if arm in iteration["arms"]
        ]
        run_summary[arm] = _arm_benchmark(values)

    return {
        "run_summary": run_summary,
        "delta": _benchmark_delta(run_summary),
        "iterations": len(iterations),
        "stddev_method": "sample",
    }


# ==================================================================================
# Manifest and summary writers
# ==================================================================================


async def write_iteration_manifest(
    path: "Path", *, data: IterationManifestData
) -> None:
    """Write the per-iteration manifest sidecar.

    Args:
        path (Path):
            Destination manifest path.
        data (IterationManifestData):
            Iteration identity, execution configuration and completion status.
    """
    document: IterationManifestDocument = {
        "schema_version": 1,
        "experiment_id": data.experiment_id,
        "iteration_index": data.iteration_index,
        "iteration_dir": str(data.iteration_dir),
        "repeat_index": data.repeat_index,
        "skill_name": data.skill_name,
        "dataset_hash": data.dataset_hash,
        "evaluation_bundle_hash": data.bundle_hash,
        "target_model": data.target_model,
        "judge_model": data.judge_model,
        "runner": data.runner,
        "mode": data.mode,
        "sandbox": data.sandbox,
        "telemetry": data.telemetry,
        "complete": data.complete,
    }
    await write_json(path, document)


async def write_experiment_manifest(
    path: "Path", *, data: ExperimentManifestData
) -> None:
    """Write the experiment manifest sidecar.

    Args:
        path (Path):
            Destination manifest path.
        data (ExperimentManifestData):
            Experiment identity, execution configuration and completion status.
    """
    config = data.config
    document: ExperimentManifestDocument = {
        "schema_version": 1,
        "experiment_id": data.experiment_id,
        "created_at": _utc_now().isoformat(),
        "skill_path": str(data.skill_path),
        "skill_name": data.skill_name,
        "dataset_hash": data.dataset_hash,
        "evaluation_bundle_hash": data.bundle_hash,
        "suite": config.suite,
        "runner": data.runner,
        "target_model": config.target_model,
        "judge_model": config.judge_model or config.target_model,
        "mode": config.mode,
        "baseline": config.baseline.mode,
        "repeat": config.repeat,
        "concurrency": config.concurrency,
        "timeout_seconds": config.timeout_seconds,
        "sandbox": config.sandbox.kind,
        "telemetry": config.telemetry.kind,
        "gates": config.gates.model_dump(mode="json"),
        "case_ids": list(data.case_ids),
        "iteration_map": {
            str(key): value for key, value in sorted(data.iteration_map.items())
        },
        "status": data.status,
        "complete": data.complete,
    }
    await write_json(path, document)


async def write_experiment_summary(
    path: "Path",
    *,
    status: "ExperimentStatus",
    experiment_dir: "Path",
    iterations: "Sequence[IterationRecord]",
    benchmark: BenchmarkPayload,
    pass_rate: float | None,
    message: str | None,
) -> None:
    """Write the experiment summary and iteration aggregation.

    Args:
        path (Path):
            Destination summary path.
        status (ExperimentStatus):
            Final experiment status.
        experiment_dir (Path):
            Root directory of the experiment.
        iterations (Sequence[IterationRecord]):
            Completed iteration records to summarize.
        benchmark (BenchmarkPayload):
            Aggregated benchmark document, or an empty object when incomplete.
        pass_rate (float | None):
            Candidate assertion pass rate, or None when ungraded.
        message (str | None):
            Combined error or gate message, if present.
    """
    iteration_documents: list[IterationSummaryDocument] = [
        {
            "iteration_dir": str(item["iteration_dir"]),
            "iteration_index": item["iteration_index"],
            "repeat_index": item["repeat_index"],
            "arms": item["arms"],
        }
        for item in iterations
    ]
    document: ExperimentSummaryDocument = {
        "schema_version": 1,
        "status": status,
        "experiment_dir": str(experiment_dir),
        "iterations": iteration_documents,
        "benchmark": benchmark,
        "pass_rate": pass_rate,
        "message": message,
    }
    await write_json(path, document)
