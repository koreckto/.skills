import json
from pathlib import Path

import pydantic_ai
import pytest
from typer.testing import CliRunner

from skill_eval.cli import app
from skill_eval.models import ExperimentConfig, ExperimentResult, ExperimentStatus


def _comparison_artifacts(root: Path, bundle_hash: str) -> Path:
    root.mkdir()
    manifest = {
        "schema_version": 1,
        "suite": "output-quality",
        "runner": "fake",
        "mode": "auto",
        "target_model": "test:model",
        "judge_model": "test:model",
        "dataset_hash": "dataset",
        "evaluation_bundle_hash": bundle_hash,
        "case_ids": ["1"],
    }
    summary = {
        "schema_version": 1,
        "status": "passed",
        "pass_rate": 1.0,
        "benchmark": {
            "run_summary": {"with_skill": {"pass_rate": {"mean": 1.0, "n": 1}}},
            "delta": {},
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return root


def _result(status: ExperimentStatus, tmp_path: Path) -> ExperimentResult:
    return ExperimentResult(
        status=status,
        experiment_dir=tmp_path / "experiment",
        iteration_dirs=(tmp_path / "experiment" / "iteration-1",),
        pass_rate=1.0 if status == "passed" else 0.5,
        artifacts={},
    )


@pytest.mark.parametrize(
    ("status", "expected_exit_code"),
    [("passed", 0), ("failed", 1), ("error", 3)],
)
def test_run_command_experiment_status_maps_to_expected_exit_code(
    sample_skill: Path,
    tmp_path: Path,
    monkeypatch,
    status: ExperimentStatus,
    expected_exit_code: int,
) -> None:
    async def fake_evaluate(config: ExperimentConfig) -> ExperimentResult:
        return _result(status, tmp_path)

    monkeypatch.setattr("skill_eval.cli.evaluate_skill", fake_evaluate)
    result = CliRunner().invoke(
        app,
        ["run", str(sample_skill), "--target", "test:model", "--sandbox", "local"],
    )

    assert result.exit_code == expected_exit_code, result.output


def test_run_command_json_passed_restores_banner_and_reports_status(
    sample_skill: Path, tmp_path: Path, monkeypatch
) -> None:
    async def fake_evaluate(config: ExperimentConfig) -> ExperimentResult:
        assert pydantic_ai.BANNER_ENABLED is False
        assert config.skill_path == sample_skill
        assert config.target_model == "test:model"
        assert config.suite == "output-quality"
        assert config.sandbox.kind == "local"
        return _result("passed", tmp_path)

    monkeypatch.setattr("skill_eval.cli.evaluate_skill", fake_evaluate)
    monkeypatch.setattr(pydantic_ai, "BANNER_ENABLED", True)
    result = CliRunner().invoke(
        app,
        [
            "run",
            str(sample_skill),
            "--target",
            "test:model",
            "--sandbox",
            "local",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert pydantic_ai.BANNER_ENABLED is True
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"


def test_cli_run_rejects_default_docker(sample_skill: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["run", str(sample_skill), "--target", "test:model"],
    )
    assert result.exit_code == 2


@pytest.mark.parametrize(
    "option",
    [
        ["--sandbox", "bogus"],
        ["--telemetry", "bogus"],
        ["--baseline", "bogus"],
        ["--mode", "bogus"],
    ],
)
def test_cli_run_invalid_choice_reports_json_config_error(
    sample_skill: Path, option: list[str]
) -> None:
    result = CliRunner().invoke(
        app,
        [
            "run",
            str(sample_skill),
            "--target",
            "test:model",
            "--sandbox",
            "local",
            *option,
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 2, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["error"]["kind"] == "config"


@pytest.mark.parametrize("gate", ["--min-pass-rate", "--max-regression"])
def test_cli_compare_incomparable_gate_exits_error(tmp_path: Path, gate: str) -> None:
    candidate = _comparison_artifacts(tmp_path / "candidate", "candidate-bundle")
    baseline = _comparison_artifacts(tmp_path / "baseline", "baseline-bundle")

    result = CliRunner().invoke(
        app,
        ["compare", str(candidate), str(baseline), gate, "0.5", "--format", "json"],
    )

    assert result.exit_code == 3, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    gate_name = gate.removeprefix("--").replace("-", "_")
    assert gate_name in payload["message"]


def test_cli_compare_incomparable_text_omits_null_delta(tmp_path: Path) -> None:
    candidate = _comparison_artifacts(tmp_path / "candidate", "candidate-bundle")
    baseline = _comparison_artifacts(tmp_path / "baseline", "baseline-bundle")

    result = CliRunner().invoke(app, ["compare", str(candidate), str(baseline)])

    assert result.exit_code == 0, result.output
    assert "status: ungraded" in result.output
    assert "comparable: False" in result.output
    assert "delta:" not in result.output


def test_cli_exposes_all_commands_after_callback_privatization() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0, result.output
    for command in ("run", "trigger", "compare", "validate"):
        assert command in result.output
