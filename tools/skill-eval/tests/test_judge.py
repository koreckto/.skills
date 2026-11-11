from pathlib import Path

import anyio
import pytest
from pydantic_evals import Case, Dataset

from skill_eval.evaluators import EvidenceJudge, JudgeVerdict, JudgeVerdicts
from skill_eval.evaluators.evidence_judge import _read_preview, _verdicts_by_assertion
from skill_eval.exceptions import VerifierError
from skill_eval.models import (
    RunnerInfo,
    RunObservation,
    SkillCaseInput,
    SkillCaseMetadata,
    UsageRecord,
)
from tests.conftest import make_evaluator_context


def _case(
    root: Path, assertions: tuple[str, ...]
) -> tuple[SkillCaseInput, SkillCaseMetadata]:
    output = root / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    (output / "answer.txt").write_text("concrete answer\n", encoding="utf-8")
    inputs = SkillCaseInput(
        case_id="1",
        prompt="Do the task.",
        arm="with_skill",
        workspace_dir=root / "work",
        output_dir=output,
        raw_evidence_dir=root / "evidence",
        target_model="test:model",
        judge_model="test:judge",
    )
    metadata = SkillCaseMetadata(
        eval_id="1",
        eval_dir_name="eval-1",
        expected_output="A concrete answer.",
        assertions=assertions,
        arm="with_skill",
    )
    return inputs, metadata


async def test_judge_grades_uncovered_assertion(tmp_path: Path) -> None:
    inputs, metadata = _case(tmp_path, ("The answer is concrete.",))
    observation = RunObservation(
        response="concrete answer",
        raw_evidence_dir=inputs.raw_evidence_dir,
        output_dir=inputs.output_dir,
        runner=RunnerInfo(name="fake", version="1"),
        usage=UsageRecord(),
    )

    async def judge(prompt: str) -> JudgeVerdicts:
        assert "The answer is concrete." in prompt
        return JudgeVerdicts(
            verdicts=[
                JudgeVerdict(
                    assertion="The answer is concrete.",
                    passed=True,
                    evidence="answer.txt contains 'concrete answer'",
                )
            ]
        )

    dataset = Dataset[SkillCaseInput, RunObservation, SkillCaseMetadata](
        name="judge-test",
        cases=[
            Case[SkillCaseInput, RunObservation, SkillCaseMetadata](
                name="eval-1",
                inputs=inputs,
                metadata=metadata,
                evaluators=[
                    EvidenceJudge(
                        assertions=metadata.assertions,
                        judge_model="test:judge",
                        expected_output=metadata.expected_output,
                        judge_fn=judge,
                    )
                ],
            )
        ],
    )
    report = await dataset.evaluate(lambda _inputs: observation, progress=False)
    assert report.cases[0].assertions["The answer is concrete."].value is True


async def test_judge_empty_evidence_cannot_pass(tmp_path: Path) -> None:
    inputs, metadata = _case(tmp_path, ("The answer is concrete.",))
    observation = RunObservation(
        response="concrete answer",
        raw_evidence_dir=inputs.raw_evidence_dir,
        output_dir=inputs.output_dir,
        runner=RunnerInfo(name="fake", version="1"),
        usage=UsageRecord(),
    )

    async def judge(prompt: str) -> JudgeVerdicts:
        return JudgeVerdicts(
            verdicts=[
                JudgeVerdict(
                    assertion="The answer is concrete.", passed=True, evidence=""
                )
            ]
        )

    dataset = Dataset[SkillCaseInput, RunObservation, SkillCaseMetadata](
        name="judge-empty",
        cases=[
            Case[SkillCaseInput, RunObservation, SkillCaseMetadata](
                name="eval-1",
                inputs=inputs,
                metadata=metadata,
                evaluators=[
                    EvidenceJudge(
                        assertions=metadata.assertions,
                        judge_model="test:judge",
                        expected_output=metadata.expected_output,
                        judge_fn=judge,
                    )
                ],
            )
        ],
    )
    report = await dataset.evaluate(lambda _inputs: observation, progress=False)
    assert report.cases[0].assertions["The answer is concrete."].value is False
    assert "empty evidence" in (
        report.cases[0].assertions["The answer is concrete."].reason or ""
    )


