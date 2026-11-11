import asyncio
import os
import shutil
import signal
from pathlib import Path

import anyio
import pytest

from skill_eval.api import evaluate_skill
from skill_eval.evaluators import VerifyCommand
from skill_eval.evaluators.checks import _kill_group
from skill_eval.models import CommandCheck, SkillCaseInput, SkillEvaluatorContext
from tests.conftest import FakeRunner, make_config, make_evaluator_context


def _copy_skill(tmp_path: Path, source: Path) -> Path:
    target = tmp_path / "sample-skill"
    shutil.copytree(source, target)
    return target


def _write_verifier(skill: Path, body: str) -> None:
    (skill / "evals" / "verify.py").write_text(body, encoding="utf-8")


def _direct_verifier(root: Path) -> tuple[VerifyCommand, SkillEvaluatorContext]:
    bundle = root / "bundle"
    workspace = root / "work"
    outputs = root / "outputs"
    for directory in (bundle, workspace, outputs):
        directory.mkdir()
    (bundle / "verify.py").write_text("", encoding="utf-8")
    inputs = SkillCaseInput(
        case_id="1",
        prompt="Test process lifecycle.",
        arm="with_skill",
        workspace_dir=workspace,
        output_dir=outputs,
        raw_evidence_dir=root / "evidence",
        target_model="test:model",
    )
    check = CommandCheck(case="1", assertion="process lifecycle", type="command")
    evaluator = VerifyCommand(
        checks=(check,), bundle_dir=bundle, case_id="1", arm="with_skill"
    )
    return evaluator, make_evaluator_context(inputs)


@pytest.mark.parametrize(
    ("body", "expected_status", "expected_fragment"),
    [
        ("import sys\nsys.exit(0)\n", "error", "blank stdout"),
        ("import sys\nsys.exit(1)\n", "failed", "exit=1"),
        ("import sys\nsys.exit(2)\n", "error", "internal or contract"),
        ("raise RuntimeError('boom')\n", "failed", "exit=1"),
    ],
)
async def test_verify_command_verifier_exit_codes_map_to_expected_status(
    sample_skill: Path,
    tmp_path: Path,
    body: str,
    expected_status: str,
    expected_fragment: str,
) -> None:
    skill = _copy_skill(tmp_path, sample_skill)
    _write_verifier(skill, body)
    config = make_config(skill, tmp_path / "workspace")
    result = await evaluate_skill(config, runner=FakeRunner(pass_without=True))

    assert result.status == expected_status
    grading_path = result.iteration_dirs[0] / "eval-1" / "with_skill" / "grading.json"
    assert grading_path.is_file()
    grading = grading_path.read_text(encoding="utf-8")
    assert expected_fragment in f"{result.message or ''} {grading}"


async def test_verifier_output_over_byte_limit_is_an_error(
    sample_skill: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skill = _copy_skill(tmp_path, sample_skill)
    _write_verifier(skill, "import sys\nsys.stdout.write('x' * 4096)\n")
    monkeypatch.setattr("skill_eval.evaluators.checks._MAX_VERIFIER_OUTPUT_BYTES", 1024)
    config = make_config(skill, tmp_path / "workspace")

    result = await evaluate_skill(config, runner=FakeRunner(pass_without=True))

    assert result.status == "error"
    assert "exceeded" in (result.message or "")
    stdout_paths = list(
        result.iteration_dirs[0].glob("eval-1/*/evidence/checks/*/stdout.txt")
    )
    assert stdout_paths
    assert all(path.stat().st_size <= 1024 for path in stdout_paths)
    assert any(path.stat().st_size == 1024 for path in stdout_paths)


def test_verifier_kill_uses_the_saved_process_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    killed = []

    def fail_pid_lookup(pid: int) -> int:
        raise AssertionError("a possibly reused PID must not be inspected")

    monkeypatch.setattr(os, "getpgid", fail_pid_lookup)
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: killed.append((pgid, sig)))

    _kill_group(12345)

    assert killed == [(12345, signal.SIGKILL)]


async def test_verifier_cleanup_preserves_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    waiting = anyio.Event()
    killed = []

    class HangingStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            await anyio.Event().wait()
            raise AssertionError("unreachable")

    class FakeProcess:
        pid = 987654
        returncode = None

        def __init__(self) -> None:
            self.stdout = HangingStream()
            self.stderr = HangingStream()
            self.wait_calls = 0
            self.close_calls = 0

        async def wait(self) -> int:
            self.wait_calls += 1
            if self.wait_calls == 1:
                waiting.set()
                await anyio.Event().wait()
            self.returncode = 0
            return 0

        async def aclose(self) -> None:
            self.close_calls += 1
            raise RuntimeError("close failure must not replace cancellation")

    process = FakeProcess()

    async def open_process(*args, **kwargs):
        return process

    monkeypatch.setattr("skill_eval.evaluators.checks.anyio.open_process", open_process)
    monkeypatch.setattr("skill_eval.evaluators.checks._kill_group", killed.append)
    bundle = tmp_path / "bundle"
    workspace = tmp_path / "work"
    outputs = tmp_path / "outputs"
    for directory in (bundle, workspace, outputs):
        directory.mkdir()
    (bundle / "verify.py").write_text("", encoding="utf-8")
    inputs = SkillCaseInput(
        case_id="1",
        prompt="Test cancellation.",
        arm="with_skill",
        workspace_dir=workspace,
        output_dir=outputs,
        raw_evidence_dir=tmp_path / "evidence",
        target_model="test:model",
    )
    check = CommandCheck(case="1", assertion="cancellation propagates", type="command")
    evaluator = VerifyCommand(
        checks=(check,), bundle_dir=bundle, case_id="1", arm="with_skill"
    )
    context = make_evaluator_context(inputs)
    task = asyncio.create_task(evaluator.evaluate(context))
    await waiting.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError), anyio.fail_after(2):
        await task

    assert killed == [process.pid]
    assert process.wait_calls == 2
    assert process.close_calls == 1


async def test_verifier_cancellation_during_spawn_still_cleans_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spawn_started = anyio.Event()
    release_spawn = anyio.Event()
    killed = []

    class FakeProcess:
        pid = 987655
        returncode = None
        stdout = None
        stderr = None

        def __init__(self) -> None:
            self.wait_calls = 0
            self.close_calls = 0

        async def wait(self) -> int:
            self.wait_calls += 1
            self.returncode = 0
            return 0

        async def aclose(self) -> None:
            self.close_calls += 1

    process = FakeProcess()

    async def open_process(*args, **kwargs):
        spawn_started.set()
        await release_spawn.wait()
        return process

    monkeypatch.setattr("skill_eval.evaluators.checks.anyio.open_process", open_process)
    monkeypatch.setattr("skill_eval.evaluators.checks._kill_group", killed.append)
    evaluator, ctx = _direct_verifier(tmp_path)
    task = asyncio.create_task(evaluator.evaluate(ctx))
    await spawn_started.wait()

    task.cancel()
    release_spawn.set()
    with pytest.raises(asyncio.CancelledError), anyio.fail_after(2):
        await task

    assert killed == [process.pid]
    assert process.wait_calls == 1
    assert process.close_calls == 1
