# tests/assessment/test_loader.py
# Tests for the YAML ruleset loader.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Loader tests for Story 01 AC8-AC10."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from nexus.assessment.errors import RulesetLoadError
from nexus.assessment.loader import load_ruleset
from tests.fakes.rulesets import sample_ruleset

_VALID_YAML = """
id: scope-readiness
version: "1.0.0"
description: scope must exist
applies_to: ["*"]
rules:
  - id: scope-must-exist
    description: target scope is recorded
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
"""


def test_load_ruleset_parses_valid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "valid.yaml"
    path.write_text(_VALID_YAML, encoding="utf-8")
    ruleset = load_ruleset(path)
    assert ruleset.id == "scope-readiness"
    assert len(ruleset.rules) == 1
    assert ruleset.rules[0].id == "scope-must-exist"


def test_load_ruleset_raises_on_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.yaml"
    with pytest.raises(RulesetLoadError) as exc_info:
        load_ruleset(path)
    assert exc_info.value.path == path
    assert isinstance(exc_info.value.cause, OSError)


def test_load_ruleset_raises_on_malformed_yaml(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text("id: x\n: bad-mapping\n[unclosed", encoding="utf-8")
    with pytest.raises(RulesetLoadError) as exc_info:
        load_ruleset(path)
    assert isinstance(exc_info.value.cause, yaml.YAMLError)


def test_load_ruleset_raises_on_schema_violation(tmp_path: Path) -> None:
    path = tmp_path / "wrong_shape.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "id": "bad",
                "version": "1.0.0",
                "description": "missing-required",
                "applies_to": ["*"],
                "rules": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RulesetLoadError):
        load_ruleset(path)


def test_load_ruleset_round_trip_via_yaml(tmp_path: Path) -> None:
    original = sample_ruleset()
    path = tmp_path / "round_trip.yaml"
    path.write_text(yaml.safe_dump(original.model_dump(mode="json")), encoding="utf-8")
    loaded = load_ruleset(path)
    assert loaded == original


def test_ruleset_load_error_str_contains_path_and_cause(tmp_path: Path) -> None:
    path = tmp_path / "doesnotmatter.yaml"
    cause = ValueError("inner")
    err = RulesetLoadError(path, cause)
    text = str(err)
    assert str(path) in text
    assert "inner" in text
