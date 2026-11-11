from pathlib import Path
from typing import cast

import pytest

from skill_eval._helpers import _read_json, read_json_model, write_json
from skill_eval.api import compare_experiments, evaluate_skill
from skill_eval.models import ExperimentSummary, GateConfig
from tests.conftest import FakeRunner, make_config


async def _experiment(
    sample_skill: Path,
    root: Path,
    *,
    pass_without: bool = True,
    pass_with_skill: bool = True,
    suite: str = "output-quality",
) -> Path:
    config = make_config(sample_skill, root, suite=suite)
    result = await evaluate_skill(
        config,
        runner=FakeRunner(pass_without=pass_without, pass_with_skill=pass_with_skill),
    )
    return result.experiment_dir


async def _comparison_experiment(
    root: Path,
    *,
    case_mean: float | None,
    assertion_micro: float | None,
    suite: str = "output-quality",
    status: str = "passed",
) -> Path:
    manifest = {
        "schema_version": 1,
        "suite": suite,
        "runner": "fake",
        "mode": "auto",
        "target_model": "test:model",
        "judge_model": "test:model",
        "dataset_hash": "dataset",
        "evaluation_bundle_hash": "bundle",
        "case_ids": ["one", "two"],
    }
    summary = {
        "schema_version": 1,
        "status": status,
        "pass_rate": assertion_micro,
        "benchmark": {
            "run_summary": {
                "with_skill": {
                    "pass_rate": {
                        "mean": case_mean,
                        "n": 2 if case_mean is not None else 0,
                    }
                }
            },
            "delta": {},
        },
    }
    await write_json(root / "manifest.json", manifest)
    await write_json(root / "summary.json", summary)
    return root


async def test_compare_experiments_comparable_pass_rates_computes_candidate_delta(
    sample_skill: Path, tmp_path: Path
) -> None:
    candidate = await _experiment(
        sample_skill, tmp_path / "candidate", pass_without=True
    )
    baseline = await _experiment(
        sample_skill, tmp_path / "baseline", pass_without=False
    )
    manifest_path = baseline / "manifest.json"
    manifest = cast("dict[str, object]", _read_json(manifest_path))
    # Keep the baseline's with_skill arm weaker while preserving comparability metadata.
    summary_path = baseline / "summary.json"
    summary = read_json_model(summary_path, ExperimentSummary)
    with_skill = summary.benchmark.run_summary["with_skill"]
    updated_with_skill = with_skill.model_copy(
        update={"pass_rate": with_skill.pass_rate.model_copy(update={"mean": 0.5})}
    )
    benchmark = summary.benchmark.model_copy(
        update={
            "run_summary": {
                **summary.benchmark.run_summary,
                "with_skill": updated_with_skill,
            }
        }
    )
    summary = summary.model_copy(update={"pass_rate": 0.5, "benchmark": benchmark})
    await write_json(summary_path, summary.model_dump(mode="json"))

    result = compare_experiments(candidate, baseline, GateConfig(max_regression=0.25))

    assert result.comparable
    assert result.status == "passed"
    assert result.delta["pass_rate"] == 0.5
    assert manifest["evaluation_bundle_hash"]


async def test_compare_marks_different_bundles_not_comparable(
    sample_skill: Path, tmp_path: Path
) -> None:
    candidate = await _experiment(
        sample_skill, tmp_path / "candidate", pass_without=True
    )
    baseline = await _experiment(sample_skill, tmp_path / "baseline", pass_without=True)
    manifest_path = baseline / "manifest.json"
    manifest = cast("dict[str, object]", _read_json(manifest_path))
    manifest["evaluation_bundle_hash"] = "different"
    await write_json(manifest_path, manifest)

    result = compare_experiments(candidate, baseline)

    assert not result.comparable
    assert result.status == "ungraded"
    assert any("evaluation_bundle_hash" in reason for reason in result.reasons)
    assert result.delta
    assert all(value is None for value in result.delta.values())


@pytest.mark.parametrize(
    ("gates", "gate_name"),
    [
        (GateConfig(min_pass_rate=0.5), "min_pass_rate"),
        (GateConfig(max_regression=0.1), "max_regression"),
    ],
)
async def test_compare_incomparable_experiments_fail_explicit_gates(
    sample_skill: Path,
    tmp_path: Path,
    gates: GateConfig,
    gate_name: str,
) -> None:
    candidate = await _experiment(sample_skill, tmp_path / "candidate")
    baseline = await _experiment(sample_skill, tmp_path / "baseline")
    manifest_path = baseline / "manifest.json"
    manifest = cast("dict[str, object]", _read_json(manifest_path))
    manifest["evaluation_bundle_hash"] = "different"
    await write_json(manifest_path, manifest)

    result = compare_experiments(candidate, baseline, gates)

    assert not result.comparable
    assert result.status == "error"
    assert any(
        gate_name in reason and "could not be evaluated" in reason
        for reason in result.reasons
    )
    assert gate_name in (result.message or "")
    assert "could not be evaluated" in (result.message or "")


