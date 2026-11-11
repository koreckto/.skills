"""Typed records shared by the CLI, runner adapters, evaluators and artifacts."""

from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_evals.reporting import EvaluationReport

if TYPE_CHECKING:
    from pydantic_evals.evaluators import EvaluatorContext
    from pydantic_evals.reporting import ReportCase, ReportCaseFailure

type JsonValue = (
    str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None
)
type Arm = Literal["with_skill", "without_skill", "old_skill"]
type RunStatus = Literal["success", "error", "deferred", "unknown"]
type ExperimentStatus = Literal["passed", "failed", "ungraded", "error"]


class _StrictModel(BaseModel):
    """Base model for records that should reject unknown fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)


# ==================================================================================
# Runtime records
# ==================================================================================


class SkillDeployment(_StrictModel):
    """A skill snapshot copied into a run workspace."""

    name: str
    """Skill name."""
    snapshot_path: Path
    """Path to the skill snapshot used for the run."""
    content_hash: str
    """Hash of the skill snapshot contents."""


class SkillLoadRecord(_StrictModel):
    """One attempt to load a skill through ``load_capability``."""

    name: str
    """Skill name passed to the load call."""
    call_id: str
    """Tool-call identifier for the load request."""
    status: RunStatus = "unknown"
    """Load outcome."""
    source_event_index: int | None = None
    """Zero-based index of the source message event when available."""


class ToolCallRecord(_StrictModel):
    """Normalized tool-call evidence independent of a runner's native format."""

    name: str
    """Tool name."""
    call_id: str
    """Tool-call identifier."""
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    """Normalized tool-call arguments."""
    status: RunStatus = "unknown"
    """Tool-call outcome."""
    duration_ms: float | None = None
    """Wall-clock duration in milliseconds when reported."""
    source_event_index: int | None = None
    """Zero-based index of the source message event when available."""


class UsageRecord(_StrictModel):
    """Token and request usage; fields are optional when unmeasured."""

    input_tokens: int | None = None
    """Input token count when reported."""
    output_tokens: int | None = None
    """Output token count when reported."""
    total_tokens: int | None = None
    """Total token count when reported."""
    requests: int | None = None
    """Number of model requests when reported."""
    tool_calls: int | None = None
    """Number of tool calls when reported."""
    cost_usd: float | None = None
    """Estimated cost in US dollars when reported."""


class RunnerInfo(_StrictModel):
    """Identity and configuration of a runner adapter."""

    name: str
    """Runner name."""
    version: str
    """Installed runner package version."""
    config_summary: dict[str, JsonValue] = Field(default_factory=dict)
    """Serialized runner configuration summary."""
    native_trace_id: str | None = None
    """Runner-native trace identifier when available."""


class RunnerCapabilities(_StrictModel):
    """Features a runner can provide before a run starts."""

    auto_invocation: bool = False
    """Whether the runner can load skills automatically."""
    forced_invocation: bool = False
    """Whether the runner can force a skill invocation."""
    loaded_skill_evidence: bool = False
    """Whether the runner reports loaded skill evidence."""
    tool_call_evidence: bool = False
    """Whether the runner reports tool-call evidence."""
    token_usage: bool = False
    """Whether the runner reports token usage."""
    cost_usage: bool = False
    """Whether the runner reports cost usage."""
    sandbox_types: tuple[str, ...] = ()
    """Sandbox kinds the runner supports."""


class RunRequest(_StrictModel):
    """Everything a runner needs for one isolated arm of one case."""

    run_id: str
    """Unique identifier for one case-arm repeat."""
    case_id: str
    """Eval case identifier."""
    repeat_index: int = Field(ge=1)
    """One-based repeat index."""
    arm: Arm
    """Comparison arm."""
    prompt: str
    """User prompt for the case."""
    fixture_files: tuple[Path, ...] = ()
    """Input files copied into the workspace."""
    skill: SkillDeployment | None = None
    """Skill deployment to load, or None when no skill applies."""
    invocation: Literal["auto", "forced"] = "auto"
    """Skill invocation mode."""
    workspace_dir: Path
    """Isolated working directory for the agent."""
    output_dir: Path
    """Directory that preserves the agent's declared outputs."""
    raw_evidence_dir: Path
    """Directory for runner-native evidence."""
    target_model: str
    """Model identifier used for the run."""
    model_settings: dict[str, JsonValue] = Field(default_factory=dict)
    """Runner-specific model settings."""
    timeout_seconds: float = Field(gt=0)
    """Per-run timeout in seconds."""


