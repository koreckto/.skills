import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anyio

from skill_eval._artifacts import allocate_iteration
from skill_eval._datasets import copy_evaluation_bundle, hash_tree
from skill_eval.api import evaluate_skill
from skill_eval.models import RunObservation, RunRequest
from tests.conftest import FakeRunner, make_config


class BadFileRunner(FakeRunner):
    def __init__(self, kind: str) -> None:
        super().__init__(pass_without=True)
        self.kind = kind

    async def run(self, request: RunRequest) -> RunObservation:
        observation = await super().run(request)
        if request.arm == "with_skill":
            await self._change_chart(request)
        return observation

    async def _change_chart(self, request: RunRequest) -> None:
        chart = anyio.Path(request.workspace_dir / "outputs" / "chart.png")
        if self.kind == "symlink":
            await chart.unlink()
            await chart.symlink_to("/etc/passwd")
        elif self.kind == "empty":
            await chart.write_bytes(b"")


async def test_file_exists_rejects_symlink(sample_skill: Path, tmp_path: Path) -> None:
    config = make_config(sample_skill, tmp_path / "workspace")
    result = await evaluate_skill(config, runner=BadFileRunner("symlink"))
    grading = json.loads(
        (result.iteration_dirs[0] / "eval-1" / "with_skill" / "grading.json").read_text(
            encoding="utf-8"
        )
    )
    assert result.status == "failed"
    chart = result.iteration_dirs[0] / "eval-1" / "with_skill" / "outputs" / "chart.png"
    assert chart.is_symlink()
    assert chart.readlink() == Path("/etc/passwd")
    assert any(
        "not a regular file" in item["evidence"]
        for item in grading["assertion_results"]
    )


async def test_file_exists_rejects_empty_file(
    sample_skill: Path, tmp_path: Path
) -> None:
    config = make_config(sample_skill, tmp_path / "workspace")
    result = await evaluate_skill(config, runner=BadFileRunner("empty"))
    grading = json.loads(
        (result.iteration_dirs[0] / "eval-1" / "with_skill" / "grading.json").read_text(
            encoding="utf-8"
        )
    )
    assert result.status == "failed"
    assert any(
        "output is empty" in item["evidence"] for item in grading["assertion_results"]
    )


async def test_verifier_evidence_is_truncated_in_grading(
    sample_skill: Path, tmp_path: Path
) -> None:
    skill = tmp_path / "sample-skill"
    shutil.copytree(sample_skill, skill)
    (skill / "evals" / "verify.py").write_text(
        "import sys\nprint('x' * 20000)\nsys.exit(0)\n",
        encoding="utf-8",
    )
    config = make_config(skill, tmp_path / "workspace")
    result = await evaluate_skill(config, runner=FakeRunner(pass_without=True))
    grading = json.loads(
        (result.iteration_dirs[0] / "eval-1" / "with_skill" / "grading.json").read_text(
            encoding="utf-8"
        )
    )
    evidence = next(
        item["evidence"]
        for item in grading["assertion_results"]
        if item["text"] == "result.json is valid JSON."
    )
    assert result.status == "passed"
    assert "[truncated " in evidence
    assert len(evidence) < 10000
    stdout_path = next(
        result.iteration_dirs[0].glob("eval-1/with_skill/evidence/checks/*/stdout.txt")
    )
    assert stdout_path.read_text(encoding="utf-8") == "x" * 20000 + "\n"


def test_hash_tree_helper_file_added_changes_bundle_hash(
    sample_skill: Path, tmp_path: Path
) -> None:
    bundle = copy_evaluation_bundle(sample_skill, tmp_path / "bundle")
    original = bundle.content_hash
    (tmp_path / "bundle" / "helper.py").write_text("VALUE = 2\n", encoding="utf-8")
    assert hash_tree(tmp_path / "bundle") != original


def test_allocate_iteration_concurrent_allocations_return_unique_directories(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"

    def allocate(_: int) -> Path:
        return allocate_iteration(workspace)[1]

    with ThreadPoolExecutor(max_workers=8) as pool:
        paths = list(pool.map(allocate, range(8)))
    assert len(set(paths)) == 8
    assert all(path.name.startswith("iteration-") for path in paths)


async def test_verifier_logs_do_not_collide_for_similar_assertions(
    sample_skill: Path, tmp_path: Path
) -> None:
    skill = tmp_path / "sample-skill"
    shutil.copytree(sample_skill, skill)
    eval_file = skill / "evals" / "evals.json"
    raw = json.loads(eval_file.read_text(encoding="utf-8"))
    raw["evals"][0]["assertions"].append("result.json is valid JSON!")
    eval_file.write_text(json.dumps(raw), encoding="utf-8")
    config_file = skill / "evals" / "skill-eval.yaml"
    config_file.write_text(
        config_file.read_text(encoding="utf-8").replace(
            "gates:\n",
            '  - case: "1"\n'
            "    assertion: result.json is valid JSON!\n"
            "    type: command\n"
            "    timeout_seconds: 5\n\n"
            "gates:\n",
        ),
        encoding="utf-8",
    )
    config = make_config(skill, tmp_path / "workspace")

    result = await evaluate_skill(config, runner=FakeRunner(pass_without=True))

    checks_dir = (
        result.iteration_dirs[0] / "eval-1" / "with_skill" / "evidence" / "checks"
    )
    stdout_paths = list(checks_dir.glob("*/stdout.txt"))
    output = "\n".join(path.read_text(encoding="utf-8") for path in stdout_paths)
    assert len(stdout_paths) == 2
    assert "valid JSON object" in output
    assert "unsupported assertion" in output
