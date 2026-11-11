"""Public Python API for validation, evaluation and experiment comparison."""

import shutil
import statistics
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

import anyio
from httpx2 import TransportError
from pydantic_ai.exceptions import ModelConnectionError
from pydantic_evals import Case, Dataset
from pydantic_evals.reporting import EvaluationReportAdapter

from skill_eval._artifacts import (
    ArmMetrics,
    BenchmarkPayload,
    ExperimentManifestData,
    GradingTotals,
    IterationManifestData,
    IterationRecord,
    TimingDocument,
    aggregate_benchmarks,
    allocate_iteration,
    benchmark_document,
    copy_outputs,
    create_experiment_dir,
    grading_document,
    timing_document,
    write_experiment_manifest,
    write_experiment_summary,
    write_iteration_manifest,
)
from skill_eval._comparison import compare_experiments
from skill_eval._config import (
    load_skill_eval_config,
    read_baseline_skill_name,
    read_skill_name,
    validate_check_bindings,
    validate_trigger_config,
)
from skill_eval._config import validate_skill as _validate_skill
from skill_eval._datasets import (
    EvalEntry,
    copy_evaluation_bundle,
    dataset_hash,
    eval_dir_name,
    hash_tree,
    load_eval_dataset,
    load_eval_file,
)
from skill_eval._helpers import run_in_thread, to_slug, write_json
from skill_eval._workspaces import (
    EvaluationLifecycle,
    reset_case_workspace,
    snapshot_skill,
)
from skill_eval.evaluators import EvidenceJudge, FileExists, SkillTrigger, VerifyCommand
from skill_eval.exceptions import ConfigError
from skill_eval.models import (
    Arm,
    ExperimentConfig,
    ExperimentResult,
    ExperimentStatus,
    RunObservation,
    RunRequest,
    SkillCaseInput,
    SkillCaseMetadata,
    SkillDeployment,
    SkillEvaluationReport,
    SkillEvalYaml,
    TriggerCase,
    ValidationResult,
)
from skill_eval.runners._base import SkillRunner, create_runner

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pydantic_evals.evaluators import Evaluator

    from skill_eval._datasets import EvalFile

__all__ = [
    "compare_experiments",
    "evaluate_skill",
    "load_eval_dataset",
    "validate_skill",
]

type _ArmSource = tuple[Arm, Path | None, str | None]
type _SkillCaseTask = Callable[[SkillCaseInput], Awaitable[RunObservation]]
type _RetryReset = Callable[[], Awaitable[None]]
type _IterationResult = tuple[IterationRecord, SkillEvaluationReport]


# ==================================================================================
# Validation and preparation
# ==================================================================================


def validate_skill(
    skill_path: Path, config_path: Path | None = None
) -> ValidationResult:
    """Validate a skill package without calling a model.

    Args:
        skill_path (Path):
            Skill directory to validate.
        config_path (Path, optional):
            External evaluation configuration. Defaults to the skill's config.

    Returns:
        ValidationResult:
            Validation status, skill identity, errors and warnings.
    """
    return _validate_skill(Path(skill_path), config_path)


@dataclass(frozen=True, slots=True)
class _PreparedExperiment:
    """Validated inputs and execution settings for one experiment."""

    skill_path: Path
    source_skill_path: Path
    skill_name: str
    runner: SkillRunner
    runner_name: str
    official: "EvalFile"
    skill_config: SkillEvalYaml
    selected: tuple[EvalEntry, ...]
    trigger_cases: tuple[TriggerCase, ...]
    case_ids: tuple[str, ...]
    baseline_path: Path | None
    baseline_name: str | None


@dataclass(frozen=True, slots=True)
class _IterationContext:
    """Execution inputs shared by all cases in one iteration."""

    config: ExperimentConfig
    prepared: _PreparedExperiment
    experiment_id: str
    iteration_index: int
    iteration_dir: Path
    repeat_index: int
    bundle_root: Path
    bundle_hash: str
    dataset_hash_value: str
    judge_model: str


@dataclass(frozen=True, slots=True)
class _IterationBatch:
    """Aggregated results from every repeat in one experiment."""

    iteration_dirs: tuple[Path, ...]
    reports: tuple[SkillEvaluationReport, ...]
    records: tuple[IterationRecord, ...]
    all_errors: tuple[str, ...]
    candidate_passed: int
    candidate_failed: int
    total_errors: int


