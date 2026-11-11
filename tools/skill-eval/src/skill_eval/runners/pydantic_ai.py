"""Pydantic AI runner using the harness Skills and Coder capabilities."""

import json
import posixpath
from importlib.metadata import version
from typing import TYPE_CHECKING, Any, cast

import anyio
from pydantic_ai import Agent, capture_run_messages
from pydantic_ai.capabilities import LocalWorkspace
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.workspaces import LocalWorkspaceBackend, Workspace
from pydantic_ai_harness import Skills
from pydantic_ai_harness._workspace import metadata_dir
from pydantic_ai_harness.coder import Coder
from pydantic_ai_harness.shell._jobs import Job
from pydantic_core import to_jsonable_python

from skill_eval.exceptions import ConfigError, EvaluationExecutionError
from skill_eval.models import (
    RunnerCapabilities,
    RunnerInfo,
    RunObservation,
    RunRequest,
    RunStatus,
    SkillLoadRecord,
    ToolCallRecord,
    UsageRecord,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from pydantic_ai.models import Model
    from pydantic_ai.run import AgentRunResult
    from pydantic_ai.settings import ModelSettings
    from pydantic_ai.usage import RunUsage

_INSTRUCTIONS = """You are completing an isolated evaluation task.
Use the available tools to inspect the workspace and finish the task. Save every
generated file under the `outputs/` directory in the workspace. Do not ask the
user questions; make reasonable assumptions.
"""
_CODER_JOB_REATTACH_SECONDS = 0.25
_CODER_JOB_REATTACH_POLL_SECONDS = 0.01


class PydanticAIRunner:
    """Run an Agent Skills task with Pydantic AI and the harness Coder."""

    def __init__(self, model: "Model | None" = None) -> None:
        self._model = model

    @property
    def info(self) -> RunnerInfo:
        """Return the Pydantic AI runner identity and pinned versions.

        Returns:
            RunnerInfo:
                Runner name, installed version and supported configuration summary.
        """
        return RunnerInfo(
            name="pydantic-ai",
            version=version("pydantic-ai-slim"),
            config_summary={"forced_invocation": False, "sandbox_types": ["local"]},
        )

    @property
    def capabilities(self) -> RunnerCapabilities:
        """Declare the runner's supported evidence surfaces.

        Returns:
            RunnerCapabilities:
                Automatic invocation, evidence collection, usage and sandbox support.
        """
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
        """Run one agent turn in a fresh workspace and collect evidence.

        Args:
            request (RunRequest):
                Complete execution request for one case arm.

        Returns:
            RunObservation:
                Agent response, normalized evidence, usage and warnings.

        Raises:
            ConfigError:
                If forced invocation is requested from this auto-only runner.
        """
        if request.invocation == "forced":
            raise ConfigError(
                "the pydantic-ai runner does not support forced skill invocation"
            )

        environment = {
            "HOME": str(request.workspace_dir / ".home"),
            "TMPDIR": str(request.workspace_dir / ".tmp"),
        }
        workspace = LocalWorkspace(request.workspace_dir, env=environment)
        capabilities: list[Any] = [
            workspace,
            Coder(repo_context=False, sub_agents=False),
        ]
        if request.skill is not None and request.invocation == "auto":
            capabilities.append(Skills("skills", include=[request.skill.name]))

        agent = Agent(
            self._model or request.target_model,
            capabilities=capabilities,
            instructions=_INSTRUCTIONS,
        )
        prompt = _prompt_with_fixtures(request)
        model_settings = (
            cast("ModelSettings", request.model_settings)
            if request.model_settings
            else None
        )
        with capture_run_messages() as captured_messages:
            try:
                result = await _run_agent_with_cleanup(
                    agent,
                    prompt=prompt,
                    model_settings=model_settings,
                    timeout_seconds=request.timeout_seconds,
                    workspace_dir=request.workspace_dir,
                    env=environment,
                )
            except BaseException as err:
                await _record_failure_evidence(request, captured_messages, err)
                raise

        messages = result.all_messages()
        loaded_skills, tool_calls = _extract_evidence(messages)
        messages_path = request.raw_evidence_dir / "messages.json"
        await anyio.Path(messages_path).write_text(
            _pretty_messages(result.all_messages_json()),
            encoding="utf-8",
        )
        await _write_runner_log(
            request.raw_evidence_dir / "runner.jsonl",
            loaded_skills,
            tool_calls,
        )
        usage = _usage_record(result.usage)

        warnings: list[str] = []
        if not result.output.strip():
            warnings.append("the model returned an empty final response")
        if (
            request.skill is not None
            and request.invocation == "auto"
            and not loaded_skills
        ):
            warnings.append(f"the model did not load skill {request.skill.name!r}")

        return RunObservation(
            response=result.output,
            loaded_skills=loaded_skills,
            tool_calls=tool_calls,
            usage=usage,
            messages_path=messages_path,
            raw_evidence_dir=request.raw_evidence_dir,
            output_dir=request.output_dir,
            runner=self.info,
            warnings=warnings,
        )


# ==================================================================================
# Agent execution and cleanup
# ==================================================================================


async def _run_agent_with_cleanup(
    agent: "Agent[Any, str]",
    *,
    prompt: str,
    model_settings: "ModelSettings | None",
    timeout_seconds: float,
    workspace_dir: "Path",
    env: dict[str, str],
) -> "AgentRunResult[str]":
    try:
        result = await agent.run(
            prompt,
            model_settings=model_settings,
            timeout=timeout_seconds,
        )
    except BaseException as err:
        cleanup_error = await _coder_cleanup_error(workspace_dir, env)
        if cleanup_error is not None:
            err.add_note(f"Coder shell cleanup also failed: {cleanup_error}")
        if isinstance(err, anyio.get_cancelled_exc_class()):
            raise
        if cleanup_error is not None:
            raise EvaluationExecutionError(
                "agent run failed and Coder shell cleanup was incomplete"
            ) from err
        raise

    cleanup_error = await _coder_cleanup_error(workspace_dir, env)
    if cleanup_error is not None:
        raise cleanup_error
    return result


async def _coder_cleanup_error(
    workspace_dir: "Path", env: dict[str, str]
) -> EvaluationExecutionError | None:
    with anyio.CancelScope(shield=True):
        try:
            await _cleanup_coder_jobs(workspace_dir, env)
        except EvaluationExecutionError as err:
            return err
        except Exception as err:  # noqa: BLE001  # return a non-transient cleanup diagnostic
            return EvaluationExecutionError(f"Coder shell cleanup failed: {err}")
    return None


async def _cleanup_coder_jobs(workspace_dir: "Path", env: dict[str, str]) -> None:
    try:
        workspace = Workspace(LocalWorkspaceBackend(workspace_dir, env=env))
        jobs_base = await metadata_dir(workspace, "shell", temp_fallback=True)
        entries = await workspace.list_dir(jobs_base)
    except Exception as err:
        raise EvaluationExecutionError(
            "Coder shell cleanup could not enumerate jobs"
        ) from err

    errors: list[str] = []
    for entry in entries:
        if (
            not entry.is_dir
            or len(entry.name) != 32
            or any(character not in "0123456789abcdef" for character in entry.name)
        ):
            continue
        directory = posixpath.join(jobs_base, entry.name)
        try:
            await _cleanup_coder_job(workspace, directory)
        except Exception as err:  # noqa: BLE001  # continue with remaining jobs
            errors.append(f"{entry.name}: {type(err).__name__}: {err}")
    if errors:
        raise EvaluationExecutionError(
            f"Coder shell cleanup was incomplete: {'; '.join(errors)}"
        )


async def _cleanup_coder_job(workspace: Workspace, directory: str) -> None:
    # The handle records the process group chosen at launch; never discover a
    # group from a PID that may already have exited and been reused.
    job = await _reattach_coder_job(workspace, directory)
    if job is None:
        raise EvaluationExecutionError(
            f"could not reattach to Coder shell job; metadata preserved at {directory}"
        )
    await job.kill()
    await job.cleanup()


async def _reattach_coder_job(workspace: Workspace, directory: str) -> Job | None:
    job: Job | None = None
    poll_delay = anyio.Event()
    with anyio.move_on_after(_CODER_JOB_REATTACH_SECONDS):
        while job is None:
            job = await Job.attach(workspace, directory, combined=True)
            if job is not None:
                break
            with anyio.move_on_after(_CODER_JOB_REATTACH_POLL_SECONDS):
                await poll_delay.wait()
    return job


# ==================================================================================
# Prompt, evidence, and logging
# ==================================================================================


def _prompt_with_fixtures(request: RunRequest) -> str:
    if not request.fixture_files:
        return request.prompt
    relative = []
    for path in request.fixture_files:
        try:
            relative.append(path.relative_to(request.workspace_dir).as_posix())
        except ValueError:
            relative.append(path.name)
    listing = "\n".join(f"- {item}" for item in relative)
    return f"{request.prompt}\n\nInput files are available in the workspace:\n{listing}"


async def _record_failure_evidence(
    request: RunRequest,
    messages: list[ModelMessage],
    error: BaseException,
) -> None:
    """Best-effort preserve captured messages without masking the original error."""
    try:
        with anyio.CancelScope(shield=True):
            evidence_dir = anyio.Path(request.raw_evidence_dir)
            await evidence_dir.mkdir(parents=True, exist_ok=True)
            loaded_skills, tool_calls = _extract_evidence(messages)
            await (evidence_dir / "messages.json").write_text(
                _pretty_messages(ModelMessagesTypeAdapter.dump_json(messages)),
                encoding="utf-8",
            )
            await _write_runner_log(
                request.raw_evidence_dir / "runner.jsonl",
                loaded_skills,
                tool_calls,
            )
    except Exception as write_error:  # noqa: BLE001  # keep the original failure
        error.add_note(f"failed to write failure evidence: {write_error}")


def _extract_evidence(
    messages: "Sequence[ModelMessage]",
) -> tuple[list[SkillLoadRecord], list[ToolCallRecord]]:
    returns: dict[str, ToolReturnPart] = {}
    for message in messages:
        for part in getattr(message, "parts", []):
            if isinstance(part, ToolReturnPart) and part.tool_call_id:
                returns[part.tool_call_id] = part

    loaded: list[SkillLoadRecord] = []
    calls: list[ToolCallRecord] = []
    for event_index, message in enumerate(messages):
        if not isinstance(message, ModelResponse):
            continue
        for part in message.parts:
            if not isinstance(part, ToolCallPart):
                continue
            arguments = _arguments(part.args)
            return_part = returns.get(part.tool_call_id or "")
            status = "deferred" if return_part is None else _return_status(return_part)
            calls.append(
                ToolCallRecord(
                    name=part.tool_name,
                    call_id=part.tool_call_id or "",
                    arguments=arguments,
                    status=status,
                    source_event_index=event_index,
                )
            )
            if part.tool_name == "load_capability":
                name = arguments.get("id") or arguments.get("name")
                if isinstance(name, str) and name:
                    loaded.append(
                        SkillLoadRecord(
                            name=name,
                            call_id=part.tool_call_id or "",
                            status=status,
                            source_event_index=event_index,
                        )
                    )
    return loaded, calls


def _arguments(args: object) -> dict[str, Any]:
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return {"raw": args}
    if isinstance(args, dict):
        value = to_jsonable_python(args)
        if isinstance(value, dict):
            return value
    return {"raw": str(args)}


def _return_status(part: ToolReturnPart) -> RunStatus:
    match part.outcome:
        case "failed" | "denied" | "retried":
            return "error"
        case "interrupted":
            return "unknown"

    content = to_jsonable_python(part.content)
    if isinstance(content, dict) and content.get("error"):
        return "error"
    text = (
        str(content.get("message", "")).lower()
        if isinstance(content, dict)
        else str(content).lower()
    )
    if "not found" in text or "unknown capability" in text:
        return "error"
    return "success"


def _pretty_messages(raw: bytes | str) -> str:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        return json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        return raw


async def _write_runner_log(
    path: "Path", loaded: list[SkillLoadRecord], calls: list[ToolCallRecord]
) -> None:
    async with await anyio.open_file(path, "w", encoding="utf-8") as handle:
        for record in loaded:
            await handle.write(
                json.dumps(
                    {"kind": "skill_load", **record.model_dump(mode="json")},
                    ensure_ascii=False,
                )
            )
            await handle.write("\n")
        for record in calls:
            await handle.write(
                json.dumps(
                    {"kind": "tool_call", **record.model_dump(mode="json")},
                    ensure_ascii=False,
                )
            )
            await handle.write("\n")


def _usage_record(usage: "RunUsage") -> UsageRecord:
    return UsageRecord(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
        requests=usage.requests,
        tool_calls=usage.tool_calls,
        cost_usd=float(usage.cost) if usage.cost is not None else None,
    )
