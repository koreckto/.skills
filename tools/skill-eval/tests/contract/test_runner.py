import asyncio
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

import anyio
import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RunUsage

from skill_eval._datasets import hash_tree
from skill_eval.evaluators import SkillTrigger
from skill_eval.exceptions import ConfigError, EvaluationExecutionError
from skill_eval.models import (
    Arm,
    RunnerInfo,
    RunObservation,
    RunRequest,
    SkillCaseInput,
    SkillDeployment,
)
from skill_eval.runners.pydantic_ai import (
    PydanticAIRunner,
    _cleanup_coder_jobs,
    _extract_evidence,
    _usage_record,
)
from tests.conftest import FIXED_TIME, make_evaluator_context

type _ToolOutcome = Literal["success", "failed", "denied", "interrupted", "retried"]


def _workspace(root: Path, sample_skill: Path, *, with_skill: bool) -> Path:
    workspace = root / "work"
    for name in ("work", "outputs", "evidence"):
        (root / name).mkdir(parents=True)
    if with_skill:
        shutil.copytree(
            sample_skill,
            workspace / "skills" / "sample-skill",
            ignore=shutil.ignore_patterns("evals", "__pycache__"),
        )
    return workspace


def _load_then_finish(messages, info):
    if any(
        isinstance(part, ToolReturnPart)
        for message in messages
        for part in getattr(message, "parts", [])
    ):
        return ModelResponse(parts=[TextPart("finished")], timestamp=FIXED_TIME)
    return ModelResponse(
        parts=[
            ToolCallPart(
                "load_capability",
                {"id": "sample-skill"},
                tool_call_id="call-load-1",
            )
        ],
        timestamp=FIXED_TIME,
    )


def _load_then_fail(messages, info):
    if any(
        isinstance(part, ToolReturnPart)
        for message in messages
        for part in getattr(message, "parts", [])
    ):
        raise RuntimeError("model failed after tool call")
    return ModelResponse(
        parts=[
            ToolCallPart(
                "load_capability",
                {"id": "sample-skill"},
                tool_call_id="call-load-1",
            )
        ],
        timestamp=FIXED_TIME,
    )


def _request(
    root: Path, sample_skill: Path, *, with_skill: bool, arm: Arm = "with_skill"
) -> RunRequest:
    workspace = _workspace(root, sample_skill, with_skill=with_skill)
    deployment = None
    if with_skill:
        deployment = SkillDeployment(
            name="sample-skill",
            snapshot_path=sample_skill,
            content_hash=hash_tree(sample_skill),
        )
    return RunRequest(
        run_id="run-1",
        case_id="1",
        repeat_index=1,
        arm=arm,
        prompt="Use the sample skill.",
        workspace_dir=workspace,
        output_dir=root / "outputs",
        raw_evidence_dir=root / "evidence",
        target_model="test:model",
        skill=deployment,
        timeout_seconds=30,
    )


async def test_auto_invocation_records_loaded_skill(
    sample_skill: Path, tmp_path: Path
) -> None:
    runner = PydanticAIRunner(model=FunctionModel(_load_then_finish))
    observation = await runner.run(_request(tmp_path, sample_skill, with_skill=True))

    assert observation.response == "finished"
    assert [record.name for record in observation.loaded_skills] == ["sample-skill"]
    assert observation.loaded_skills[0].status == "success"
    assert observation.tool_calls[0].name == "load_capability"
    assert observation.tool_calls[0].arguments == {"id": "sample-skill"}
    assert observation.messages_path is not None
    assert observation.messages_path.is_file()
    assert (tmp_path / "evidence" / "runner.jsonl").is_file()
    assert observation.usage.total_tokens is not None


async def test_failed_run_preserves_captured_messages_and_runner_log(
    sample_skill: Path, tmp_path: Path
) -> None:
    runner = PydanticAIRunner(model=FunctionModel(_load_then_fail))
    request = _request(tmp_path, sample_skill, with_skill=True)

    with pytest.raises(RuntimeError, match="model failed after tool call"):
        await runner.run(request)

    messages_path = request.raw_evidence_dir / "messages.json"
    runner_log_path = request.raw_evidence_dir / "runner.jsonl"
    assert messages_path.is_file()
    assert runner_log_path.is_file()
    messages = json.loads(messages_path.read_text(encoding="utf-8"))
    assert messages
    assert "load_capability" in messages_path.read_text(encoding="utf-8")
    runner_log = runner_log_path.read_text(encoding="utf-8")
    assert '"kind": "skill_load"' in runner_log
    assert "sample-skill" in runner_log