@dataclass(frozen=True, slots=True)
class _GradingSummary:
    """Per-case error list and grading totals from one iteration report."""

    errors: tuple[str, ...]
    grading_totals: GradingTotals
    candidate_grading_totals: GradingTotals
    arm_metrics: dict[str, list[ArmMetrics]]


@dataclass(frozen=True, slots=True)
class _CaseSpec:
    """One dataset case with the assertions its grading document reports."""

    case_name: str
    arm: Arm
    inputs: SkillCaseInput
    assertions: tuple[str, ...]


def _read_runner_name(runner: SkillRunner) -> str:
    return runner.info.name


async def _validate_experiment(
    config: ExperimentConfig,
    skill_path: Path,
    runner: SkillRunner | None,
) -> tuple[str, SkillRunner, str]:
    """Validate the package and resolve the runner for one experiment."""
    validation = await run_in_thread(validate_skill, skill_path, _config_path(config))
    if not validation.ok:
        raise ConfigError("; ".join(validation.errors))
    skill_name = validation.skill_name or await run_in_thread(
        read_skill_name, skill_path
    )

    if config.sandbox.kind == "docker":
        raise ConfigError(
            "the Docker sandbox is not implemented in the MVP; "
            "use --sandbox local for a trusted skill"
        )
    if config.mode == "forced":
        raise ConfigError(
            "the pydantic-ai runner does not support forced skill invocation"
        )
    if config.telemetry.kind != "local":
        raise ConfigError(
            "OTel/Logfire telemetry is not implemented in the MVP; "
            "use --telemetry local"
        )

    resolved_runner = runner or _create_runner(config.runner)
    runner_name = await run_in_thread(_read_runner_name, resolved_runner)
    if not resolved_runner.capabilities.auto_invocation:
        raise ConfigError(
            f"runner {runner_name!r} does not support automatic skill invocation"
        )
    if config.mode == "forced" and not resolved_runner.capabilities.forced_invocation:
        raise ConfigError(
            f"runner {runner_name!r} does not support forced skill invocation"
        )
    return skill_name, resolved_runner, runner_name


async def _load_experiment_inputs(
    config: ExperimentConfig, skill_path: Path
) -> tuple["EvalFile", SkillEvalYaml]:
    """Load the eval file and skill configuration, then validate bindings."""
    official = await run_in_thread(load_eval_file, skill_path)
    skill_config = await run_in_thread(
        load_skill_eval_config, skill_path, _config_path(config)
    )
    binding_errors = await run_in_thread(
        validate_check_bindings, official, skill_config, skill_path
    )
    trigger_errors = await run_in_thread(
        validate_trigger_config, skill_config, skill_path
    )
    if binding_errors or trigger_errors:
        raise ConfigError("; ".join(binding_errors + trigger_errors))
    return official, skill_config


def _select_suite(
    config: ExperimentConfig,
    skill_config: SkillEvalYaml,
    official: "EvalFile",
) -> tuple[tuple[EvalEntry, ...], tuple[TriggerCase, ...]]:
    """Select output-quality evals or trigger cases for the configured suite."""
    if config.suite == "trigger":
        if skill_config.trigger is None:
            raise ConfigError("trigger suite requires trigger.cases in skill-eval.yaml")
        return (), _select_trigger_cases(skill_config.trigger.cases, config.case_ids)
    selected = _select_evals(official.evals, config.case_ids)
    if not selected:
        raise ConfigError("no eval cases selected")
    if config.gates.max_regression is not None and config.baseline.mode == "none":
        raise ConfigError("max_regression requires a comparison baseline")
    return selected, ()


async def _resolve_baseline(
    config: ExperimentConfig,
) -> tuple[Path | None, str | None]:
    """Resolve the optional skill baseline and its declared name."""
    if config.baseline.mode != "skill":
        return None, None
    baseline_setting = config.baseline.skill_path
    if baseline_setting is None:
        raise ConfigError("baseline.mode=skill requires baseline.skill_path")
    baseline_path = await run_in_thread(baseline_setting.resolve)
    if not await run_in_thread(baseline_path.is_dir):
        raise ConfigError(f"baseline skill path is not a directory: {baseline_path}")
    baseline_name = await run_in_thread(read_baseline_skill_name, baseline_path)
    return baseline_path, baseline_name