async def test_judge_timeout_is_evaluator_error(tmp_path: Path) -> None:
    inputs, metadata = _case(tmp_path, ("The answer is concrete.",))
    observation = RunObservation(
        response="concrete answer",
        raw_evidence_dir=inputs.raw_evidence_dir,
        output_dir=inputs.output_dir,
        runner=RunnerInfo(name="fake", version="1"),
        usage=UsageRecord(),
    )

    async def judge(prompt: str) -> JudgeVerdicts:
        await anyio.Event().wait()
        raise AssertionError("unreachable")

    dataset = Dataset[SkillCaseInput, RunObservation, SkillCaseMetadata](
        name="judge-timeout",
        cases=[
            Case[SkillCaseInput, RunObservation, SkillCaseMetadata](
                name="eval-1",
                inputs=inputs,
                metadata=metadata,
                evaluators=[
                    EvidenceJudge(
                        assertions=metadata.assertions,
                        judge_model="test:judge",
                        expected_output=metadata.expected_output,
                        judge_fn=judge,
                        timeout_seconds=0,
                    )
                ],
            )
        ],
    )

    report = await dataset.evaluate(lambda _inputs: observation, progress=False)

    failures = report.cases[0].evaluator_failures
    assert len(failures) == 1
    assert "judge timed out" in failures[0].error_message


async def test_judge_repeated_assertion_verdict_is_an_error(tmp_path: Path) -> None:
    assertion = "The answer is concrete."
    inputs, metadata = _case(tmp_path, (assertion,))
    observation = RunObservation(
        response="concrete answer",
        raw_evidence_dir=inputs.raw_evidence_dir,
        output_dir=inputs.output_dir,
        runner=RunnerInfo(name="fake", version="1"),
        usage=UsageRecord(),
    )

    async def judge(prompt: str) -> JudgeVerdicts:
        return JudgeVerdicts(
            verdicts=[
                JudgeVerdict(assertion=assertion, passed=True, evidence="first"),
                JudgeVerdict(assertion=assertion, passed=False, evidence="second"),
            ]
        )

    evaluator = EvidenceJudge(
        assertions=(assertion,),
        judge_model="test:judge",
        expected_output=metadata.expected_output,
        judge_fn=judge,
    )
    ctx = make_evaluator_context(
        inputs,
        output=observation,
        metadata=metadata,
        attributes={"outputs_inventory": []},
    )
    with pytest.raises(VerifierError, match="duplicate"):
        await evaluator.evaluate(ctx)


def test_judge_missing_and_extra_verdicts_remain_an_error() -> None:
    verdicts = JudgeVerdicts(
        verdicts=[JudgeVerdict(assertion="unexpected", passed=True, evidence="x")]
    )

    with pytest.raises(VerifierError, match=r"missing=.*expected.*extra=.*unexpected"):
        _verdicts_by_assertion(verdicts, ("expected",))


@pytest.mark.parametrize(
    ("contents", "expected"),
    [
        (b"a" * 1997 + "€".encode(), "a" * 1997 + "€"),
        (b"a" * 1999 + "€".encode() + b"tail", "a" * 1999),
    ],
)
def test_preview_preserves_utf8_at_byte_limit(
    tmp_path: Path, contents: bytes, expected: str
) -> None:
    path = tmp_path / "preview.txt"
    path.write_bytes(contents)

    assert _read_preview(path) == expected


def test_preview_reads_only_a_bounded_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "large.txt"
    path.write_bytes(b"x" * 2000 + b"y" * 5_000_000)

    def reject_whole_file_read(self: Path) -> bytes:
        raise AssertionError("preview must not read the whole file")

    monkeypatch.setattr(Path, "read_bytes", reject_whole_file_read)

    assert _read_preview(path) == "x" * 2000
