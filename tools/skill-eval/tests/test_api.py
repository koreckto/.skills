import json
import shutil
from pathlib import Path

import anyio
import pytest

from skill_eval._datasets import hash_tree
from skill_eval.api import evaluate_skill, load_eval_dataset
from skill_eval.evaluators import EvidenceJudge, JudgeVerdict, JudgeVerdicts
from skill_eval.exceptions import ConfigError
from skill_eval.models import GateConfig, RunObservation, RunRequest, SandboxConfig
from tests.conftest import FakeRunner, make_config


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


async def _no_sleep(_delay_seconds: float) -> None:
    pass


# ==================================================================================
# Output-quality behavior
# ==================================================================================


async def test_output_quality_success_writes_grading_outputs_and_benchmarks(
    sample_skill: Path, tmp_path: Path
) -> None:
    config = make_config(sample_skill, tmp_path / "workspace")
    result = await evaluate_skill(config, runner=FakeRunner(pass_without=False))

    assert result.status == "passed"
    assert result.pass_rate == 1.0
    assert len(result.iteration_dirs) == 1
    iteration = result.iteration_dirs[0]
    with_skill = iteration / "eval-1" / "with_skill"
    without_skill = iteration / "eval-1" / "without_skill"

    with_grading = _read(with_skill / "grading.json")
    assert with_grading["summary"]["passed"] == 2
    assert with_grading["summary"]["failed"] == 0
    assert (with_skill / "outputs" / "chart.png").read_bytes() == (
        b"\x89PNG\r\n\x1a\nfake"
    )
    assert (with_skill / "outputs" / "result.json").read_text(
        encoding="utf-8"
    ) == '{"ok": true}\n'
    assert not (iteration / ".work" / "eval-1" / "with_skill").exists()

    without_grading = _read(without_skill / "grading.json")
    assert without_grading["summary"]["passed"] == 0
    assert without_grading["summary"]["failed"] == 2

    benchmark = _read(iteration / "benchmark.json")
    assert benchmark["run_summary"]["with_skill"]["pass_rate"]["mean"] == 1.0
    assert benchmark["run_summary"]["without_skill"]["pass_rate"]["mean"] == 0.0
    assert benchmark["delta"]["pass_rate"] == 1.0

    manifest = _read(result.experiment_dir / "manifest.json")
    assert manifest["complete"] is True
    assert manifest["status"] == "passed"
    assert manifest["evaluation_bundle_hash"]
    assert manifest["runner"] == "fake"
    assert manifest["case_ids"] == ["1", "2"]
    iteration_manifest = _read(iteration / "skill-eval-manifest.json")
    assert iteration_manifest["runner"] == "fake"
    assert (result.experiment_dir / "evaluation-bundle" / "evals.json").is_file()
    assert not list(iteration.rglob("judge.json"))


async def test_output_quality_all_assertions_pass_marks_experiment_passed(
    sample_skill: Path, tmp_path: Path
) -> None:
    config = make_config(sample_skill, tmp_path / "workspace")
    result = await evaluate_skill(config, runner=FakeRunner(pass_without=True))

    assert result.status == "passed"
    assert result.pass_rate == 1.0
    benchmark = _read(result.experiment_dir / "benchmark.json")
    assert benchmark["run_summary"]["with_skill"]["pass_rate"]["stddev"] is None