class RunObservation(_StrictModel):
    """Uniform, serializable evidence returned by every runner."""

    schema_version: Literal[1] = 1
    """Observation schema version."""
    response: str
    """Final model response text."""
    loaded_skills: list[SkillLoadRecord] = Field(default_factory=list)
    """Skill load attempts observed during the run."""
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    """Tool calls observed during the run."""
    usage: UsageRecord = Field(default_factory=UsageRecord)
    """Token and request usage."""
    messages_path: Path | None = None
    """Path to the serialized message transcript when available."""
    raw_evidence_dir: Path
    """Directory containing runner-native evidence."""
    output_dir: Path
    """Directory containing preserved outputs."""
    runner: RunnerInfo
    """Runner identity and version information."""
    warnings: list[str] = Field(default_factory=list)
    """Non-fatal warnings collected during the run."""


class ValidationResult(_StrictModel):
    """Result of validating a skill package and its evaluation definitions."""

    ok: bool
    """Whether validation succeeded."""
    skill_path: Path
    """Validated skill directory."""
    skill_name: str | None = None
    """Resolved skill name when available."""
    errors: tuple[str, ...] = ()
    """Validation errors; empty when validation succeeds."""
    warnings: tuple[str, ...] = ()
    """Non-fatal validation warnings."""

    @classmethod
    def from_errors(
        cls,
        skill_path: Path,
        errors: list[str],
        warnings: list[str] | None = None,
        skill_name: str | None = None,
    ) -> "ValidationResult":
        """Build a result from a list of validation errors.

        Args:
            skill_path (Path):
                Validated skill directory.
            errors (list[str]):
                Validation errors, empty when validation succeeds.
            warnings (list[str], optional):
                Non-fatal validation warnings. Defaults to no warnings.
            skill_name (str, optional):
                Resolved skill name when available. Defaults to None.

        Returns:
            ValidationResult:
                Validation result with status derived from the error list.
        """
        return cls(
            ok=not errors,
            skill_path=skill_path,
            skill_name=skill_name,
            errors=tuple(errors),
            warnings=tuple(warnings or ()),
        )


# ==================================================================================
# Configuration models
# ==================================================================================


class BaselineConfig(_StrictModel):
    """How the comparison arm is selected."""

    mode: Literal["no-skill", "none", "skill"] = "no-skill"
    """Baseline arm selection."""
    skill_path: Path | None = None
    """Baseline skill directory; required when mode is ``skill``."""

    @model_validator(mode="after")
    def _skill_path_required(self) -> "BaselineConfig":
        if self.mode == "skill" and self.skill_path is None:
            raise ValueError("baseline.mode=skill requires baseline.skill_path")
        if self.mode != "skill" and self.skill_path is not None:
            raise ValueError(
                "baseline.skill_path is only valid with baseline.mode=skill"
            )
        return self


class SandboxConfig(_StrictModel):
    """Execution isolation settings."""

    kind: Literal["local", "docker"] = "docker"
    """Sandbox implementation."""
    image: str | None = None
    """Docker image used when kind is ``docker``."""
    network: bool = False
    """Whether the sandbox permits network access."""

    @model_validator(mode="after")
    def _docker_image_required(self) -> "SandboxConfig":
        if self.kind == "docker" and not self.image:
            raise ValueError("docker sandbox requires an image")
        return self


class TelemetryConfig(_StrictModel):
    """OpenTelemetry/Logfire settings. The MVP records local metadata only."""

    kind: Literal["local", "logfire", "otlp"] = "local"
    """Telemetry backend."""
    include_content: bool = False
    """Whether telemetry may include prompt and response content."""


class GateConfig(_StrictModel):
    """Quality gates applied after a complete experiment."""

    min_pass_rate: float | None = Field(default=None, ge=0, le=1)
    """Minimum candidate pass rate; None disables the gate."""
    max_regression: float | None = Field(default=None, ge=0, le=1)
    """Maximum allowed pass-rate regression; None disables the gate."""


class ExperimentConfig(_StrictModel):
    """Complete description of one experiment."""

    skill_path: Path
    """Skill directory under evaluation."""
    suite: Literal["output-quality", "trigger"] = "output-quality"
    """Evaluation suite."""
    target_model: str
    """Model used for the candidate run."""
    judge_model: str | None = None
    """Model used for LLM judging, or None when judging is disabled."""
    runner: str = "pydantic-ai"
    """Runner adapter name."""
    mode: Literal["auto", "forced"] = "auto"
    """Skill invocation mode."""
    baseline: BaselineConfig = Field(default_factory=BaselineConfig)
    """Baseline arm configuration."""
    case_ids: tuple[str, ...] = ()
    """Eval case identifiers to run; empty selects all cases."""
    repeat: int = Field(default=1, ge=1)
    """Number of repeats per case."""
    concurrency: int = Field(default=2, ge=1)
    """Maximum number of concurrent cases."""
    timeout_seconds: float = Field(default=600, gt=0)
    """Per-case timeout in seconds."""
    sandbox: SandboxConfig
    """Execution isolation settings."""
    workspace: Path = Path(".skill-eval")
    """Root directory for experiment artifacts."""
    config_path: Path | None = None
    """External evaluation config path when provided."""
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    """Telemetry settings."""
    gates: GateConfig = Field(default_factory=GateConfig)
    """Quality gate settings."""


