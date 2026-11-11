"""Compare two experiment directories and apply their quality gates."""

from typing import TYPE_CHECKING

from skill_eval._helpers import read_json_model
from skill_eval.models import (
    ComparisonResult,
    ExperimentManifest,
    ExperimentStatus,
    ExperimentSummary,
    GateConfig,
)

if TYPE_CHECKING:
    from pathlib import Path

    from skill_eval.models import ArmBenchmark

__all__ = ["compare_experiments"]


# ==================================================================================
# Experiment comparison
# ==================================================================================


def _comparison_delta(
    *,
    comparable: bool,
    candidate: "ArmBenchmark | None",
    baseline: "ArmBenchmark | None",
) -> dict[str, float | None]:
    """Return numeric deltas only for compatible experiment manifests."""
    delta: dict[str, float | None] = {
        "pass_rate": None,
        "time_seconds": None,
        "tokens": None,
    }
    if not comparable:
        return delta
    candidate_rate = candidate.pass_rate.mean if candidate is not None else None
    baseline_rate = baseline.pass_rate.mean if baseline is not None else None
    delta["pass_rate"] = (
        candidate_rate - baseline_rate
        if candidate_rate is not None and baseline_rate is not None
        else None
    )
    for metric in ("time_seconds", "tokens"):
        left = getattr(candidate, metric).mean if candidate is not None else None
        right = getattr(baseline, metric).mean if baseline is not None else None
        delta[metric] = (
            (left - right) if left is not None and right is not None else None
        )
    return delta


def _incomparable_gate_reasons(gates: GateConfig | None) -> list[str]:
    """Describe gates that cannot be evaluated for incompatible inputs."""
    if gates is None:
        return []
    return [
        f"{name} gate could not be evaluated because experiments are not comparable"
        for name, configured in (
            ("min_pass_rate", gates.min_pass_rate is not None),
            ("max_regression", gates.max_regression is not None),
        )
        if configured
    ]


def compare_experiments(
    candidate: "Path",
    baseline: "Path",
    gates: GateConfig | None = None,
) -> ComparisonResult:
    """Compare two complete experiments with the same evaluation inputs.

    Args:
        candidate (Path):
            Candidate experiment directory.
        baseline (Path):
            Baseline experiment directory.
        gates (GateConfig, optional):
            Quality gates to apply. Defaults to no gates.

    Returns:
        ComparisonResult:
            Compatibility metadata, metrics and gate status.

    Raises:
        OSError:
            If an experiment artifact cannot be read.
        ValueError:
            If an artifact contains invalid JSON or fails schema validation.
    """
    candidate = candidate.resolve()
    baseline = baseline.resolve()
    candidate_manifest = read_json_model(
        candidate / "manifest.json", ExperimentManifest
    )
    baseline_manifest = read_json_model(baseline / "manifest.json", ExperimentManifest)
    candidate_summary = read_json_model(candidate / "summary.json", ExperimentSummary)
    baseline_summary = read_json_model(baseline / "summary.json", ExperimentSummary)

    keys = (
        "suite",
        "runner",
        "mode",
        "target_model",
        "judge_model",
        "dataset_hash",
        "evaluation_bundle_hash",
        "case_ids",
    )
    reasons = [
        f"{key} differs: "
        f"{getattr(candidate_manifest, key)!r} != "
        f"{getattr(baseline_manifest, key)!r}"
        for key in keys
        if getattr(candidate_manifest, key) != getattr(baseline_manifest, key)
    ]
    comparable = not reasons

    candidate_metrics = candidate_summary.benchmark.run_summary
    baseline_metrics = baseline_summary.benchmark.run_summary
    candidate_with_skill = candidate_metrics.get("with_skill")
    baseline_with_skill = baseline_metrics.get("with_skill")
    candidate_micro = candidate_summary.pass_rate
    baseline_micro = baseline_summary.pass_rate

    delta = _comparison_delta(
        comparable=comparable,
        candidate=candidate_with_skill,
        baseline=baseline_with_skill,
    )

    status: ExperimentStatus = "ungraded"
    if not comparable:
        gate_reasons = _incomparable_gate_reasons(gates)
        reasons.extend(gate_reasons)
        if gate_reasons:
            status = "error"
    elif candidate_summary.status == "error" or baseline_summary.status == "error":
        status = "error"
        reasons.append("one or both experiments are incomplete")
    elif candidate_micro is not None and baseline_micro is not None:
        gate_failed = False
        if (
            gates is not None
            and gates.min_pass_rate is not None
            and candidate_micro is not None
            and candidate_micro < gates.min_pass_rate
        ):
            gate_failed = True
            reasons.append(
                f"pass rate {candidate_micro:.3f} is below gate "
                f"{gates.min_pass_rate:.3f}"
            )
        if gates is not None and gates.max_regression is not None:
            regression = delta["pass_rate"]
            if regression is None:
                status = "error"
                reasons.append("pass rate regression gate could not be evaluated")
            elif regression < -gates.max_regression:
                gate_failed = True
                reasons.append(
                    f"pass rate regression {-regression:.3f} exceeds gate "
                    f"{gates.max_regression:.3f}"
                )
        if status != "error":
            status = "failed" if gate_failed else "passed"

    message = (
        "experiments are not directly comparable"
        if not comparable and status == "ungraded"
        else "; ".join(reasons) or None
    )
    return ComparisonResult(
        comparable=comparable,
        status=status,
        candidate_dir=candidate,
        baseline_dir=baseline,
        reasons=tuple(reasons),
        candidate={
            arm: values.model_dump(mode="json")
            for arm, values in candidate_metrics.items()
        },
        baseline={
            arm: values.model_dump(mode="json")
            for arm, values in baseline_metrics.items()
        },
        delta=delta,
        gates=gates or GateConfig(),
        message=message,
    )