async def test_output_quality_judge_case_without_expected_output_preserves_rubric(
    sample_skill: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skill = tmp_path / "sample-skill"
    shutil.copytree(sample_skill, skill)
    eval_file = skill / "evals" / "evals.json"
    raw = json.loads(eval_file.read_text(encoding="utf-8"))
    assertion = "The response is a short sentence."
    raw["evals"][1]["assertions"] = [assertion]
    eval_file.write_text(json.dumps(raw), encoding="utf-8")
    judge_prompts: list[str] = []

    async def fake_judge(self: EvidenceJudge, prompt: str) -> JudgeVerdicts:
        judge_prompts.append(prompt)
        return JudgeVerdicts(
            verdicts=[
                JudgeVerdict(
                    assertion=case_assertion,
                    passed=True,
                    evidence="The response is one short sentence.",
                )
                for case_assertion in self.assertions
            ]
        )

    monkeypatch.setattr(EvidenceJudge, "_judge", fake_judge)
    config = make_config(
        skill,
        tmp_path / "workspace",
        baseline="none",
        case_ids=("2",),
    )

    result = await evaluate_skill(config, runner=FakeRunner())

    assert result.status == "passed"
    report_case = result.reports[0].cases[0]
    assert isinstance(report_case.output, RunObservation)
    assert report_case.expected_output is None
    report_metadata = report_case.metadata
    assert report_metadata is not None
    assert report_metadata.expected_output == "A short sentence."
    assert report_case.assertions[assertion].value is True
    grading = _read(result.iteration_dirs[0] / "eval-2" / "with_skill" / "grading.json")
    assert grading["summary"]["passed"] == 1
    assert grading["summary"]["failed"] == 0
    assert len(judge_prompts) == 1
    assert "Expected output:\nA short sentence." in judge_prompts[0]


async def test_repeated_experiment_two_iterations_aggregates_metrics_and_manifest_map(
    sample_skill: Path, tmp_path: Path
) -> None:
    config = make_config(sample_skill, tmp_path / "workspace", repeat=2)
    result = await evaluate_skill(config, runner=FakeRunner(pass_without=True))

    assert result.status == "passed"
    assert len(result.iteration_dirs) == 2
    manifest = _read(result.experiment_dir / "manifest.json")
    assert manifest["iteration_map"].keys() == {"1", "2"}
    benchmark = _read(result.experiment_dir / "benchmark.json")
    assert benchmark["iterations"] == 2
    assert benchmark["stddev_method"] == "sample"
    assert benchmark["run_summary"]["with_skill"]["pass_rate"]["stddev"] == 0.0


async def test_skill_baseline_old_skill_deploys_distinct_baseline_snapshot(
    sample_skill: Path, tmp_path: Path
) -> None:
    baseline = tmp_path / "baseline-input" / "legacy-skill"
    shutil.copytree(sample_skill, baseline)
    baseline_skill_file = baseline / "SKILL.md"
    baseline_contents = (
        baseline_skill_file.read_text(encoding="utf-8")
        .replace("name: sample-skill", "name: legacy-skill", 1)
        .replace("# Sample Skill", "# Legacy Skill", 1)
        + "\nThis legacy baseline has materially different instructions.\n"
    )
    baseline_skill_file.write_text(baseline_contents, encoding="utf-8")
    baseline_evals = baseline / "evals" / "evals.json"
    baseline_evals.write_text(
        baseline_evals.read_text(encoding="utf-8").replace(
            '"skill_name": "sample-skill"', '"skill_name": "legacy-skill"', 1
        ),
        encoding="utf-8",
    )
    candidate_contents = (sample_skill / "SKILL.md").read_text(encoding="utf-8")
    candidate_hash = hash_tree(sample_skill)
    baseline_hash = hash_tree(baseline)
    deployments: dict[str, tuple[str, Path, str, str]] = {}

    class BaselineRecordingRunner(FakeRunner):
        async def run(self, request: RunRequest) -> RunObservation:
            assert request.skill is not None
            deployed_skill = (
                request.workspace_dir / "skills" / request.skill.name / "SKILL.md"
            )
            deployments[request.arm] = (
                request.skill.name,
                request.skill.snapshot_path,
                request.skill.content_hash,
                deployed_skill.read_text(encoding="utf-8"),
            )
            return await super().run(request)

    config = make_config(
        sample_skill,
        tmp_path / "workspace",
        baseline="skill",
        baseline_skill=baseline,
    )
    result = await evaluate_skill(
        config, runner=BaselineRecordingRunner(pass_without=True)
    )

    assert result.status == "passed"
    benchmark = _read(result.experiment_dir / "benchmark.json")
    assert "old_skill" in benchmark["run_summary"]
    assert "without_skill" not in benchmark["run_summary"]
    candidate = deployments["with_skill"]
    old_skill = deployments["old_skill"]
    baseline_snapshot = result.experiment_dir / "inputs" / "baseline" / "legacy-skill"
    assert candidate[0] == "sample-skill"
    assert candidate[2] == candidate_hash
    assert candidate[3] == candidate_contents
    assert old_skill[0] == "legacy-skill"
    assert old_skill[1] == baseline_snapshot
    assert old_skill[2] == baseline_hash == hash_tree(baseline_snapshot)
    assert old_skill[2] != candidate[2]
    assert old_skill[3] == baseline_contents != candidate_contents


async def test_trigger_suite_expected_load_outcomes_passes_and_writes_grading(
    sample_skill: Path, tmp_path: Path
) -> None:
    config = make_config(sample_skill, tmp_path / "workspace", suite="trigger")
    result = await evaluate_skill(config, runner=FakeRunner())

    assert result.status == "passed"
    iteration = result.iteration_dirs[0]
    assert (iteration / "eval-should-trigger" / "grading.json").is_file()
    grading = _read(iteration / "eval-should-not-trigger" / "grading.json")
    assert grading["summary"]["passed"] == 1


async def test_docker_sandbox_is_not_silently_downgraded(
    sample_skill: Path, tmp_path: Path
) -> None:
    config = make_config(sample_skill, tmp_path / "workspace")
    config = config.model_copy(
        update={
            "sandbox": SandboxConfig(kind="docker", image="example@sha256:deadbeef")
        }
    )
    with pytest.raises(ConfigError, match="Docker sandbox"):
        await evaluate_skill(config, runner=FakeRunner())


async def test_forced_mode_is_rejected(sample_skill: Path, tmp_path: Path) -> None:
    config = make_config(sample_skill, tmp_path / "workspace")
    config = config.model_copy(update={"mode": "forced"})
    with pytest.raises(ConfigError, match="forced"):
        await evaluate_skill(config, runner=FakeRunner())


async def test_unknown_case_is_rejected(sample_skill: Path, tmp_path: Path) -> None:
    config = make_config(sample_skill, tmp_path / "workspace", case_ids=("missing",))
    with pytest.raises(ConfigError, match="unknown eval case"):
        await evaluate_skill(config, runner=FakeRunner())


async def test_no_assertions_is_ungraded(sample_skill: Path, tmp_path: Path) -> None:
    skill = tmp_path / "sample-skill"
    shutil.copytree(sample_skill, skill)
    eval_file = skill / "evals" / "evals.json"
    raw = json.loads(eval_file.read_text(encoding="utf-8"))
    raw["evals"] = raw["evals"][:1]
    raw["evals"][0]["assertions"] = []
    eval_file.write_text(json.dumps(raw), encoding="utf-8")
    config_file = skill / "evals" / "skill-eval.yaml"
    config_file.write_text(
        "version: 1\ngates:\n  min_pass_rate: 0.9\n", encoding="utf-8"
    )

    config = make_config(skill, tmp_path / "workspace")
    result = await evaluate_skill(config, runner=FakeRunner(pass_without=True))

    assert result.status == "ungraded"
    assert result.pass_rate is None
    benchmark = _read(result.experiment_dir / "benchmark.json")
    with_skill = benchmark["run_summary"]["with_skill"]
    assert with_skill["pass_rate"]["mean"] is None
    assert with_skill["time_seconds"]["n"] == 1
    assert with_skill["time_seconds"]["mean"] > 0
    assert with_skill["tokens"]["n"] == 1
    assert with_skill["tokens"]["mean"] == 150


# ==================================================================================
# Retry and snapshot behavior
# ==================================================================================


class FlakyRunner(FakeRunner):
    def __init__(self) -> None:
        super().__init__(pass_without=True)
        self.calls = 0

    async def run(self, request: RunRequest) -> RunObservation:
        self.calls += 1
        if self.calls == 1:
            raise ConnectionError("temporary transport failure")
        return await super().run(request)


async def test_transient_transport_error_is_retried(
    sample_skill: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("skill_eval.api.anyio.sleep", _no_sleep)
    config = make_config(sample_skill, tmp_path / "workspace")
    runner = FlakyRunner()
    result = await evaluate_skill(config, runner=runner)

    assert result.status == "passed"
    assert (
        runner.calls >= 3
    )  # one failed attempt plus the retry, then the remaining case(s)


class DirtyRetryRunner(FakeRunner):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def run(self, request: RunRequest) -> RunObservation:
        self.calls += 1
        assert request.skill is not None
        fixture = request.fixture_files[0]
        deployed_skill = (
            request.workspace_dir / "skills" / request.skill.name / "SKILL.md"
        )
        stale_evidence = request.raw_evidence_dir / "stale.json"
        if self.calls == 1:
            self.original_fixture = fixture.read_text(encoding="utf-8")
            self.original_deployed_skill = deployed_skill.read_text(encoding="utf-8")
            fixture.write_text("dirty fixture\n", encoding="utf-8")
            deployed_skill.write_text("dirty skill\n", encoding="utf-8")
            request.output_dir.mkdir(parents=True, exist_ok=True)
            request.raw_evidence_dir.mkdir(parents=True, exist_ok=True)
            stale_evidence.write_text("dirty evidence\n", encoding="utf-8")
            workspace_outputs = request.workspace_dir / "outputs"
            workspace_outputs.mkdir(parents=True, exist_ok=True)
            (request.output_dir / "chart.png").write_bytes(b"stale")
            (workspace_outputs / "chart.png").write_bytes(b"stale")
            raise ConnectionError("temporary transport failure")

        assert fixture.read_text(encoding="utf-8") == self.original_fixture
        assert (
            deployed_skill.read_text(encoding="utf-8") == self.original_deployed_skill
        )
        assert not stale_evidence.exists()
        assert not (request.output_dir / "chart.png").exists()
        assert not (request.workspace_dir / "outputs" / "chart.png").exists()
        request.raw_evidence_dir.mkdir(parents=True, exist_ok=True)
        workspace_outputs = request.workspace_dir / "outputs"
        workspace_outputs.mkdir(parents=True, exist_ok=True)
        (workspace_outputs / "result.json").write_text(
            '{"ok": true}\n', encoding="utf-8"
        )
        return RunObservation(
            response="done without a chart",
            raw_evidence_dir=request.raw_evidence_dir,
            output_dir=request.output_dir,
            runner=self.info,
        )


async def test_transient_retry_discards_failed_attempt_outputs(
    sample_skill: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("skill_eval.api.anyio.sleep", _no_sleep)
    config = make_config(
        sample_skill,
        tmp_path / "workspace",
        baseline="none",
        case_ids=("1",),
    )

    result = await evaluate_skill(config, runner=DirtyRetryRunner())

    iteration = result.iteration_dirs[0]
    case_dir = iteration / "eval-1" / "with_skill"
    assert not (case_dir / "outputs" / "chart.png").exists()
    grading = _read(case_dir / "grading.json")
    assert grading["assertion_results"][0]["passed"] is False
    assert grading["summary"]["passed"] == 1


class MutatingSourceRunner(FakeRunner):
    def __init__(self, source: Path) -> None:
        super().__init__()
        self.source = source
        self.calls = 0
        self.skill_contents: list[str] = []
        self.fixture_contents: list[str] = []
        self.content_hashes: list[str] = []

    async def run(self, request: RunRequest) -> RunObservation:
        assert request.skill is not None
        self.skill_contents.append(
            (request.skill.snapshot_path / "SKILL.md").read_text(encoding="utf-8")
        )
        self.fixture_contents.append(
            request.fixture_files[0].read_text(encoding="utf-8")
        )
        self.content_hashes.append(request.skill.content_hash)
        self.calls += 1
        if self.calls == 1:
            with (self.source / "SKILL.md").open("a", encoding="utf-8") as stream:
                stream.write("\nMutated after the first run.\n")
            (self.source / "evals" / "files" / "input.txt").write_text(
                "mutated fixture\n", encoding="utf-8"
            )
        return await super().run(request)


async def test_execution_uses_fixed_input_snapshots(
    sample_skill: Path, tmp_path: Path
) -> None:
    skill = tmp_path / "source" / "sample-skill"
    shutil.copytree(sample_skill, skill)
    original_skill = (skill / "SKILL.md").read_text(encoding="utf-8")
    original_fixture = (skill / "evals" / "files" / "input.txt").read_text(
        encoding="utf-8"
    )
    runner = MutatingSourceRunner(skill)
    config = make_config(
        skill,
        tmp_path / "workspace",
        baseline="none",
        case_ids=("1",),
        repeat=2,
    )

    result = await evaluate_skill(config, runner=runner)

    assert result.status == "passed"
    assert runner.skill_contents == [original_skill, original_skill]
    assert runner.fixture_contents == [original_fixture, original_fixture]
    assert len(set(runner.content_hashes)) == 1
    snapshot = (
        result.experiment_dir / "inputs" / "candidate" / "sample-skill" / "SKILL.md"
    )
    assert snapshot.read_text(encoding="utf-8") == original_skill


# ==================================================================================
# Workspace containment
# ==================================================================================


async def test_default_workspace_inside_skill_is_rejected_before_copying(
    sample_skill: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skill = tmp_path / "sample-skill"
    shutil.copytree(sample_skill, skill)
    monkeypatch.chdir(skill)
    config = make_config(skill, Path(".skill-eval"))

    with pytest.raises(ConfigError, match=r"workspace.*skill source"):
        await evaluate_skill(config, runner=FakeRunner())

    assert not (skill / ".skill-eval").exists()


async def test_workspace_containing_skill_is_rejected_before_experiment_creation(
    sample_skill: Path, tmp_path: Path
) -> None:
    skill = tmp_path / "sample-skill"
    shutil.copytree(sample_skill, skill)
    config = make_config(skill, tmp_path)

    with pytest.raises(ConfigError, match=r"workspace.*skill source"):
        await evaluate_skill(config, runner=FakeRunner())

    assert not (tmp_path / "experiments").exists()


async def test_workspace_inside_baseline_is_rejected_before_experiment_creation(
    sample_skill: Path, tmp_path: Path
) -> None:
    baseline = tmp_path / "baseline" / "sample-skill"
    shutil.copytree(sample_skill, baseline)
    workspace = baseline / ".skill-eval"
    config = make_config(
        sample_skill,
        workspace,
        baseline="skill",
        baseline_skill=baseline,
    )

    with pytest.raises(ConfigError, match=r"workspace.*skill source"):
        await evaluate_skill(config, runner=FakeRunner())

    assert not workspace.exists()


async def test_malicious_baseline_name_is_rejected_before_deployment(
    sample_skill: Path, tmp_path: Path
) -> None:
    baseline = tmp_path / "baseline" / "sample-skill"
    shutil.copytree(sample_skill, baseline)
    skill_file = baseline / "SKILL.md"
    skill_file.write_text(
        skill_file.read_text(encoding="utf-8").replace(
            "name: sample-skill", 'name: "../escaped"', 1
        ),
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    config = make_config(
        sample_skill,
        workspace,
        baseline="skill",
        baseline_skill=baseline,
    )

    with pytest.raises(ConfigError, match="baseline"):
        await evaluate_skill(config, runner=FakeRunner())

    assert not workspace.exists()


async def test_baseline_requires_valid_frontmatter(
    sample_skill: Path, tmp_path: Path
) -> None:
    baseline = tmp_path / "baseline" / "renamed-skill"
    shutil.copytree(sample_skill, baseline)
    workspace = tmp_path / "workspace"
    config = make_config(
        sample_skill,
        workspace,
        baseline="skill",
        baseline_skill=baseline,
    )

    with pytest.raises(ConfigError, match=r"baseline.*frontmatter"):
        await evaluate_skill(config, runner=FakeRunner())

    assert not workspace.exists()


# ==================================================================================
# Case filtering and gates
# ==================================================================================


def test_load_eval_dataset_valid_skill_preserves_case_ids(
    sample_skill: Path,
) -> None:
    dataset = load_eval_dataset(sample_skill)
    assert len(dataset.cases) == 2
    assert dataset.cases[0].inputs.case_id == "1"


async def test_case_filter_selected_eval_excludes_unselected_cases(
    sample_skill: Path, tmp_path: Path
) -> None:
    config = make_config(sample_skill, tmp_path / "workspace", case_ids=("1",))
    result = await evaluate_skill(config, runner=FakeRunner(pass_without=True))
    iteration = result.iteration_dirs[0]
    assert (iteration / "eval-1").is_dir()
    assert not (iteration / "eval-2").exists()
    manifest = _read(result.experiment_dir / "manifest.json")
    assert manifest["case_ids"] == ["1"]


class PartialPassRunner(FakeRunner):
    def __init__(self) -> None:
        super().__init__(pass_without=True, pass_with_skill=False)

    async def run(self, request: RunRequest) -> RunObservation:
        observation = await super().run(request)
        if request.arm == "with_skill":
            chart = request.workspace_dir / "outputs" / "chart.png"
            await anyio.Path(chart).write_bytes(b"partial")
        return observation


@pytest.mark.parametrize(("minimum", "expected"), [(0.5, "passed"), (0.51, "failed")])
async def test_min_pass_rate_controls_partial_pass_status(
    sample_skill: Path,
    tmp_path: Path,
    minimum: float,
    expected: str,
) -> None:
    config = make_config(
        sample_skill, tmp_path / "workspace", gates=GateConfig(min_pass_rate=minimum)
    )

    result = await evaluate_skill(config, runner=PartialPassRunner())

    assert result.pass_rate == 0.5
    assert result.status == expected


@pytest.mark.parametrize(("maximum", "expected"), [(0.25, "failed"), (0.5, "passed")])
async def test_max_regression_is_enforced_against_comparison_arm(
    sample_skill: Path,
    tmp_path: Path,
    maximum: float,
    expected: str,
) -> None:
    gates = GateConfig(min_pass_rate=0.5, max_regression=maximum)
    config = make_config(sample_skill, tmp_path / "workspace", gates=gates)

    result = await evaluate_skill(config, runner=PartialPassRunner())

    assert result.pass_rate == 0.5
    assert result.status == expected
    if expected == "failed":
        assert "regression" in (result.message or "")


async def test_regression_gate_requires_comparison_baseline(
    sample_skill: Path, tmp_path: Path
) -> None:
    config = make_config(
        sample_skill,
        tmp_path / "workspace",
        baseline="none",
        gates=GateConfig(max_regression=0.1),
    )

    with pytest.raises(ConfigError, match="requires a comparison baseline"):
        await evaluate_skill(config, runner=FakeRunner())


async def test_trigger_case_filter_selects_trigger_id(
    sample_skill: Path, tmp_path: Path
) -> None:
    config = make_config(
        sample_skill,
        tmp_path / "workspace",
        suite="trigger",
        case_ids=("should-trigger",),
    )

    result = await evaluate_skill(config, runner=FakeRunner())

    assert result.status == "passed"
    iteration = result.iteration_dirs[0]
    assert (iteration / "eval-should-trigger").is_dir()
    assert not (iteration / "eval-should-not-trigger").exists()
    manifest = _read(result.experiment_dir / "manifest.json")
    assert manifest["case_ids"] == ["should-trigger"]


async def test_unknown_trigger_case_is_rejected(
    sample_skill: Path, tmp_path: Path
) -> None:
    config = make_config(
        sample_skill,
        tmp_path / "workspace",
        suite="trigger",
        case_ids=("missing",),
    )

    with pytest.raises(ConfigError, match="unknown trigger case"):
        await evaluate_skill(config, runner=FakeRunner())


async def test_trigger_fixture_changes_dataset_hash(
    sample_skill: Path, tmp_path: Path
) -> None:
    skill = tmp_path / "sample-skill"
    shutil.copytree(sample_skill, skill)
    fixture = skill / "evals" / "files" / "trigger.txt"
    fixture.write_text("first fixture\n", encoding="utf-8")
    config_file = skill / "evals" / "skill-eval.yaml"
    config_file.write_text(
        config_file.read_text(encoding="utf-8").replace(
            "      should_trigger: true",
            '      files: ["evals/files/trigger.txt"]\n      should_trigger: true',
            1,
        ),
        encoding="utf-8",
    )

    first = await evaluate_skill(
        make_config(skill, tmp_path / "first", suite="trigger"), runner=FakeRunner()
    )
    fixture.write_text("second fixture\n", encoding="utf-8")
    second = await evaluate_skill(
        make_config(skill, tmp_path / "second", suite="trigger"), runner=FakeRunner()
    )

    first_manifest = _read(first.experiment_dir / "manifest.json")
    second_manifest = _read(second.experiment_dir / "manifest.json")
    assert first_manifest["dataset_hash"] != second_manifest["dataset_hash"]
    assert (
        first_manifest["evaluation_bundle_hash"]
        != second_manifest["evaluation_bundle_hash"]
    )