async def test_compare_uses_case_mean_for_regression_and_micro_for_minimum(
    tmp_path: Path,
) -> None:
    # Candidate cases score 3/3 and 0/1: micro=0.75, case-mean=0.5.
    candidate = await _comparison_experiment(
        tmp_path / "candidate", case_mean=0.5, assertion_micro=0.75
    )
    baseline = await _comparison_experiment(
        tmp_path / "baseline", case_mean=1.0, assertion_micro=1.0
    )

    result = compare_experiments(
        candidate,
        baseline,
        GateConfig(min_pass_rate=0.7, max_regression=0.4),
    )

    assert result.delta["pass_rate"] == -0.5
    assert result.status == "failed"
    assert any("regression 0.500" in reason for reason in result.reasons)
    assert not any("below gate" in reason for reason in result.reasons)
    assert "regression" in (result.message or "")


async def test_compare_minimum_gate_uses_assertion_micro_average(
    tmp_path: Path,
) -> None:
    # Cases score 1/1 and 2/4: micro=0.6, case-mean=0.75.
    candidate = await _comparison_experiment(
        tmp_path / "candidate", case_mean=0.75, assertion_micro=0.6
    )
    baseline = await _comparison_experiment(
        tmp_path / "baseline", case_mean=0.75, assertion_micro=0.6
    )

    result = compare_experiments(candidate, baseline, GateConfig(min_pass_rate=0.7))

    assert result.delta["pass_rate"] == 0
    assert result.status == "failed"
    assert any("0.600" in reason and "0.700" in reason for reason in result.reasons)
    assert "below gate" in (result.message or "")


async def test_compare_ungraded_experiment_stays_ungraded(tmp_path: Path) -> None:
    candidate = await _comparison_experiment(
        tmp_path / "candidate", case_mean=None, assertion_micro=None
    )
    baseline = await _comparison_experiment(
        tmp_path / "baseline", case_mean=None, assertion_micro=None
    )

    result = compare_experiments(candidate, baseline)

    assert result.status == "ungraded"
    assert result.delta["pass_rate"] is None


async def test_compare_ungraded_candidate_with_min_gate_is_error(
    tmp_path: Path,
) -> None:
    candidate = await _comparison_experiment(
        tmp_path / "candidate", case_mean=None, assertion_micro=None
    )
    baseline = await _comparison_experiment(
        tmp_path / "baseline", case_mean=None, assertion_micro=None
    )

    result = compare_experiments(candidate, baseline, GateConfig(min_pass_rate=0.5))

    assert result.status == "error"
    assert any(
        "min_pass_rate" in reason and "could not be evaluated" in reason
        for reason in result.reasons
    )
    assert "min_pass_rate" in (result.message or "")


async def test_compare_min_gate_passes_without_baseline_pass_rate(
    tmp_path: Path,
) -> None:
    candidate = await _comparison_experiment(
        tmp_path / "candidate", case_mean=0.75, assertion_micro=0.75
    )
    baseline = await _comparison_experiment(
        tmp_path / "baseline", case_mean=None, assertion_micro=None
    )

    result = compare_experiments(candidate, baseline, GateConfig(min_pass_rate=0.7))

    assert result.comparable
    assert result.status == "passed"
    assert result.reasons == ()
    assert result.delta["pass_rate"] is None


async def test_compare_trigger_suite_ignores_max_regression(tmp_path: Path) -> None:
    candidate = await _comparison_experiment(
        tmp_path / "candidate",
        case_mean=0.5,
        assertion_micro=0.5,
        suite="trigger",
    )
    baseline = await _comparison_experiment(
        tmp_path / "baseline",
        case_mean=1.0,
        assertion_micro=1.0,
        suite="trigger",
    )

    result = compare_experiments(candidate, baseline, GateConfig(max_regression=0.1))

    assert result.comparable
    assert result.delta["pass_rate"] == -0.5
    assert result.status == "passed"
    assert not any("regression" in reason for reason in result.reasons)


async def test_compare_failed_candidate_experiment_marks_comparison_failed(
    sample_skill: Path, tmp_path: Path
) -> None:
    candidate = await _experiment(
        sample_skill, tmp_path / "candidate", pass_with_skill=False
    )
    baseline = await _experiment(sample_skill, tmp_path / "baseline")

    result = compare_experiments(candidate, baseline)

    assert result.comparable
    assert result.status == "failed"
    assert any(
        "candidate" in reason and "failed" in reason for reason in result.reasons
    )
    assert "failed" in (result.message or "")


async def test_compare_experiments_regression_above_gate_marks_failed(
    sample_skill: Path, tmp_path: Path
) -> None:
    candidate = await _experiment(
        sample_skill, tmp_path / "candidate", pass_with_skill=False
    )
    baseline = await _experiment(sample_skill, tmp_path / "baseline", pass_without=True)

    result = compare_experiments(candidate, baseline, GateConfig(max_regression=0.1))

    assert result.comparable
    assert result.status == "failed"
    assert any("regression" in reason for reason in result.reasons)
    assert "regression" in (result.message or "")


async def test_compare_rejects_different_suites(
    sample_skill: Path, tmp_path: Path
) -> None:
    candidate = await _experiment(sample_skill, tmp_path / "candidate")
    baseline = await _experiment(sample_skill, tmp_path / "baseline", suite="trigger")

    result = compare_experiments(candidate, baseline)

    assert not result.comparable
    assert any("suite differs" in reason for reason in result.reasons)


async def test_compare_rejects_non_object_summary(
    sample_skill: Path, tmp_path: Path
) -> None:
    candidate = await _experiment(sample_skill, tmp_path / "candidate")
    baseline = await _experiment(sample_skill, tmp_path / "baseline")
    await write_json(candidate / "summary.json", [])

    with pytest.raises(ValueError, match=r"summary\.json"):
        compare_experiments(candidate, baseline)