async def test_without_skill_has_no_skill_catalog(
    sample_skill: Path, tmp_path: Path
) -> None:
    runner = PydanticAIRunner(
        model=FunctionModel(
            lambda messages, info: ModelResponse(
                parts=[TextPart("plain")], timestamp=FIXED_TIME
            )
        )
    )
    observation = await runner.run(
        _request(tmp_path, sample_skill, with_skill=False, arm="without_skill")
    )

    assert observation.response == "plain"
    assert observation.loaded_skills == []


async def test_forced_invocation_is_rejected(
    sample_skill: Path, tmp_path: Path
) -> None:
    runner = PydanticAIRunner(
        model=FunctionModel(
            lambda messages, info: ModelResponse(
                parts=[TextPart("plain")], timestamp=FIXED_TIME
            )
        )
    )
    request = _request(tmp_path, sample_skill, with_skill=True)
    request = request.model_copy(update={"invocation": "forced"})
    with pytest.raises(ConfigError, match="forced"):
        await runner.run(request)


def test_usage_record_zero_counts_preserves_zero_values() -> None:
    usage = _usage_record(
        RunUsage(input_tokens=0, output_tokens=0, requests=0, tool_calls=0)
    )

    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    assert usage.total_tokens == 0
    assert usage.requests == 0
    assert usage.tool_calls == 0


@pytest.mark.parametrize(
    ("outcome", "expected_status"),
    [
        ("success", "success"),
        ("failed", "error"),
        ("denied", "error"),
        ("interrupted", "unknown"),
        ("retried", "error"),
    ],
)
def test_tool_outcome_prevents_false_successful_trigger(
    tmp_path: Path, outcome: _ToolOutcome, expected_status: str
) -> None:
    messages = [
        ModelResponse(
            parts=[
                ToolCallPart(
                    "load_capability",
                    {"id": "sample-skill"},
                    tool_call_id="call-1",
                )
            ],
            timestamp=FIXED_TIME,
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    "load_capability",
                    "loaded",
                    tool_call_id="call-1",
                    timestamp=FIXED_TIME,
                    outcome=outcome,
                )
            ],
            timestamp=FIXED_TIME,
        ),
    ]

    loaded, calls = _extract_evidence(messages)
    inputs = SkillCaseInput(
        case_id="1",
        prompt="Load the sample skill.",
        arm="with_skill",
        workspace_dir=tmp_path / "work",
        output_dir=tmp_path / "outputs",
        raw_evidence_dir=tmp_path / "evidence",
        target_model="test:model",
    )
    observation = RunObservation(
        response="done",
        loaded_skills=loaded,
        raw_evidence_dir=inputs.raw_evidence_dir,
        output_dir=inputs.output_dir,
        runner=RunnerInfo(name="fake", version="1"),
    )
    verdict = SkillTrigger(skill_name="sample-skill", should_trigger=True).evaluate(
        make_evaluator_context(inputs, output=observation)
    )["trigger"]

    assert calls[0].status == expected_status
    assert loaded[0].status == expected_status
    assert verdict.value is (outcome == "success")


@pytest.mark.parametrize("exception_type", [None, RuntimeError, TimeoutError])
async def test_coder_cleanup_runs_after_every_agent_completion(
    sample_skill: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exception_type: type[Exception] | None,
) -> None:
    cleanup_calls = []

    class FakeAgent:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def run(self, *args, **kwargs):
            if exception_type is not None:
                raise exception_type("agent stopped")
            return SimpleNamespace(
                output="done",
                all_messages=lambda: [],
                all_messages_json=lambda: b"[]",
                usage=RunUsage(),
            )

    async def cleanup(workspace_dir, env) -> None:
        cleanup_calls.append((workspace_dir, env))

    monkeypatch.setattr("skill_eval.runners.pydantic_ai.Agent", FakeAgent)
    monkeypatch.setattr("skill_eval.runners.pydantic_ai._cleanup_coder_jobs", cleanup)
    runner = PydanticAIRunner()
    request = _request(tmp_path, sample_skill, with_skill=False)

    if exception_type is None:
        observation = await runner.run(request)
        assert observation.response == "done"
    else:
        with pytest.raises(exception_type, match="agent stopped"):
            await runner.run(request)

    assert len(cleanup_calls) == 1
    assert cleanup_calls[0][0] == request.workspace_dir


