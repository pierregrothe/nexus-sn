# tests/assessment/test_validate_assessment_rulesets_script.py
# Tests for the CI validator script.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Story 07 AC1, AC5-AC11: validate_assessment_rulesets script + example load."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow tests to import the scripts/ helper without installing it as a package
_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import validate_assessment_rulesets as validator_script  # noqa: E402
import yaml  # noqa: E402

from nexus.assessment.loader import load_ruleset  # noqa: E402

_REPO_TEMPLATES = Path(__file__).resolve().parents[2] / "templates"


def test_every_shipped_assessment_ruleset_parses() -> None:
    assessments_dir = _REPO_TEMPLATES / "assessments"
    files = sorted(assessments_dir.glob("*.yaml"))
    assert files, "expected at least one ruleset under templates/assessments/"
    for path in files:
        ruleset = load_ruleset(path)
        assert ruleset.id
        assert ruleset.rules


def test_every_shipped_ruleset_round_trips_through_pydantic() -> None:
    for path in sorted((_REPO_TEMPLATES / "assessments").glob("*.yaml")):
        ruleset = load_ruleset(path)
        re_dumped = yaml.safe_dump(ruleset.model_dump(mode="json"))
        re_loaded_path = path.parent / "__round_trip__.yaml"
        re_loaded_path.write_text(re_dumped, encoding="utf-8")
        try:
            re_loaded = load_ruleset(re_loaded_path)
        finally:
            re_loaded_path.unlink()
        assert re_loaded == ruleset


def test_validator_passes_on_shipped_rulesets() -> None:
    failures, messages = validator_script.validate_directory(_REPO_TEMPLATES)
    assert failures == 0, "\n".join(messages)


def test_validator_returns_zero_when_no_assessments_directory(tmp_path: Path) -> None:
    failures, messages = validator_script.validate_directory(tmp_path)
    assert failures == 0
    assert any("no assessments" in m for m in messages)


def test_validator_returns_zero_when_assessments_dir_empty(tmp_path: Path) -> None:
    (tmp_path / "assessments").mkdir()
    failures, messages = validator_script.validate_directory(tmp_path)
    assert failures == 0
    assert any("no rulesets" in m for m in messages)


def test_validator_reports_failure_for_invalid_yaml(tmp_path: Path) -> None:
    (tmp_path / "assessments").mkdir()
    bad = tmp_path / "assessments" / "bad.yaml"
    bad.write_text("id: x\n: nope\n[unclosed", encoding="utf-8")
    failures, messages = validator_script.validate_directory(tmp_path)
    assert failures == 1
    assert any("FAIL" in m for m in messages)


def test_validator_flags_orphaned_applies_to_entries(tmp_path: Path) -> None:
    assess_dir = tmp_path / "assessments"
    assess_dir.mkdir()
    (assess_dir / "orphan.yaml").write_text(
        """\
id: orphan
version: "1.0.0"
description: refers to nonexistent template
applies_to:
  - does-not-exist
rules:
  - id: r
    description: r
    severity: ERROR
    phase: PRE_APPLY
    scope:
      kind: table
      table: sys_scope
    required_tables: [sys_scope]
    logic: AND_ALL
    constraints:
      - operator: record_exists
        table: sys_scope
        filter: []
""",
        encoding="utf-8",
    )
    failures, messages = validator_script.validate_directory(tmp_path)
    assert failures == 1
    assert any("orphan.yaml" in m and "does-not-exist" in m for m in messages)


def test_validator_accepts_star_applies_to(tmp_path: Path) -> None:
    assess_dir = tmp_path / "assessments"
    assess_dir.mkdir()
    (assess_dir / "wildcard.yaml").write_text(
        """\
id: wildcard
version: "1.0.0"
description: applies to all templates
applies_to:
  - "*"
rules:
  - id: r
    description: r
    severity: ERROR
    phase: PRE_APPLY
    scope:
      kind: table
      table: sys_scope
    required_tables: [sys_scope]
    logic: AND_ALL
    constraints:
      - operator: record_exists
        table: sys_scope
        filter: []
""",
        encoding="utf-8",
    )
    failures, _messages = validator_script.validate_directory(tmp_path)
    assert failures == 0


def test_validator_main_returns_zero_for_clean_directory(tmp_path: Path) -> None:
    assess_dir = tmp_path / "assessments"
    assess_dir.mkdir()
    code = validator_script.main([str(tmp_path)])
    assert code == 0


def test_validator_main_returns_one_on_failure(tmp_path: Path) -> None:
    assess_dir = tmp_path / "assessments"
    assess_dir.mkdir()
    (assess_dir / "broken.yaml").write_text("not a ruleset", encoding="utf-8")
    code = validator_script.main([str(tmp_path)])
    assert code == 1
