import asyncio
import contextlib
import os
import re
import shlex
import shutil
import signal
from pathlib import Path

import anyio
import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from skill_eval.api import evaluate_skill
from skill_eval.evaluators import VerifyCommand
from skill_eval.exceptions import VerifierError
from skill_eval.models import CommandCheck, RunRequest, SkillCaseInput
from skill_eval.runners.pydantic_ai import PydanticAIRunner
from tests.conftest import (
    FIXED_TIME,
    FakeRunner,
    make_config,
    make_evaluator_context,
)


def _model(messages, info):
    has_load_tool = any(tool.name == "load_capability" for tool in info.function_tools)
    returned = any(
        isinstance(part, ToolReturnPart)
        for message in messages
        for part in getattr(message, "parts", [])
    )
    if has_load_tool and not returned:
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
    return ModelResponse(
        parts=[TextPart("The task is complete.")], timestamp=FIXED_TIME
    )


async def test_full_pydantic_ai_pipeline_uses_lifecycle_and_checks(
    sample_skill: Path, tmp_path: Path
) -> None:
    config = make_config(sample_skill, tmp_path / "workspace")
    runner = PydanticAIRunner(model=FunctionModel(_model))
    result = await evaluate_skill(config, runner=runner)

    assert result.status == "failed"
    assert result.pass_rate == 0.0
    iteration = result.iteration_dirs[0]
    grading = (iteration / "eval-1" / "with_skill" / "grading.json").read_text(
        encoding="utf-8"
    )
    assert "chart.png" in grading
    run_record = iteration / "eval-1" / "with_skill" / "skill-eval-run.json"
    assert run_record.is_file()
    assert '"loaded_skills"' in run_record.read_text(encoding="utf-8")
    assert not (iteration / ".work" / "eval-1" / "with_skill").exists()


def _runner_request(root: Path, *, timeout_seconds: float = 5) -> RunRequest:
    for name in ("work", "outputs", "evidence"):
        (root / name).mkdir(parents=True)
    return RunRequest(
        run_id="run-1",
        case_id="1",
        repeat_index=1,
        arm="without_skill",
        prompt="Start a background process.",
        workspace_dir=root / "work",
        output_dir=root / "outputs",
        raw_evidence_dir=root / "evidence",
        target_model="test:model",
        timeout_seconds=timeout_seconds,
    )


async def _child_pid(path: Path) -> int:
    with anyio.fail_after(3):
        while True:
            try:
                contents = await anyio.Path(path).read_text(encoding="utf-8")
            except FileNotFoundError:
                contents = ""
            if contents.strip():
                return int(contents)
            await anyio.sleep(0.01)


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def _assert_process_stopped(pid: int) -> None:
    poll_delay = anyio.Event()
    with anyio.fail_after(3):
        while _process_exists(pid):
            with anyio.move_on_after(0.01):
                await poll_delay.wait()


def _kill_test_processes(wrapper_pids: list[int], child_pids: list[int]) -> None:
    for pid in wrapper_pids:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pid, signal.SIGKILL)
    for pid in child_pids:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(pid, signal.SIGKILL)


@pytest.mark.parametrize("behavior", ["success", "error", "timeout", "cancel"])
async def test_coder_background_shell_is_cleaned_after_agent_exit(
    tmp_path: Path, behavior: str
) -> None:
    request = _runner_request(
        tmp_path, timeout_seconds=0.5 if behavior == "timeout" else 5
    )
    pid_path = request.workspace_dir / "child.pid"
    wrapper_pids: list[int] = []
    child_pids: list[int] = []
    child_ready = anyio.Event()

    async def model(messages, info):
        shell_returns = [
            part
            for message in messages
            for part in getattr(message, "parts", [])
            if isinstance(part, ToolReturnPart) and part.tool_name == "shell"
        ]
        if not shell_returns:
            command = f"sleep 300 & echo $! > {shlex.quote(str(pid_path))}; wait"
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "shell",
                        {"command": command, "mode": "background"},
                        tool_call_id="call-shell-1",
                    )
                ],
                timestamp=FIXED_TIME,
            )
        match = re.search(r"PID: (\d+)", str(shell_returns[-1].content))
        assert match is not None
        wrapper_pids.append(int(match.group(1)))
        child_pids.append(await _child_pid(pid_path))
        child_ready.set()
        if behavior == "error":
            raise RuntimeError("model failed")
        if behavior in {"timeout", "cancel"}:
            await anyio.Event().wait()
        return ModelResponse(parts=[TextPart("done")], timestamp=FIXED_TIME)

    runner = PydanticAIRunner(model=FunctionModel(model))
    cleanup_verified = False
    try:
        if behavior == "success":
            observation = await runner.run(request)
            assert observation.response == "done"
        elif behavior == "error":
            with pytest.raises(RuntimeError, match="model failed"):
                await runner.run(request)
        elif behavior == "timeout":
            with pytest.raises(TimeoutError):
                await runner.run(request)
        else:
            task = asyncio.create_task(runner.run(request))
            await child_ready.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError), anyio.fail_after(3):
                await task
        assert child_pids
        assert wrapper_pids
        await _assert_process_stopped(child_pids[0])
        await _assert_process_stopped(wrapper_pids[0])
        cleanup_verified = True
    finally:
        if not cleanup_verified:
            _kill_test_processes(wrapper_pids, child_pids)