class TriggerCase(_StrictModel):
    """One trigger or non-trigger prompt."""

    id: str
    """Trigger case identifier."""
    prompt: str = Field(min_length=1)
    """Prompt text."""
    files: tuple[str, ...] = ()
    """Fixture files available to the case."""
    should_trigger: bool
    """Whether the skill should load for this prompt."""


class TriggerConfig(_StrictModel):
    """Trigger suite definition stored in ``skill-eval.yaml``."""

    decoy_skills: tuple[str, ...] = ()
    """Additional skills that should not be selected."""
    cases: tuple[TriggerCase, ...] = ()
    """Trigger cases."""


class FileExistsCheck(_StrictModel):
    """Deterministic existence check bound to one official assertion."""

    case: str
    """Eval identifier the check is bound to."""
    assertion: str = Field(min_length=1)
    """Assertion text the check verifies."""
    type: Literal["file_exists"]
    """Check discriminator."""
    path: str = Field(min_length=1)
    """Output path to test, relative to the outputs directory."""
    non_empty: bool = True
    """Whether the file must contain data."""

    @field_validator("case", mode="before")
    @classmethod
    def _normalize_case(cls, value: object) -> str:
        match value:
            case bool():
                raise TypeError("case must be an eval id, not a boolean")
            case int():
                return str(value)
            case str():
                return value
            case _:
                raise ValueError("case must be a string or integer eval id")


class CommandCheck(_StrictModel):
    """Verifier call bound to one official assertion."""

    case: str
    """Eval identifier the check is bound to."""
    assertion: str = Field(min_length=1)
    """Assertion text the check verifies."""
    type: Literal["command"]
    """Check discriminator."""
    timeout_seconds: float = Field(default=30, gt=0)
    """Verifier timeout in seconds."""

    @field_validator("case", mode="before")
    @classmethod
    def _normalize_case(cls, value: object) -> str:
        match value:
            case bool():
                raise TypeError("case must be an eval id, not a boolean")
            case int():
                return str(value)
            case str():
                return value
            case _:
                raise ValueError("case must be a string or integer eval id")


type CheckSpec = Annotated[FileExistsCheck | CommandCheck, Field(discriminator="type")]


class SkillEvalYaml(_StrictModel):
    """Typed ``evals/skill-eval.yaml`` document."""

    version: Literal[1] = 1
    """Configuration schema version."""
    trigger: TriggerConfig | None = None
    """Optional trigger suite definition."""
    checks: tuple[CheckSpec, ...] = ()
    """Deterministic checks bound to official assertions."""
    gates: GateConfig = Field(default_factory=GateConfig)
    """Quality gate settings."""


# ==================================================================================
# Case and result models
# ==================================================================================


class SkillCaseInput(_StrictModel):
    """Inputs for one Pydantic Evals case (one eval id and one arm)."""

    case_id: str
    """Eval case identifier."""
    prompt: str
    """Prompt text for the case."""
    fixture_files: tuple[str, ...] = ()
    """Fixture files to copy into the workspace."""
    arm: Arm
    """Comparison arm."""
    workspace_dir: Path
    """Isolated working directory for the case."""
    output_dir: Path
    """Output directory for preserved artifacts."""
    raw_evidence_dir: Path
    """Directory for raw evidence."""
    skill_source_path: Path | None = None
    """Skill directory to deploy, or None for the baseline."""
    fixture_source_root: Path | None = None
    """Root directory used to resolve fixture files."""
    skill_name: str | None = None
    """Skill name to load, or None when no skill applies."""
    target_model: str
    """Model used for the case."""
    judge_model: str | None = None
    """Model used for LLM judging, or None when judging is disabled."""
    mode: Literal["auto", "forced"] = "auto"
    """Skill invocation mode."""
    timeout_seconds: float = 600
    """Case timeout in seconds."""


class SkillCaseMetadata(_StrictModel):
    """Case data evaluators and artifact writers need after the run."""

    eval_id: str
    """Eval identifier."""
    eval_dir_name: str
    """Filesystem-safe eval directory name."""
    expected_output: str
    """Expected output description used by evaluators and the judge."""
    assertions: tuple[str, ...] = ()
    """Assertion texts."""
    arm: Arm
    """Comparison arm."""
    should_trigger: bool | None = None
    """Expected trigger outcome for trigger cases."""
    checks: tuple[CheckSpec, ...] = ()
    """Deterministic checks bound to the case."""
    bundle_dir: Path | None = None
    """Evaluation bundle directory when available."""
    skill_name: str | None = None
    """Skill name when available."""
    repeat_index: int = 1
    """One-based repeat index."""