async def _prepare_experiment(
    config: ExperimentConfig, runner: SkillRunner | None
) -> _PreparedExperiment:
    """Validate and load every input needed before running an experiment."""
    skill_path = await run_in_thread(config.skill_path.resolve)
    skill_name, resolved_runner, runner_name = await _validate_experiment(
        config, skill_path, runner
    )
    official, skill_config = await _load_experiment_inputs(config, skill_path)
    selected, trigger_cases = _select_suite(config, skill_config, official)
    baseline_path, baseline_name = await _resolve_baseline(config)
    selected_items = trigger_cases if config.suite == "trigger" else selected
    return _PreparedExperiment(
        skill_path=skill_path,
        source_skill_path=skill_path,
        skill_name=skill_name,
        runner=resolved_runner,
        runner_name=runner_name,
        official=official,
        skill_config=skill_config,
        selected=selected,
        trigger_cases=trigger_cases,
        case_ids=tuple(item.id for item in selected_items),
        baseline_path=baseline_path,
        baseline_name=baseline_name,
    )


def _validate_workspace_containment(
    workspace: Path, sources: tuple[Path | None, ...]
) -> None:
    """Reject workspaces nested with any candidate or baseline source."""
    for source in sources:
        if source is None:
            continue
        if (
            workspace == source
            or workspace in source.parents
            or source in workspace.parents
        ):
            raise ConfigError(
                "workspace must not contain or be contained by a skill source: "
                f"{workspace} and {source}"
            )


async def _snapshot_experiment_inputs(
    config: ExperimentConfig,
    prepared: _PreparedExperiment,
    experiment_dir: Path,
) -> tuple[ExperimentConfig, _PreparedExperiment]:
    """Freeze every skill and external config before hashing or execution."""
    inputs_root = experiment_dir / "inputs"
    candidate_snapshot = inputs_root / "candidate" / prepared.skill_name
    await run_in_thread(snapshot_skill, prepared.skill_path, candidate_snapshot)

    baseline_snapshot: Path | None = None
    if prepared.baseline_path is not None and prepared.baseline_name is not None:
        baseline_snapshot = inputs_root / "baseline" / prepared.baseline_name
        await run_in_thread(snapshot_skill, prepared.baseline_path, baseline_snapshot)

    config_snapshot: Path | None = None
    if config.config_path is not None:
        config_snapshot = inputs_root / "external-skill-eval.yaml"
        await run_in_thread(shutil.copy2, config.config_path, config_snapshot)

    baseline_config = config.baseline.model_copy(
        update={"skill_path": baseline_snapshot}
    )
    snapshot_config = config.model_copy(
        update={
            "skill_path": candidate_snapshot,
            "baseline": baseline_config,
            "config_path": config_snapshot,
        }
    )
    snapshot_prepared = await _prepare_experiment(snapshot_config, prepared.runner)
    return snapshot_config, replace(
        snapshot_prepared, source_skill_path=prepared.source_skill_path
    )


# ==================================================================================
# Iteration execution
# ==================================================================================


async def _run_iterations(
    *,
    config: ExperimentConfig,
    prepared: _PreparedExperiment,
    experiment_id: str,
    workspace_root: Path,
    bundle_root: Path,
    bundle_hash: str,
    dataset_hash_value: str,
) -> _IterationBatch:
    """Run every repeat and aggregate its report and grading totals."""
    iteration_dirs: list[Path] = []
    reports: list[SkillEvaluationReport] = []
    records: list[IterationRecord] = []
    all_errors: list[str] = []
    candidate_passed = candidate_failed = total_errors = 0

    for repeat_index in range(1, config.repeat + 1):
        iteration_index, iteration_dir = await run_in_thread(
            allocate_iteration,
            workspace_root / "workspaces" / to_slug(prepared.skill_name),
        )
        iteration_dirs.append(iteration_dir)
        context = _IterationContext(
            config=config,
            prepared=prepared,
            experiment_id=experiment_id,
            iteration_index=iteration_index,
            iteration_dir=iteration_dir,
            repeat_index=repeat_index,
            bundle_root=bundle_root,
            bundle_hash=bundle_hash,
            dataset_hash_value=dataset_hash_value,
            judge_model=config.judge_model or config.target_model,
        )
        if config.suite == "trigger":
            record, report = await _run_trigger_iteration(context)
        else:
            record, report = await _run_output_quality_iteration(context)
        reports.append(report)
        records.append(record)
        all_errors.extend(record["errors"])
        grading = record["candidate_grading_totals"]
        candidate_passed += grading["passed"]
        candidate_failed += grading["failed"]
        total_errors += record["grading_totals"]["errors"]

    return _IterationBatch(
        iteration_dirs=tuple(iteration_dirs),
        reports=tuple(reports),
        records=tuple(records),
        all_errors=tuple(all_errors),
        candidate_passed=candidate_passed,
        candidate_failed=candidate_failed,
        total_errors=total_errors,
    )


