from datetime import UTC, datetime
from itertools import count
from pathlib import Path
from typing import Literal, cast

import anyio
import pytest
from pydantic_evals.evaluators import EvaluatorContext
from pydantic_evals.otel.span_tree import SpanTree

from skill_eval.models import (
    BaselineConfig,
    ExperimentConfig,
    GateConfig,
    RunnerCapabilities,
    RunnerInfo,
    RunObservation,
    RunRequest,
    SandboxConfig,
    SkillCaseInput,
    SkillCaseMetadata,
    SkillEvaluatorContext,
    SkillLoadRecord,
    TelemetryConfig,
    UsageRecord,
)

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_SKILL = FIXTURES / "skills" / "sample-skill"
FIXED_TIME = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    """Run async tests on the asyncio backend only."""
    return "asyncio"


@pytest.fixture(autouse=True)
def _isolate_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skill_eval._artifacts._utc_now", lambda: FIXED_TIME)
    experiment_ids = count()

    def token_hex(size: int) -> str:
        return f"{next(experiment_ids):0{size * 2}x}"

    monkeypatch.setattr("skill_eval._artifacts.secrets.token_hex", token_hex)


class FakeRunner:
    """Deterministic runner used by unit and contract tests."""

    def __init__(
        self, *, pass_without: bool = False, pass_with_skill: bool = True
    ) -> None:
        self.pass_without = pass_without
        self.pass_with_skill = pass_with_skill

    @property
    def info(self) -> RunnerInfo:
        return RunnerInfo(name="fake", version="1", config_summary={"test": True})

    @property
    def capabilities(self) -> RunnerCapabilities:
        return RunnerCapabilities(
            auto_invocation=True,
            forced_invocation=False,
            loaded_skill_evidence=True,
            tool_call_evidence=True,
            token_usage=True,
            cost_usage=True,
            sandbox_types=("local",),
        )

    async def run(self, request: RunRequest) -> RunObservation:
        return await anyio.to_thread.run_sync(self._run, request)

    def _run(self, request: RunRequest) -> RunObservation:
        request.workspace_dir.mkdir(parents=True, exist_ok=True)
        workspace_outputs = request.workspace_dir / "outputs"
        workspace_outputs.mkdir(parents=True, exist_ok=True)
        request.raw_evidence_dir.mkdir(parents=True, exist_ok=True)
        for fixture in request.fixture_files:
            assert fixture.is_file(), fixture

        loaded: list[SkillLoadRecord] = []
        if request.skill is not None and "JavaScript" not in request.prompt:
            loaded.append(
                SkillLoadRecord(
                    name=request.skill.name,
                    call_id="call-1",
                    status="success",
                    source_event_index=0,
                )
            )

        pass_case = (
            self.pass_with_skill if request.arm == "with_skill" else self.pass_without
        )
        if pass_case:
            (workspace_outputs / "chart.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
            (workspace_outputs / "result.json").write_text(
                '{"ok": true}\n', encoding="utf-8"
            )
        elif request.arm == "without_skill":
            (workspace_outputs / "result.json").write_text(
                "not json\n", encoding="utf-8"
            )

        messages_path = request.raw_evidence_dir / "messages.json"
        messages_path.write_text("[]\n", encoding="utf-8")
        (request.raw_evidence_dir / "runner.jsonl").write_text("", encoding="utf-8")
        return RunObservation(
            response="done",
            loaded_skills=loaded,
            tool_calls=[],
            usage=UsageRecord(
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                requests=2,
                tool_calls=1,
                cost_usd=0.01,
            ),
            messages_path=messages_path,
            raw_evidence_dir=request.raw_evidence_dir,
            output_dir=request.output_dir,
            runner=self.info,
        )


def make_evaluator_context(
    inputs: SkillCaseInput,
    *,
    output: RunObservation | None = None,
    metadata: SkillCaseMetadata | None = None,
    attributes: dict[str, object] | None = None,
) -> SkillEvaluatorContext:
    """Build a fully typed context for direct evaluator tests."""
    if output is None:
        output = RunObservation(
            response="test response",
            raw_evidence_dir=inputs.raw_evidence_dir,
            output_dir=inputs.output_dir,
            runner=RunnerInfo(name="fake", version="1"),
        )
    return EvaluatorContext[SkillCaseInput, RunObservation, SkillCaseMetadata](
        name=inputs.case_id,
        inputs=inputs,
        metadata=metadata,
        expected_output=None,
        output=output,
        duration=0.0,
        _span_tree=SpanTree(),
        attributes=dict(attributes or {}),
        metrics={},
    )


@pytest.fixture
def sample_skill() -> Path:
    return SAMPLE_SKILL


@pytest.fixture
def fake_runner() -> FakeRunner:
    return FakeRunner()


def make_config(
    skill_path: Path,
    workspace: Path,
    *,
    baseline: str = "no-skill",
    baseline_skill: Path | None = None,
    repeat: int = 1,
    suite: str = "output-quality",
    case_ids: tuple[str, ...] = (),
    gates: GateConfig | None = None,
) -> ExperimentConfig:
    return ExperimentConfig(
        skill_path=skill_path,
        suite=cast(Literal["output-quality", "trigger"], suite),
        target_model="test:model",
        baseline=BaselineConfig(
            mode=cast(Literal["no-skill", "none", "skill"], baseline),
            skill_path=baseline_skill,
        ),
        case_ids=case_ids,
        repeat=repeat,
        concurrency=2,
        timeout_seconds=30,
        sandbox=SandboxConfig(kind="local"),
        workspace=workspace,
        telemetry=TelemetryConfig(kind="local"),
        gates=gates or GateConfig(),
    )