type SkillEvaluationReport = EvaluationReport[
    SkillCaseInput, RunObservation, SkillCaseMetadata
]
type SkillEvaluatorContext = EvaluatorContext[
    SkillCaseInput, RunObservation, SkillCaseMetadata
]
type SkillReportCase = ReportCase[SkillCaseInput, RunObservation, SkillCaseMetadata]
type SkillCaseResult = (
    SkillReportCase
    | ReportCaseFailure[SkillCaseInput, RunObservation, SkillCaseMetadata]
)


class ExperimentResult(BaseModel):
    """Result of a complete or partially completed experiment."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    status: ExperimentStatus
    """Experiment status."""
    experiment_dir: Path
    """Experiment artifact directory."""
    iteration_dirs: tuple[Path, ...] = ()
    """Directories of completed iterations."""
    reports: tuple[SkillEvaluationReport, ...] = ()
    """Evaluation reports for completed iterations."""
    artifacts: dict[str, Path] = Field(default_factory=dict)
    """Paths to written artifacts keyed by artifact name."""
    message: str | None = None
    """Diagnostic message when available."""
    pass_rate: float | None = None
    """Aggregate pass rate when available."""


class ExperimentManifest(BaseModel):
    """Fields required when comparing an experiment manifest."""

    model_config = ConfigDict(extra="allow", frozen=True)

    schema_version: Literal[1] = 1
    """Manifest schema version."""
    suite: Literal["output-quality", "trigger"]
    """Evaluation suite."""
    runner: str
    """Runner adapter name."""
    mode: Literal["auto", "forced"]
    """Skill invocation mode."""
    target_model: str
    """Candidate model."""
    judge_model: str
    """Judge model."""
    dataset_hash: str
    """Hash of the evaluation dataset."""
    evaluation_bundle_hash: str
    """Hash of the evaluation bundle."""
    case_ids: tuple[str, ...] = ()
    """Eval case identifiers included in the experiment."""


class MetricSummary(_StrictModel):
    """Descriptive statistics for one benchmark metric."""

    mean: float | None = None
    """Arithmetic mean, or None when no samples exist."""
    stddev: float | None = None
    """Sample standard deviation, or None when fewer than two samples exist."""
    min: float | None = None
    """Minimum sample value, or None when no samples exist."""
    max: float | None = None
    """Maximum sample value, or None when no samples exist."""
    n: int = 0
    """Number of samples."""


class ArmBenchmark(_StrictModel):
    """Benchmark metrics collected for one arm."""

    pass_rate: MetricSummary = Field(default_factory=MetricSummary)
    """Pass-rate statistics for the arm."""
    time_seconds: MetricSummary = Field(default_factory=MetricSummary)
    """Runtime statistics in seconds."""
    tokens: MetricSummary = Field(default_factory=MetricSummary)
    """Token-usage statistics."""


class BenchmarkDocument(BaseModel):
    """Benchmark fields used during experiment comparison."""

    model_config = ConfigDict(extra="allow", frozen=True)

    run_summary: dict[str, ArmBenchmark] = Field(default_factory=dict)
    """Metric summaries keyed by arm."""
    delta: dict[str, float | None] = Field(default_factory=dict)
    """Candidate-to-baseline deltas keyed by metric."""


class ExperimentSummary(BaseModel):
    """Fields required when comparing an experiment summary."""

    model_config = ConfigDict(extra="allow", frozen=True)

    schema_version: Literal[1] = 1
    """Summary schema version."""
    status: ExperimentStatus
    """Experiment status."""
    benchmark: BenchmarkDocument = Field(default_factory=BenchmarkDocument)
    """Benchmark metrics for the experiment."""
    pass_rate: float | None = Field(default=None, ge=0, le=1)
    """Overall pass rate when available."""


class ComparisonResult(_StrictModel):
    """Result of comparing two experiment directories."""

    comparable: bool
    """Whether the manifests are directly comparable."""
    status: ExperimentStatus = "ungraded"
    """Gate result."""
    candidate_dir: Path
    """Candidate experiment directory."""
    baseline_dir: Path
    """Baseline experiment directory."""
    reasons: tuple[str, ...] = ()
    """Comparability or gate failure reasons."""
    candidate: dict[str, JsonValue] = Field(default_factory=dict)
    """Candidate arm metrics."""
    baseline: dict[str, JsonValue] = Field(default_factory=dict)
    """Baseline arm metrics."""
    delta: dict[str, JsonValue] = Field(default_factory=dict)
    """Candidate-to-baseline deltas."""
    gates: GateConfig = Field(default_factory=GateConfig)
    """Quality gates applied to the comparison."""
    message: str | None = None
    """Human-readable summary when available."""