def _unavailable_gate_errors(config: ExperimentConfig, *, reason: str) -> list[str]:
    """Describe configured gates that cannot apply to this experiment's suite."""
    configured = [("min_pass_rate", config.gates.min_pass_rate is not None)]
    if config.suite == "output-quality":
        configured.append(("max_regression", config.gates.max_regression is not None))
    return [
        f"{name} gate could not be evaluated because {reason}"
        for name, enabled in configured
        if enabled
    ]


def _evaluate_experiment_status(
    config: ExperimentConfig,
    batch: _IterationBatch,
    benchmark: BenchmarkPayload,
    *,
    complete: bool,
    pass_rate: float | None,
) -> tuple[ExperimentStatus, list[str]]:
    """Apply completion and quality gates, returning status and gate errors."""
    errors: list[str] = []
    if not complete or batch.total_errors:
        return "error", errors
    if pass_rate is None:
        gate_errors = _unavailable_gate_errors(
            config, reason="the experiment has no graded assertions"
        )
        if gate_errors:
            return "error", gate_errors
        return "ungraded", errors

    status: ExperimentStatus = "passed"
    minimum = (
        config.gates.min_pass_rate if config.gates.min_pass_rate is not None else 1.0
    )
    if pass_rate < minimum:
        status = "failed"
        if config.gates.min_pass_rate is not None:
            errors.append(f"pass rate {pass_rate:.3f} is below gate {minimum:.3f}")

    max_regression = config.gates.max_regression
    if config.suite == "output-quality" and max_regression is not None:
        regression = benchmark.get("delta", {}).get("pass_rate")
        if regression is None:
            status = "error"
            errors.append("pass rate regression gate could not be evaluated")
        elif regression < -max_regression:
            status = "failed"
            errors.append(
                f"pass rate regression {-regression:.3f} exceeds gate "
                f"{max_regression:.3f}"
            )
    return status, errors


async def _write_experiment_result(
    *,
    config: ExperimentConfig,
    prepared: _PreparedExperiment,
    experiment_id: str,
    experiment_dir: Path,
    batch: _IterationBatch,
    complete: bool,
    status: ExperimentStatus,
    pass_rate: float | None,
    benchmark: BenchmarkPayload,
    dataset_hash_value: str,
    bundle_hash: str,
    all_errors: list[str],
) -> ExperimentResult:
    """Write benchmark, manifest and summary artifacts, then return the result."""
    if complete:
        await write_json(experiment_dir / "benchmark.json", benchmark)

    iteration_map = {
        item["repeat_index"]: str(item["iteration_dir"]) for item in batch.records
    }
    await write_experiment_manifest(
        experiment_dir / "manifest.json",
        data=ExperimentManifestData(
            experiment_id=experiment_id,
            skill_path=prepared.source_skill_path,
            skill_name=prepared.skill_name,
            dataset_hash=dataset_hash_value,
            bundle_hash=bundle_hash,
            config=config,
            runner=prepared.runner_name,
            case_ids=prepared.case_ids,
            iteration_map=iteration_map,
            status=status,
            complete=complete,
        ),
    )
    await write_experiment_summary(
        experiment_dir / "summary.json",
        status=status,
        experiment_dir=experiment_dir,
        iterations=batch.records,
        benchmark=benchmark,
        pass_rate=pass_rate,
        message="; ".join(all_errors) if all_errors else None,
    )
    return ExperimentResult(
        status=status,
        experiment_dir=experiment_dir,
        iteration_dirs=batch.iteration_dirs,
        reports=batch.reports,
        artifacts={
            "manifest": experiment_dir / "manifest.json",
            "summary": experiment_dir / "summary.json",
            **({"benchmark": experiment_dir / "benchmark.json"} if complete else {}),
        },
        message="; ".join(all_errors) if all_errors else None,
        pass_rate=pass_rate,
    )