async def test_verifier_wall_clock_timeout_is_evaluator_error(
    sample_skill: Path, tmp_path: Path
) -> None:
    skill = tmp_path / "sample-skill"
    shutil.copytree(sample_skill, skill)
    (skill / "evals" / "verify.py").write_text(
        "while True:\n    pass\n", encoding="utf-8"
    )
    config_file = skill / "evals" / "skill-eval.yaml"
    config_file.write_text(
        config_file.read_text(encoding="utf-8").replace(
            "timeout_seconds: 5", "timeout_seconds: 0.01"
        ),
        encoding="utf-8",
    )
    config = make_config(skill, tmp_path / "workspace")

    result = await evaluate_skill(config, runner=FakeRunner(pass_without=True))

    assert result.status == "error"
    assert "timed out" in (result.message or "")


async def test_verifier_kills_descendant_that_inherits_output_pipes(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "bundle"
    workspace = tmp_path / "work"
    outputs = tmp_path / "outputs"
    evidence = tmp_path / "evidence"
    for directory in (bundle, workspace, outputs, evidence):
        directory.mkdir()
    (bundle / "verify.py").write_text(
        "import os\n"
        "import time\n"
        "pid = os.fork()\n"
        "if pid == 0:\n"
        "    time.sleep(300)\n"
        "    os._exit(0)\n"
        "print(pid, flush=True)\n",
        encoding="utf-8",
    )
    inputs = SkillCaseInput(
        case_id="1",
        prompt="Test descendants.",
        arm="with_skill",
        workspace_dir=workspace,
        output_dir=outputs,
        raw_evidence_dir=evidence,
        target_model="test:model",
    )
    check = CommandCheck(
        case="1",
        assertion="descendants are cleaned",
        type="command",
        timeout_seconds=0.05,
    )
    evaluator = VerifyCommand(
        checks=(check,), bundle_dir=bundle, case_id="1", arm="with_skill"
    )
    child_pids: list[int] = []
    cleanup_verified = False
    try:
        with pytest.raises(VerifierError, match="timed out"):
            await evaluator.evaluate(make_evaluator_context(inputs))
        stdout_path = next(evidence.glob("checks/*/stdout.txt"))
        child_pids.append(int(stdout_path.read_text(encoding="utf-8")))
        await _assert_process_stopped(child_pids[0])
        cleanup_verified = True
    finally:
        if not cleanup_verified:
            _kill_test_processes([], child_pids)


async def test_verifier_cancellation_during_real_spawn_cleans_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = tmp_path / "bundle"
    workspace = tmp_path / "work"
    outputs = tmp_path / "outputs"
    evidence = tmp_path / "evidence"
    for directory in (bundle, workspace, outputs, evidence):
        directory.mkdir()
    (bundle / "verify.py").write_text(
        "import time\ntime.sleep(300)\n", encoding="utf-8"
    )
    inputs = SkillCaseInput(
        case_id="1",
        prompt="Test spawn cancellation.",
        arm="with_skill",
        workspace_dir=workspace,
        output_dir=outputs,
        raw_evidence_dir=evidence,
        target_model="test:model",
    )
    check = CommandCheck(case="1", assertion="spawn cleanup", type="command")
    evaluator = VerifyCommand(
        checks=(check,), bundle_dir=bundle, case_id="1", arm="with_skill"
    )
    spawn_started = anyio.Event()
    release_spawn = anyio.Event()
    real_open_process = anyio.open_process
    processes = []

    async def delayed_open_process(*args, **kwargs):
        spawn_started.set()
        await release_spawn.wait()
        process = await real_open_process(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(
        "skill_eval.evaluators.checks.anyio.open_process", delayed_open_process
    )
    context = make_evaluator_context(inputs)
    task = asyncio.create_task(evaluator.evaluate(context))
    await spawn_started.wait()
    task.cancel()
    release_spawn.set()
    cleanup_verified = False
    try:
        with pytest.raises(asyncio.CancelledError), anyio.fail_after(3):
            await task
        assert processes
        process = processes[0]
        assert process.returncode is not None
        await _assert_process_stopped(process.pid)
        cleanup_verified = True
    finally:
        if processes and not cleanup_verified:
            _kill_test_processes([processes[0].pid], [])


async def test_verifier_spawn_shield_has_a_wall_clock_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = tmp_path / "bundle"
    workspace = tmp_path / "work"
    outputs = tmp_path / "outputs"
    evidence = tmp_path / "evidence"
    for directory in (bundle, workspace, outputs, evidence):
        directory.mkdir()
    (bundle / "verify.py").write_text("", encoding="utf-8")
    inputs = SkillCaseInput(
        case_id="1",
        prompt="Test spawn deadline.",
        arm="with_skill",
        workspace_dir=workspace,
        output_dir=outputs,
        raw_evidence_dir=evidence,
        target_model="test:model",
    )
    check = CommandCheck(case="1", assertion="spawn deadline", type="command")
    evaluator = VerifyCommand(
        checks=(check,), bundle_dir=bundle, case_id="1", arm="with_skill"
    )

    async def open_process(*args, **kwargs):
        await anyio.Event().wait()
        raise AssertionError("unreachable")

    monkeypatch.setattr("skill_eval.evaluators.checks.anyio.open_process", open_process)
    monkeypatch.setattr(
        "skill_eval.evaluators.checks._VERIFIER_SPAWN_TIMEOUT_SECONDS", 0.01
    )

    with pytest.raises(VerifierError, match="starting"), anyio.fail_after(1):
        await evaluator.evaluate(make_evaluator_context(inputs))
