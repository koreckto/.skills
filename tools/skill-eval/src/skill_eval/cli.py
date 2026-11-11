"""Command line interface for the internal skill evaluation tool."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import anyio
import pydantic_ai
import typer
from pydantic import ValidationError

from skill_eval._config import load_skill_eval_config
from skill_eval.api import compare_experiments, evaluate_skill, validate_skill
from skill_eval.exceptions import ConfigError, EvaluationExecutionError
from skill_eval.models import (
    BaselineConfig,
    ExperimentConfig,
    GateConfig,
    SandboxConfig,
    TelemetryConfig,
)

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Evaluate Agent Skills with Pydantic Evals.",
)


@dataclass(frozen=True, slots=True)
class _RunOptions:
    """Execution options shared by the output-quality and trigger commands."""

    skill_path: Path
    target: str
    judge: str | None
    runner: str
    mode: str
    baseline: str
    baseline_skill: Path | None
    case: tuple[str, ...]
    repeat: int
    concurrency: int
    timeout: float
    sandbox: str
    image: str | None
    workspace: Path
    config_path: Path | None
    telemetry: str
    suite: Literal["output-quality", "trigger"]


def _build_config(options: _RunOptions) -> ExperimentConfig:
    skill_config = load_skill_eval_config(
        options.skill_path,
        options.config_path,
        required=options.config_path is not None,
    )

    try:
        baseline_config = BaselineConfig(
            mode=cast("Literal['no-skill', 'none', 'skill']", options.baseline),
            skill_path=options.baseline_skill,
        )
        sandbox_config = SandboxConfig(
            kind=cast("Literal['local', 'docker']", options.sandbox),
            image=options.image,
        )

        return ExperimentConfig(
            skill_path=options.skill_path,
            suite=options.suite,
            target_model=options.target,
            judge_model=options.judge,
            runner=options.runner,
            mode=cast("Literal['auto', 'forced']", options.mode),
            baseline=baseline_config,
            case_ids=options.case,
            repeat=options.repeat,
            concurrency=options.concurrency,
            timeout_seconds=options.timeout,
            sandbox=sandbox_config,
            workspace=options.workspace,
            config_path=options.config_path,
            telemetry=TelemetryConfig(
                kind=cast("Literal['local', 'logfire', 'otlp']", options.telemetry)
            ),
            gates=skill_config.gates,
        )
    except ValidationError as err:
        raise ConfigError(f"invalid configuration: {err}") from err


def _error_payload(message: str, kind: str = "config") -> dict[str, object]:
    return {"status": "error", "error": {"kind": kind, "message": message}}


def _print_error(message: str, output_format: str, kind: str = "config") -> None:
    if output_format == "json":
        typer.echo(json.dumps(_error_payload(message, kind), ensure_ascii=False))
    else:
        typer.echo(message, err=True)


def _exit_code(status: str) -> int:
    if status in {"passed", "ungraded"}:
        return 0
    if status == "failed":
        return 1
    return 3


def _run_and_report(config: ExperimentConfig, output_format: str) -> None:
    # The CLI owns its output streams; suppress the library's first-run banner only
    # during evaluation.
    banner_enabled = pydantic_ai.BANNER_ENABLED
    pydantic_ai.BANNER_ENABLED = False  # ty: ignore[invalid-assignment]  # pydantic-ai documents runtime mutation, but its stub narrows the flag to Literal[True].
    try:
        result = anyio.run(evaluate_skill, config)
    except ConfigError as err:
        _print_error(str(err), output_format)
        raise typer.Exit(2) from err
    except EvaluationExecutionError as err:
        _print_error(str(err), output_format, "execution")
        raise typer.Exit(3) from err
    except Exception as err:
        _print_error(f"{type(err).__name__}: {err}", output_format, "execution")
        raise typer.Exit(3) from err
    finally:
        pydantic_ai.BANNER_ENABLED = banner_enabled

    payload = {
        "status": result.status,
        "experiment_dir": str(result.experiment_dir),
        "iteration_dirs": [str(path) for path in result.iteration_dirs],
        "pass_rate": result.pass_rate,
        "artifacts": {key: str(value) for key, value in result.artifacts.items()},
        "message": result.message,
    }
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        typer.echo(f"status: {result.status}")
        typer.echo(f"experiment: {result.experiment_dir}")
        if result.pass_rate is not None:
            typer.echo(f"pass rate: {result.pass_rate:.3f}")
        for iteration in result.iteration_dirs:
            typer.echo(f"iteration: {iteration}")
        if result.message:
            typer.echo(result.message, err=True)

    raise typer.Exit(_exit_code(result.status))


# ==================================================================================
# Commands
# ==================================================================================


@app.command("validate")
def _validate_command(
    skill_path: Path = typer.Argument(
        ..., exists=False, help="Skill directory containing SKILL.md."
    ),
    output_format: str = typer.Option("text", "--format", help="text or json"),
) -> None:
    """Validate a skill package and its evaluation definitions without model calls."""
    try:
        result = validate_skill(skill_path)
    except ConfigError as err:
        _print_error(str(err), output_format)
        raise typer.Exit(2) from err

    payload = {
        "status": "passed" if result.ok else "error",
        "skill_path": str(result.skill_path),
        "skill_name": result.skill_name,
        "errors": list(result.errors),
        "warnings": list(result.warnings),
    }
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        typer.echo(f"{'OK' if result.ok else 'INVALID'}: {result.skill_path}")
        for warning in result.warnings:
            typer.echo(f"warning: {warning}", err=True)
        for error in result.errors:
            typer.echo(f"error: {error}", err=True)

    raise typer.Exit(0 if result.ok else 2)


def _common_run_options(options: _RunOptions, output_format: str) -> None:
    try:
        experiment = _build_config(options)
    except ConfigError as err:
        _print_error(str(err), output_format)
        raise typer.Exit(2) from err

    _run_and_report(experiment, output_format)


@app.command("run")
def _run_command(
    skill_path: Path = typer.Argument(
        ..., exists=False, help="Skill directory containing SKILL.md."
    ),
    target: str = typer.Option(
        ..., "--target", help="Target model, for example openai:gpt-5."
    ),
    judge: str | None = typer.Option(
        None, "--judge", help="Judge model; defaults to target."
    ),
    runner: str = typer.Option("pydantic-ai", "--runner"),
    mode: str = typer.Option(
        "auto", "--mode", help="auto; forced is not supported by pydantic-ai."
    ),
    baseline: str = typer.Option(
        "no-skill", "--baseline", help="no-skill, none, or skill."
    ),
    baseline_skill: Path | None = typer.Option(
        None, "--baseline-skill", help="Baseline skill for --baseline skill."
    ),
    case: list[str] | None = typer.Option(
        None, "--case", help="Eval id to run; repeat for multiple cases."
    ),
    repeat: int = typer.Option(1, "--repeat", min=1),
    concurrency: int = typer.Option(2, "--concurrency", min=1),
    timeout: float = typer.Option(600, "--timeout", min=0.001),
    sandbox: str = typer.Option("docker", "--sandbox", help="local or docker."),
    image: str | None = typer.Option(None, "--image", help="Docker image digest."),
    workspace: Path = typer.Option(Path(".skill-eval"), "--workspace"),
    config: Path | None = typer.Option(None, "--config"),
    telemetry: str = typer.Option(
        "local", "--telemetry", help="local, logfire, or otlp."
    ),
    output_format: str = typer.Option("text", "--format", help="text or json."),
) -> None:
    """Run the official output-quality evaluation loop."""
    options = _RunOptions(
        skill_path=skill_path,
        target=target,
        judge=judge,
        runner=runner,
        mode=mode,
        baseline=baseline,
        baseline_skill=baseline_skill,
        case=tuple(case or ()),
        repeat=repeat,
        concurrency=concurrency,
        timeout=timeout,
        sandbox=sandbox,
        image=image,
        workspace=workspace,
        config_path=config,
        telemetry=telemetry,
        suite="output-quality",
    )
    _common_run_options(options, output_format)


@app.command("trigger")
def _trigger_command(
    skill_path: Path = typer.Argument(..., exists=False),
    target: str = typer.Option(..., "--target"),
    judge: str | None = typer.Option(None, "--judge"),
    runner: str = typer.Option("pydantic-ai", "--runner"),
    case: list[str] | None = typer.Option(None, "--case"),
    repeat: int = typer.Option(1, "--repeat", min=1),
    concurrency: int = typer.Option(2, "--concurrency", min=1),
    timeout: float = typer.Option(600, "--timeout", min=0.001),
    sandbox: str = typer.Option("docker", "--sandbox"),
    image: str | None = typer.Option(None, "--image"),
    workspace: Path = typer.Option(Path(".skill-eval"), "--workspace"),
    config: Path | None = typer.Option(None, "--config"),
    telemetry: str = typer.Option("local", "--telemetry"),
    output_format: str = typer.Option("text", "--format"),
) -> None:
    """Run the trigger suite from skill-eval.yaml."""
    options = _RunOptions(
        skill_path=skill_path,
        target=target,
        judge=judge,
        runner=runner,
        mode="auto",
        baseline="none",
        baseline_skill=None,
        case=tuple(case or ()),
        repeat=repeat,
        concurrency=concurrency,
        timeout=timeout,
        sandbox=sandbox,
        image=image,
        workspace=workspace,
        config_path=config,
        telemetry=telemetry,
        suite="trigger",
    )
    _common_run_options(options, output_format)


@app.command("compare")
def _compare_command(
    candidate: Path = typer.Argument(...),
    baseline: Path = typer.Argument(...),
    min_pass_rate: float | None = typer.Option(None, "--min-pass-rate", min=0, max=1),
    max_regression: float | None = typer.Option(None, "--max-regression", min=0, max=1),
    output_format: str = typer.Option("text", "--format"),
) -> None:
    """Compare two experiment directories."""
    gates = GateConfig(min_pass_rate=min_pass_rate, max_regression=max_regression)
    try:
        result = compare_experiments(candidate, baseline, gates)
    except (OSError, KeyError, ValueError) as err:
        _print_error(f"cannot compare experiments: {err}", output_format)
        raise typer.Exit(2) from err
    except Exception as err:
        _print_error(f"{type(err).__name__}: {err}", output_format, "execution")
        raise typer.Exit(3) from err

    payload = result.model_dump(mode="json")
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        typer.echo(f"status: {result.status}")
        typer.echo(f"comparable: {result.comparable}")
        if result.reasons:
            for reason in result.reasons:
                typer.echo(f"reason: {reason}", err=True)
        if result.comparable and any(
            value is not None for value in result.delta.values()
        ):
            typer.echo(f"delta: {json.dumps(result.delta, ensure_ascii=False)}")

    raise typer.Exit(_exit_code(result.status))


if __name__ == "__main__":
    app()