async def evaluate_skill(
    config: ExperimentConfig,
    *,
    runner: SkillRunner | None = None,
) -> ExperimentResult:
    """Run one output-quality or trigger experiment.

    Args:
        config (ExperimentConfig):
            Fully validated experiment configuration.
        runner (SkillRunner, optional):
            Runner override for testing or custom execution. Defaults to the
            registered runner.

    Returns:
        ExperimentResult:
            Experiment status, reports and artifact locations.

    Raises:
        ConfigError:
            If configuration, capability or case selection is invalid.
    """
    prepared = await _prepare_experiment(config, runner)
    workspace_root = await run_in_thread(config.workspace.resolve)
    _validate_workspace_containment(
        workspace_root, (prepared.skill_path, prepared.baseline_path)
    )
    experiment_id, experiment_dir = await run_in_thread(
        create_experiment_dir, workspace_root / "experiments"
    )
    config, prepared = await _snapshot_experiment_inputs(
        config, prepared, experiment_dir
    )
    bundle = await run_in_thread(
        copy_evaluation_bundle,
        prepared.skill_path,
        experiment_dir / "evaluation-bundle",
        _config_path(config),
    )
    dataset_hash_value = await run_in_thread(
        dataset_hash, prepared.skill_path, prepared.official, prepared.skill_config
    )
    batch = await _run_iterations(
        config=config,
        prepared=prepared,
        experiment_id=experiment_id,
        workspace_root=workspace_root,
        bundle_root=bundle.root,
        bundle_hash=bundle.content_hash,
        dataset_hash_value=dataset_hash_value,
    )
    complete = len(batch.records) == config.repeat and all(
        item["complete"] for item in batch.records
    )
    pass_rate = (
        batch.candidate_passed / (batch.candidate_passed + batch.candidate_failed)
        if batch.candidate_passed + batch.candidate_failed
        else None
    )
    benchmark: BenchmarkPayload = (
        aggregate_benchmarks(batch.records) if complete else {}
    )
    status, gate_errors = _evaluate_experiment_status(
        config,
        batch,
        benchmark,
        complete=complete,
        pass_rate=pass_rate,
    )
    all_errors = [*batch.all_errors, *gate_errors]
    return await _write_experiment_result(
        config=config,
        prepared=prepared,
        experiment_id=experiment_id,
        experiment_dir=experiment_dir,
        batch=batch,
        complete=complete,
        status=status,
        pass_rate=pass_rate,
        benchmark=benchmark,
        dataset_hash_value=dataset_hash_value,
        bundle_hash=bundle.content_hash,
        all_errors=all_errors,
    )


# ==================================================================================
# Output-quality suite
# ==================================================================================


def _output_quality_arms(context: _IterationContext) -> tuple[_ArmSource, ...]:
    """Build the candidate and optional baseline arms."""
    config = context.config
    prepared = context.prepared
    arms: tuple[_ArmSource, ...] = (
        ("with_skill", prepared.skill_path, prepared.skill_name),
    )
    if config.baseline.mode == "no-skill":
        arms += (("without_skill", None, None),)
    elif config.baseline.mode == "skill":
        if prepared.baseline_path is None or prepared.baseline_name is None:
            raise ConfigError("baseline skill deployment is incomplete")
        arms += (("old_skill", prepared.baseline_path, prepared.baseline_name),)
    return arms


def _build_output_quality_cases(
    context: _IterationContext, *, arms: tuple[_ArmSource, ...]
) -> tuple[
    list[Case[SkillCaseInput, RunObservation, SkillCaseMetadata]],
    list[_CaseSpec],
]:
    """Build dataset cases and grading specs for every eval and arm."""
    config = context.config
    prepared = context.prepared
    cases: list[Case[SkillCaseInput, RunObservation, SkillCaseMetadata]] = []
    specs: list[_CaseSpec] = []
    used_names: set[str] = set()
    for item in prepared.selected:
        item_dir = eval_dir_name(item.id, used_names)
        checks = tuple(
            check for check in prepared.skill_config.checks if check.case == item.id
        )
        covered = {check.assertion for check in checks}
        uncovered = tuple(
            assertion for assertion in item.assertions if assertion not in covered
        )
        for arm, source_path, source_name in arms:
            case_root = context.iteration_dir / item_dir / arm
            workspace_dir = context.iteration_dir / ".work" / item_dir / arm
            output_dir = case_root / "outputs"
            evidence_dir = case_root / "evidence"
            inputs = SkillCaseInput(
                case_id=item.id,
                prompt=item.prompt,
                fixture_files=item.files,
                arm=arm,
                workspace_dir=workspace_dir,
                output_dir=output_dir,
                raw_evidence_dir=evidence_dir,
                skill_source_path=source_path,
                fixture_source_root=prepared.skill_path,
                skill_name=source_name,
                target_model=config.target_model,
                judge_model=context.judge_model,
                mode=config.mode,
                timeout_seconds=config.timeout_seconds,
            )
            metadata = SkillCaseMetadata(
                eval_id=item.id,
                eval_dir_name=item_dir,
                expected_output=item.expected_output,
                assertions=item.assertions,
                arm=arm,
                checks=checks,
                bundle_dir=context.bundle_root,
                skill_name=source_name,
                repeat_index=context.repeat_index,
            )
            evaluators: list[
                Evaluator[SkillCaseInput, RunObservation, SkillCaseMetadata]
            ] = []
            if any(check.type == "file_exists" for check in checks):
                evaluators.append(FileExists(checks=checks))
            if any(check.type == "command" for check in checks):
                evaluators.append(
                    VerifyCommand(
                        checks=checks,
                        bundle_dir=context.bundle_root,
                        case_id=item.id,
                        arm=arm,
                    )
                )
            if uncovered:
                evaluators.append(
                    EvidenceJudge(
                        assertions=uncovered,
                        judge_model=context.judge_model,
                        expected_output=metadata.expected_output,
                        timeout_seconds=config.timeout_seconds,
                    )
                )
            case_name = f"{item_dir}/{arm}"
            cases.append(
                Case[SkillCaseInput, RunObservation, SkillCaseMetadata](
                    name=case_name,
                    inputs=inputs,
                    expected_output=None,
                    metadata=metadata,
                    evaluators=tuple(evaluators),
                )
            )
            specs.append(
                _CaseSpec(
                    case_name=case_name,
                    arm=arm,
                    inputs=inputs,
                    assertions=item.assertions,
                )
            )
    return cases, specs


