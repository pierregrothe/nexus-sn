# tests/templates/test_env_var_resolution.py
# Tests for {{ env.X }} substitution inside template schemas.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Story 01 AC2-AC5: env-var field validator behavior."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from nexus.templates.schemas._env import (
    resolve_env_in_string,
    resolve_env_in_value,
)
from nexus.templates.schemas.now_assist_skill import NowAssistSkill


def test_resolve_env_in_string_substitutes_single_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MY_VAR", "hello")
    assert resolve_env_in_string("Value: {{ env.MY_VAR }}") == "Value: hello"


def test_resolve_env_in_string_substitutes_multiple_references(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("A", "1")
    monkeypatch.setenv("B", "2")
    assert resolve_env_in_string("{{ env.A }}-{{ env.B }}") == "1-2"


def test_resolve_env_in_string_passes_through_when_no_references() -> None:
    assert resolve_env_in_string("plain value") == "plain value"


def test_resolve_env_in_string_raises_on_unset_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEFINITELY_UNSET_VAR", raising=False)
    with pytest.raises(ValueError, match="env var 'DEFINITELY_UNSET_VAR' is not set"):
        resolve_env_in_string("{{ env.DEFINITELY_UNSET_VAR }}")


def test_resolve_env_in_value_passes_through_non_strings() -> None:
    assert resolve_env_in_value(42) == 42
    assert resolve_env_in_value(True) is True
    assert resolve_env_in_value(None) is None


def test_resolve_env_in_string_does_not_interpret_jinja_syntax() -> None:
    text = "{% if foo %}bar{% endif %}"
    assert resolve_env_in_string(text) == text


def test_now_assist_skill_resolves_env_in_instructions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SKILL_PROMPT", "Read the incident.")
    skill = NowAssistSkill(
        id="x",
        version="1.0",
        name="x",
        instructions="Prompt: {{ env.SKILL_PROMPT }}",
    )
    assert skill.instructions == "Prompt: Read the incident."


def test_now_assist_skill_resolves_env_in_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SKILL_DESC", "incident triage")
    skill = NowAssistSkill(
        id="x",
        version="1.0",
        name="x",
        instructions="x",
        description="{{ env.SKILL_DESC }}",
    )
    assert skill.description == "incident triage"


def test_now_assist_skill_raises_validation_error_on_unset_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MISSING_VAR_FOR_TEST", raising=False)
    with pytest.raises(ValidationError) as exc_info:
        NowAssistSkill(
            id="x",
            version="1.0",
            name="x",
            instructions="{{ env.MISSING_VAR_FOR_TEST }}",
        )
    assert "'MISSING_VAR_FOR_TEST'" in str(exc_info.value)


def test_now_assist_skill_resolves_env_in_target_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEPLOY_SCOPE", "x_my_app")
    skill = NowAssistSkill(
        id="x",
        version="1.0",
        target_scope="{{ env.DEPLOY_SCOPE }}",
        name="x",
        instructions="x",
    )
    assert skill.target_scope == "x_my_app"


def test_now_assist_skill_lowercase_env_name_not_recognized() -> None:
    skill = NowAssistSkill(
        id="x",
        version="1.0",
        name="x",
        instructions="{{ env.lower_var }}",
    )
    assert skill.instructions == "{{ env.lower_var }}"
