import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from skill_eval.api import validate_skill
from skill_eval.cli import app


def _copy_skill(tmp_path: Path, source: Path) -> Path:
    target = tmp_path / "sample-skill"
    shutil.copytree(source, target)
    return target


def test_validate_skill_valid_sample_returns_success(sample_skill: Path) -> None:
    result = validate_skill(sample_skill)
    assert result.ok, result.errors
    assert result.skill_name == "sample-skill"
    assert not result.errors


def test_validate_rejects_unknown_check_case(
    sample_skill: Path, tmp_path: Path
) -> None:
    skill = _copy_skill(tmp_path, sample_skill)
    config = skill / "evals" / "skill-eval.yaml"
    config.write_text(
        config.read_text(encoding="utf-8").replace('case: "1"', 'case: "99"'),
        encoding="utf-8",
    )
    result = validate_skill(skill)
    assert not result.ok
    assert any("unknown eval id" in error for error in result.errors)


def test_validate_rejects_check_assertion_mismatch(
    sample_skill: Path, tmp_path: Path
) -> None:
    skill = _copy_skill(tmp_path, sample_skill)
    config = skill / "evals" / "skill-eval.yaml"
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "chart.png exists and is non-empty.",
            "a different assertion",
        ),
        encoding="utf-8",
    )
    result = validate_skill(skill)
    assert not result.ok
    assert any("not present" in error for error in result.errors)


def test_validate_rejects_duplicate_assertion(
    sample_skill: Path, tmp_path: Path
) -> None:
    skill = _copy_skill(tmp_path, sample_skill)
    eval_file = skill / "evals" / "evals.json"
    raw = json.loads(eval_file.read_text(encoding="utf-8"))
    raw["evals"][0]["assertions"].append(raw["evals"][0]["assertions"][0])
    eval_file.write_text(json.dumps(raw), encoding="utf-8")
    result = validate_skill(skill)
    assert not result.ok
    assert any("duplicate assertion" in error for error in result.errors)


def test_validate_rejects_path_traversal(sample_skill: Path, tmp_path: Path) -> None:
    skill = _copy_skill(tmp_path, sample_skill)
    config = skill / "evals" / "skill-eval.yaml"
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "path: chart.png", "path: ../chart.png"
        ),
        encoding="utf-8",
    )
    result = validate_skill(skill)
    assert not result.ok
    assert any("must not contain '..'" in error for error in result.errors)


def test_validate_command_valid_skill_json_reports_passed_and_exits_zero(
    sample_skill: Path,
) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["validate", str(sample_skill), "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"


def test_validate_command_missing_path_exits_two(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["validate", str(tmp_path / "missing")])
    assert result.exit_code == 2


def test_validate_explicit_missing_config_is_error(
    sample_skill: Path, tmp_path: Path
) -> None:
    result = validate_skill(sample_skill, tmp_path / "missing.yaml")
    assert not result.ok
    assert any("missing evaluation config" in error for error in result.errors)


def test_validate_rejects_trigger_fixture_outside_evals(
    sample_skill: Path, tmp_path: Path
) -> None:
    skill = _copy_skill(tmp_path, sample_skill)
    (skill / "outside.txt").write_text("outside evals\n", encoding="utf-8")
    config = skill / "evals" / "skill-eval.yaml"
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "      should_trigger: true",
            '      files: ["outside.txt"]\n      should_trigger: true',
            1,
        ),
        encoding="utf-8",
    )

    result = validate_skill(skill)

    assert not result.ok
    assert any("inside evals/" in error for error in result.errors)


def test_validate_rejects_trigger_fixture_symlink_escape(
    sample_skill: Path, tmp_path: Path
) -> None:
    skill = _copy_skill(tmp_path, sample_skill)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside the skill\n", encoding="utf-8")
    (skill / "evals" / "outside.txt").symlink_to(outside)
    config = skill / "evals" / "skill-eval.yaml"
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "      should_trigger: true",
            '      files: ["evals/outside.txt"]\n      should_trigger: true',
        ),
        encoding="utf-8",
    )

    result = validate_skill(skill)

    assert not result.ok
    assert any("fixture escapes the skill root" in error for error in result.errors)