async def _collect_case_metrics(
    *,
    specs: list[_CaseSpec],
    report: SkillEvaluationReport,
) -> _GradingSummary:
    """Write per-case artifacts and aggregate grading totals for one report."""
    by_name = {case.name: case for case in report.cases}
    failures = {failure.name: failure for failure in report.failures}
    errors: list[str] = []
    grading_totals: GradingTotals = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "total": 0,
    }
    candidate_grading_totals: GradingTotals = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "total": 0,
    }
    arm_metrics: dict[str, list[ArmMetrics]] = defaultdict(list)
    for spec in specs:
        report_case = by_name.get(spec.case_name)
        case_errors: list[str] = []
        if spec.case_name in failures:
            case_errors.append(
                f"{spec.case_name}: {failures[spec.case_name].error_message}"
            )
        if report_case is not None:
            case_errors.extend(
                f"{spec.case_name}/{failure.name}: {failure.error_message}"
                for failure in report_case.evaluator_failures
            )
        errors.extend(case_errors)
        observation = report_case.output if report_case is not None else None
        grading = grading_document(spec.assertions, report_case, case_errors)
        await write_json(spec.inputs.output_dir.parent / "grading.json", grading)
        if observation is not None:
            await write_json(
                spec.inputs.output_dir.parent / "skill-eval-run.json",
                observation.model_dump(mode="json"),
            )
            timing = timing_document(report_case, observation)
        else:
            timing: TimingDocument = {"total_tokens": None, "duration_ms": None}
        await write_json(spec.inputs.output_dir.parent / "timing.json", timing)
        summary = grading["summary"]
        grading_totals["passed"] += summary["passed"]
        grading_totals["failed"] += summary["failed"]
        grading_totals["errors"] += summary["errors"]
        grading_totals["total"] += summary["total"]
        if spec.arm == "with_skill":
            candidate_grading_totals["passed"] += summary["passed"]
            candidate_grading_totals["failed"] += summary["failed"]
            candidate_grading_totals["errors"] += summary["errors"]
            candidate_grading_totals["total"] += summary["total"]
        arm_metrics[spec.arm].append(
            {
                "pass_rate": summary["pass_rate"],
                "duration_ms": timing["duration_ms"],
                "total_tokens": timing["total_tokens"],
            }
        )
    return _GradingSummary(
        errors=tuple(errors),
        grading_totals=grading_totals,
        candidate_grading_totals=candidate_grading_totals,
        arm_metrics=arm_metrics,
    )


async def _run_output_quality_iteration(
    context: _IterationContext,
) -> _IterationResult:
    """Run one output-quality iteration and write its artifacts."""
    config = context.config
    prepared = context.prepared
    arms = _output_quality_arms(context)
    cases, specs = _build_output_quality_cases(context, arms=arms)
    report = await Dataset[SkillCaseInput, RunObservation, SkillCaseMetadata](
        name=f"{prepared.skill_name}-iteration-{context.iteration_index}", cases=cases
    ).evaluate(
        _task(prepared.runner, config, context.repeat_index),
        max_concurrency=config.concurrency,
        progress=False,
        lifecycle=EvaluationLifecycle,
        task_timeout=config.timeout_seconds,
    )
    summary = await _collect_case_metrics(specs=specs, report=report)
    return await _finish_iteration(
        context, report=report, summary=summary, expected_cases=len(specs)
    )


