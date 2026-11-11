"""Deterministic skill-trigger scoring."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic_evals.evaluators import EvaluationReason, Evaluator

from skill_eval.models import RunObservation, SkillCaseInput, SkillCaseMetadata

if TYPE_CHECKING:
    from skill_eval.models import SkillEvaluatorContext


@dataclass
class SkillTrigger(Evaluator[SkillCaseInput, RunObservation, SkillCaseMetadata]):
    """Check whether the target skill loaded for a positive or negative trigger case."""

    skill_name: str
    """Name of the skill whose load status is evaluated."""
    should_trigger: bool
    """Whether the case expects the skill to load."""

    def evaluate(
        self,
        ctx: "SkillEvaluatorContext",
    ) -> dict[str, EvaluationReason]:
        """Return whether the target skill was loaded as expected.

        Args:
            ctx (SkillEvaluatorContext):
                Evaluation context containing normalized skill-load evidence.

        Returns:
            dict[str, EvaluationReason]:
                Expected-versus-observed trigger verdict and loaded skill names.
        """
        loaded = {
            record.name
            for record in ctx.output.loaded_skills
            if record.status == "success"
        }
        triggered = self.skill_name in loaded
        passed = triggered is self.should_trigger
        expected = (
            "load the skill" if self.should_trigger else "leave the skill unloaded"
        )
        observed = "loaded" if triggered else "not loaded"
        return {
            "trigger": EvaluationReason(
                passed,
                f"expected to {expected}; observed {observed}. loaded={sorted(loaded)}",
            )
        }
