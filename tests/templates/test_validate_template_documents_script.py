# tests/templates/test_validate_template_documents_script.py
# Tests for scripts/validate_template_documents.py.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Story 07 AC7-AC10: validate_template_documents script behavior."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import validate_template_documents as validator_script  # noqa: E402

_REPO_TEMPLATES = Path(__file__).resolve().parents[2] / "templates"


def test_validator_passes_on_shipped_templates() -> None:
    failures, messages = validator_script.validate_directory(_REPO_TEMPLATES)
    assert failures == 0, "\n".join(messages)


def test_validator_returns_zero_when_directory_missing(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    failures, messages = validator_script.validate_directory(missing)
    assert failures == 0
    assert any("no templates directory" in m for m in messages)


def test_validator_returns_zero_when_no_templates(tmp_path: Path) -> None:
    failures, messages = validator_script.validate_directory(tmp_path)
    assert failures == 0
    assert any("no templates to validate" in m for m in messages)


def test_validator_reports_failure_for_invalid_template(tmp_path: Path) -> None:
    template_dir = tmp_path / "broken"
    template_dir.mkdir()
    (template_dir / "template.yaml").write_text(
        "kind: now_assist_skill\nid: x\n: bad\n[unclosed",
        encoding="utf-8",
    )
    failures, messages = validator_script.validate_directory(tmp_path)
    assert failures == 1
    assert any("FAIL" in m for m in messages)


def test_validator_main_clean_returns_zero(tmp_path: Path) -> None:
    code = validator_script.main([str(tmp_path)])
    assert code == 0


def test_validator_main_failure_returns_one(tmp_path: Path) -> None:
    template_dir = tmp_path / "broken"
    template_dir.mkdir()
    (template_dir / "template.yaml").write_text("kind: bogus_kind\nid: x", encoding="utf-8")
    code = validator_script.main([str(tmp_path)])
    assert code == 1
