"""LLM judge for assertions not covered by deterministic checks."""

import codecs
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import anyio
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_evals.evaluators import EvaluationReason, Evaluator

from skill_eval._helpers import run_in_thread, tail_text, write_json
from skill_eval.exceptions import VerifierError
from skill_eval.models import RunObservation, SkillCaseInput, SkillCaseMetadata

if TYPE_CHECKING:
    from pathlib import Path

    from pydantic_ai.models import Model

    from skill_eval.models import SkillEvaluatorContext


class JudgeVerdict(BaseModel):
    """One assertion verdict from the judge."""

    assertion: str = Field(min_length=1)
    """Exact assertion text being graded."""
    passed: bool
    """Whether the evidence satisfies the assertion."""
    evidence: str = ""
    """Concrete evidence supporting the verdict."""


class JudgeVerdicts(BaseModel):
    """Structured judge output."""

    verdicts: list[JudgeVerdict] = Field(default_factory=list)
    """Assertion verdicts returned by the judge."""


type JudgeCallable = Callable[[str], Awaitable[JudgeVerdicts]]


@dataclass
class EvidenceJudge(Evaluator[SkillCaseInput, RunObservation, SkillCaseMetadata]):
    """Grade uncovered assertions from answers, inventory and previews."""

    assertions: tuple[str, ...]
    """Assertions not covered by deterministic checks."""
    judge_model: str
    """Model identifier used for judging."""
    expected_output: str
    """Expected output description supplied to the judge."""
    timeout_seconds: float = 600
    """Maximum judge duration in seconds."""
    model: "Model | None" = None
    """Optional model instance overriding ``judge_model``."""
    judge_fn: JudgeCallable | None = field(default=None, repr=False)
    """Optional injected judge callable used instead of an agent."""

    async def evaluate(
        self,
        ctx: "SkillEvaluatorContext",
    ) -> dict[str, EvaluationReason]:
        """Grade only the assertions left uncovered by deterministic checks.

        Args:
            ctx (SkillEvaluatorContext):
                Evaluation context containing the run observation and output inventory.

        Returns:
            dict[str, EvaluationReason]:
                Judged verdicts and concrete evidence keyed by assertion text.

        Raises:
            VerifierError:
                If evidence preparation or judging fails, times out or returns
                invalid coverage.
        """
        if not self.assertions:
            return {}
        error = ctx.attributes.get("outputs_inventory_error")
        if error:
            raise VerifierError(f"cannot prepare judge evidence: {error}")
        inventory = ctx.attributes.get("outputs_inventory") or []
        previews = await run_in_thread(_previews, ctx.inputs.output_dir, inventory)
        prompt = _judge_prompt(
            ctx.inputs.prompt,
            self.expected_output,
            ctx.output.response,
            inventory,
            previews,
            self.assertions,
        )
        try:
            with anyio.fail_after(self.timeout_seconds):
                verdicts = await self._judge(prompt)
        except TimeoutError as err:
            raise VerifierError(
                f"judge timed out after {self.timeout_seconds:g}s"
            ) from err
        except Exception as err:
            raise VerifierError(f"judge failed: {err}") from err

        await write_json(
            ctx.inputs.raw_evidence_dir / "judge.json",
            {
                "model": self.judge_model,
                "prompt": prompt,
                "verdicts": verdicts.model_dump(mode="json"),
            },
        )
        by_assertion = _verdicts_by_assertion(verdicts, self.assertions)
        results: dict[str, EvaluationReason] = {}
        for assertion in self.assertions:
            verdict = by_assertion[assertion]
            evidence = verdict.evidence.strip()
            passed = verdict.passed
            if passed and not evidence:
                passed = False
                evidence = "empty evidence cannot be a PASS"
            if not evidence:
                evidence = "judge returned no evidence"
            results[assertion] = EvaluationReason(passed, tail_text(evidence))
        return results

    async def _judge(self, prompt: str) -> JudgeVerdicts:
        if self.judge_fn is not None:
            return await self.judge_fn(prompt)
        agent = Agent(
            self.model or self.judge_model,
            output_type=JudgeVerdicts,
            instructions=(
                "You are a strict evaluation judge. Return one verdict for every "
                "assertion, using only the supplied response, inventory and previews. "
                "A PASS needs concrete evidence."
            ),
        )
        result = await agent.run(prompt)
        return result.output


def _verdicts_by_assertion(
    verdicts: JudgeVerdicts, assertions: tuple[str, ...]
) -> dict[str, JudgeVerdict]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for verdict in verdicts.verdicts:
        if verdict.assertion in seen and verdict.assertion not in duplicates:
            duplicates.append(verdict.assertion)
        seen.add(verdict.assertion)
    if duplicates:
        raise VerifierError(
            f"judge returned duplicate assertion verdicts: {duplicates!r}"
        )

    by_assertion = {verdict.assertion: verdict for verdict in verdicts.verdicts}
    missing = [assertion for assertion in assertions if assertion not in by_assertion]
    extra = [assertion for assertion in by_assertion if assertion not in assertions]
    if missing or extra:
        raise VerifierError(
            f"judge returned incorrect assertion coverage: "
            f"missing={missing!r}, extra={extra!r}"
        )
    return by_assertion


def _judge_prompt(
    task: str,
    expected_output: str,
    response: str,
    inventory: list[dict[str, object]],
    previews: dict[str, str],
    assertions: tuple[str, ...],
) -> str:
    inventory_lines = (
        "\n".join(
            f"- {item.get('path')} ({item.get('type')}, {item.get('size')} bytes)"
            for item in inventory
        )
        or "(no generated files)"
    )
    preview_blocks = (
        "\n\n".join(f"--- {path} ---\n{content}" for path, content in previews.items())
        or "(no text previews)"
    )
    assertion_lines = "\n".join(
        f"{index}. {assertion}" for index, assertion in enumerate(assertions, 1)
    )
    return (
        f"Task:\n{task}\n\n"
        f"Expected output:\n{expected_output}\n\n"
        f"Final response:\n{response}\n\n"
        f"Generated files:\n{inventory_lines}\n\n"
        f"Limited file previews:\n{preview_blocks}\n\n"
        f"Assertions to grade:\n{assertion_lines}\n\n"
        "Return a verdict for every assertion, quoting or referencing concrete "
        "evidence. "
        "Do not pass an assertion when the evidence is empty or speculative."
    )


def _read_preview(path: "Path") -> str | None:
    decoder = codecs.getincrementaldecoder("utf-8")(errors="strict")
    with contextlib.suppress(OSError, UnicodeDecodeError):
        with path.open("rb") as handle:
            data = handle.read(2000)
            at_eof = len(data) < 2000 or not handle.read(1)
        return decoder.decode(data, final=at_eof)
    return None


def _previews(output_dir: "Path", inventory: list[dict[str, object]]) -> dict[str, str]:
    previews: dict[str, str] = {}
    for item in inventory:
        if len(previews) >= 8:
            break
        if item.get("type") != "file":
            continue
        relative = str(item.get("path") or "")
        if not relative:
            continue
        text = _read_preview(output_dir / relative)
        if text is None:
            continue
        previews[relative] = text
    return previews