async def _finish_iteration(
    context: _IterationContext,
    *,
    report: SkillEvaluationReport,
    summary: _GradingSummary,
    expected_cases: int,
) -> _IterationResult:
    """Write iteration-level artifacts and build the iteration record."""
    config = context.config
    prepared = context.prepared
    arms_summary = _arm_averages(summary.arm_metrics)
    benchmark = benchmark_document(arms_summary)
    await write_json(context.iteration_dir / "benchmark.json", benchmark)
    await write_json(
        context.iteration_dir / "pydantic-report.json", _report_json(report)
    )
    complete = (
        not summary.errors
        and len(report.cases) == expected_cases
        and not report.failures
    )
    await write_iteration_manifest(
        context.iteration_dir / "skill-eval-manifest.json",
        data=IterationManifestData(
            experiment_id=context.experiment_id,
            iteration_index=context.iteration_index,
            iteration_dir=context.iteration_dir,
            repeat_index=context.repeat_index,
            skill_name=prepared.skill_name,
            dataset_hash=context.dataset_hash_value,
            bundle_hash=context.bundle_hash,
            target_model=config.target_model,
            judge_model=context.judge_model,
            runner=prepared.runner_name,
            mode=config.mode,
            sandbox=config.sandbox.kind,
            telemetry=config.telemetry.kind,
            complete=complete,
        ),
    )
    record: IterationRecord = {
        "iteration_index": context.iteration_index,
        "iteration_dir": context.iteration_dir,
        "repeat_index": context.repeat_index,
        "arms": arms_summary,
        "complete": complete,
        "errors": summary.errors,
        "grading_totals": summary.grading_totals,
        "candidate_grading_totals": summary.candidate_grading_totals,
    }
    return record, report


# ==================================================================================
# Trigger suite
# ==================================================================================


async def _run_trigger_iteration(context: _IterationContext) -> _IterationResult:
    """Run one trigger iteration and write its artifacts."""
    config = context.config
    prepared = context.prepared
    cases: list[Case[SkillCaseInput, RunObservation, SkillCaseMetadata]] = []
    specs: list[_CaseSpec] = []
    used_names: set[str] = set()
    for item in prepared.trigger_cases:
        item_dir = eval_dir_name(item.id, used_names)
        case_root = context.iteration_dir / item_dir
        workspace_dir = context.iteration_dir / ".work" / item_dir
        output_dir = case_root / "outputs"
        evidence_dir = case_root / "evidence"
        inputs = SkillCaseInput(
            case_id=item.id,
            prompt=item.prompt,
            fixture_files=item.files,
            arm="with_skill",
            workspace_dir=workspace_dir,
            output_dir=output_dir,
            raw_evidence_dir=evidence_dir,
            skill_source_path=prepared.skill_path,
            fixture_source_root=prepared.skill_path,
            skill_name=prepared.skill_name,
            target_model=config.target_model,
            judge_model=context.judge_model,
            mode=config.mode,
            timeout_seconds=config.timeout_seconds,
        )
        metadata = SkillCaseMetadata(
            eval_id=item.id,
            eval_dir_name=item_dir,
            expected_output="",
            assertions=(),
            arm="with_skill",
            should_trigger=item.should_trigger,
            bundle_dir=context.bundle_root,
            skill_name=prepared.skill_name,
            repeat_index=context.repeat_index,
        )
        case_name = item_dir
        cases.append(
            Case[SkillCaseInput, RunObservation, SkillCaseMetadata](
                name=case_name,
                inputs=inputs,
                metadata=metadata,
                evaluators=[
                    SkillTrigger(
                        skill_name=prepared.skill_name,
                        should_trigger=item.should_trigger,
                    )
                ],
            )
        )
        specs.append(
            _CaseSpec(
                case_name=case_name,
                arm="with_skill",
                inputs=inputs,
                assertions=("trigger",),
            )
        )

    report = await Dataset[SkillCaseInput, RunObservation, SkillCaseMetadata](
        name=f"{prepared.skill_name}-trigger-{context.iteration_index}", cases=cases
    ).evaluate(
        _task(prepared.runner, config, context.repeat_index),
        max_concurrency=config.concurrency,
        progress=False,
        lifecycle=EvaluationLifecycle,
        task_timeout=config.timeout_seconds,
    )
    summary = await _collect_case_metrics(specs=specs, report=report)
    return await _finish_iteration(
        context, report=report, summary=summary, expected_cases=len(specs)
    )


