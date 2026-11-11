"""Domain exceptions mapped to CLI exit codes by ``skill_eval.cli``."""


class SkillEvalError(Exception):
    """Base class for expected tool errors."""


class ConfigError(SkillEvalError):
    """Invalid CLI input, configuration, dataset or capability request."""


class EvaluationExecutionError(SkillEvalError):
    """The experiment could not be completed."""


class VerifierError(SkillEvalError):
    """The verifier itself failed, timed out or violated its output contract."""