async def test_coder_cleanup_preserves_cancellation(
    sample_skill: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = anyio.Event()
    cleanup_calls = []

    class FakeAgent:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def run(self, *args, **kwargs):
            started.set()
            await anyio.Event().wait()
            raise AssertionError("unreachable")

    async def cleanup(workspace_dir, env) -> None:
        cleanup_calls.append(workspace_dir)
        raise RuntimeError("cleanup failure must not replace cancellation")

    monkeypatch.setattr("skill_eval.runners.pydantic_ai.Agent", FakeAgent)
    monkeypatch.setattr("skill_eval.runners.pydantic_ai._cleanup_coder_jobs", cleanup)
    runner = PydanticAIRunner()
    task = asyncio.create_task(
        runner.run(_request(tmp_path, sample_skill, with_skill=False))
    )
    await started.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError) as caught:
        await task

    assert len(cleanup_calls) == 1
    assert any("cleanup" in note for note in caught.value.__notes__)


def _coder_job_directory(root: Path, name: str) -> Path:
    directory = root / ".pydantic-ai-harness" / "shell" / name
    directory.mkdir(parents=True)
    (directory / "launch.ready").write_bytes(b"")
    (directory / "status.json").write_text(
        '{"pid": 12345, "exit_code": null}\n', encoding="utf-8"
    )
    return directory


def _coder_environment(root: Path) -> dict[str, str]:
    return {"HOME": str(root / ".home"), "TMPDIR": str(root / ".tmp")}


async def test_coder_unresolved_launch_window_preserves_metadata_and_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = _coder_job_directory(tmp_path, "a" * 32)
    attach_calls = []

    async def attach(workspace, job_directory, *, combined):
        attach_calls.append(job_directory)
        return

    monkeypatch.setattr("skill_eval.runners.pydantic_ai.Job.attach", attach)
    monkeypatch.setattr(
        "skill_eval.runners.pydantic_ai._CODER_JOB_REATTACH_SECONDS", 0.02
    )

    with pytest.raises(EvaluationExecutionError, match=r"reattach|metadata"):
        await _cleanup_coder_jobs(tmp_path, _coder_environment(tmp_path))

    assert len(attach_calls) >= 2
    assert directory.is_dir()
    assert (directory / "launch.ready").is_file()
    assert (directory / "status.json").is_file()


async def test_coder_cleanup_continues_after_a_job_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _coder_job_directory(tmp_path, "a" * 32)
    second = _coder_job_directory(tmp_path, "b" * 32)
    calls = []

    class FakeJob:
        def __init__(self, name: str, *, fail: bool = False) -> None:
            self.name = name
            self.fail = fail

        async def kill(self) -> None:
            calls.append((self.name, "kill"))
            if self.fail:
                raise RuntimeError("kill failed")

        async def cleanup(self) -> None:
            calls.append((self.name, "cleanup"))

    jobs = {
        first.name: FakeJob(first.name, fail=True),
        second.name: FakeJob(second.name),
    }

    async def attach(workspace, job_directory, *, combined):
        return jobs[job_directory.rsplit("/", 1)[-1]]

    monkeypatch.setattr("skill_eval.runners.pydantic_ai.Job.attach", attach)

    with pytest.raises(EvaluationExecutionError, match="kill failed"):
        await _cleanup_coder_jobs(tmp_path, _coder_environment(tmp_path))

    assert calls == [
        (first.name, "kill"),
        (second.name, "kill"),
        (second.name, "cleanup"),
    ]
    assert first.is_dir()


async def test_coder_cleanup_failure_prevents_transient_retry(
    sample_skill: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeAgent:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def run(self, *args, **kwargs):
            raise TimeoutError("transient agent failure")

    async def cleanup(workspace_dir, env) -> None:
        raise RuntimeError("unresolved job metadata")

    monkeypatch.setattr("skill_eval.runners.pydantic_ai.Agent", FakeAgent)
    monkeypatch.setattr("skill_eval.runners.pydantic_ai._cleanup_coder_jobs", cleanup)
    runner = PydanticAIRunner()

    with pytest.raises(EvaluationExecutionError) as caught:
        await runner.run(_request(tmp_path, sample_skill, with_skill=False))

    assert not isinstance(caught.value, (ConnectionError, TimeoutError))
    assert isinstance(caught.value.__cause__, TimeoutError)
    assert any("cleanup" in note for note in caught.value.__cause__.__notes__)