# ==================================================================================
# Shared execution helpers
# ==================================================================================


def _task(
    runner: SkillRunner,
    config: ExperimentConfig,
    repeat_index: int,
) -> _SkillCaseTask:
    async def _run_case(inputs: SkillCaseInput) -> RunObservation:
        deployment = None
        if inputs.skill_source_path is not None and inputs.skill_name:
            deployment = SkillDeployment(
                name=inputs.skill_name,
                snapshot_path=inputs.skill_source_path,
                content_hash=await run_in_thread(hash_tree, inputs.skill_source_path),
            )

        request = RunRequest(
            run_id=f"{inputs.case_id}-{inputs.arm}-{repeat_index}",
            case_id=inputs.case_id,
            repeat_index=repeat_index,
            arm=inputs.arm,
            prompt=inputs.prompt,
            fixture_files=tuple(
                inputs.workspace_dir / fixture for fixture in inputs.fixture_files
            ),
            skill=deployment,
            invocation=inputs.mode,
            workspace_dir=inputs.workspace_dir,
            output_dir=inputs.output_dir,
            raw_evidence_dir=inputs.raw_evidence_dir,
            target_model=config.target_model,
            model_settings={},
            timeout_seconds=config.timeout_seconds,
        )

        async def _reset_attempt() -> None:
            await reset_case_workspace(inputs)

        observation = await _run_with_transient_retry(
            runner, request, on_retry=_reset_attempt
        )
        warnings = await run_in_thread(
            copy_outputs, inputs.workspace_dir, inputs.output_dir
        )
        if warnings:
            observation = observation.model_copy(
                update={"warnings": [*observation.warnings, *warnings]}
            )

        return observation

    return _run_case


async def _run_with_transient_retry(
    runner: SkillRunner, request: RunRequest, *, on_retry: _RetryReset
) -> RunObservation:
    """Retry transient failures after resetting every run-owned path."""
    last_error: Exception | None = None
    for attempt in range(2):
        if attempt:
            await on_retry()
        try:
            return await runner.run(request)
        except (
            ConnectionError,
            TimeoutError,
            TransportError,
            ModelConnectionError,
        ) as err:
            last_error = err
            if attempt == 0:
                await anyio.sleep(0.1)
    if last_error is None:
        raise RuntimeError("retry loop ended without an error or result")
    raise last_error


def _arm_averages(
    metrics: dict[str, list[ArmMetrics]],
) -> dict[str, ArmMetrics]:
    result: dict[str, ArmMetrics] = {}
    for arm, values in metrics.items():
        pass_rates = [
            value["pass_rate"] for value in values if value["pass_rate"] is not None
        ]
        durations = [
            value["duration_ms"] for value in values if value["duration_ms"] is not None
        ]
        tokens = [
            value["total_tokens"]
            for value in values
            if value["total_tokens"] is not None
        ]
        result[arm] = {
            "pass_rate": statistics.mean(pass_rates) if pass_rates else None,
            "duration_ms": statistics.mean(durations) if durations else None,
            "total_tokens": statistics.mean(tokens) if tokens else None,
        }
    return result


def _report_json(report: SkillEvaluationReport) -> object:
    return EvaluationReportAdapter.dump_python(report, mode="json")


def _select_evals(
    evals: tuple[EvalEntry, ...], case_ids: tuple[str, ...]
) -> tuple[EvalEntry, ...]:
    if not case_ids:
        return evals
    selected_ids = {str(case_id) for case_id in case_ids}
    known = {item.id for item in evals}
    unknown = selected_ids - known
    if unknown:
        raise ConfigError(f"unknown eval case ids: {', '.join(sorted(unknown))}")
    return tuple(item for item in evals if item.id in selected_ids)


def _select_trigger_cases(
    cases: tuple[TriggerCase, ...], case_ids: tuple[str, ...]
) -> tuple[TriggerCase, ...]:
    if not case_ids:
        return cases
    selected_ids = set(case_ids)
    known = {item.id for item in cases}
    unknown = selected_ids - known
    if unknown:
        raise ConfigError(f"unknown trigger case ids: {', '.join(sorted(unknown))}")
    return tuple(item for item in cases if item.id in selected_ids)


def _create_runner(name: str) -> SkillRunner:
    try:
        return create_runner(name)
    except ValueError as err:
        raise ConfigError(str(err)) from err


def _config_path(config: ExperimentConfig) -> Path | None:
    return config.config_path
