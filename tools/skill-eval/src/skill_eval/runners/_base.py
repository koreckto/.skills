"""Runner protocol and explicit registry."""

from typing import TYPE_CHECKING, Protocol

from skill_eval.runners.pydantic_ai import PydanticAIRunner

if TYPE_CHECKING:
    from skill_eval.models import (
        RunnerCapabilities,
        RunnerInfo,
        RunObservation,
        RunRequest,
    )


class SkillRunner(Protocol):
    """One execution backend that returns normalized evidence."""

    @property
    def info(self) -> "RunnerInfo":
        """Return runner identity and version metadata.

        Returns:
            RunnerInfo:
                Stable runner identity, version and configuration summary.
        """
        ...

    @property
    def capabilities(self) -> "RunnerCapabilities":
        """Declare the evidence and invocation features this runner supports.

        Returns:
            RunnerCapabilities:
                Supported invocation, evidence and sandbox capabilities.
        """
        ...

    async def run(self, request: "RunRequest") -> "RunObservation":
        """Execute one isolated run and return normalized evidence.

        Args:
            request (RunRequest):
                Complete execution request for one case arm.

        Returns:
            RunObservation:
                Normalized response, evidence, usage and runner metadata.
        """
        ...


def create_runner(name: str) -> SkillRunner:
    """Create a runner by its stable registry name.

    Args:
        name (str):
            Registered runner name.

    Returns:
        SkillRunner:
            New runner instance.

    Raises:
        ValueError:
            If the registry name is unknown.
    """
    if name == "pydantic-ai":
        return PydanticAIRunner()
    raise ValueError(f"unknown runner: {name}")
