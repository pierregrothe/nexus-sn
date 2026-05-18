# tests/test_cli_prompts.py
# Tests for nexus.cli.prompts and the scripted PromptSource fake.
# Author: Pierre Grothe
# Date: 2026-05-18
"""Tests for the PromptSource Protocol and its impls."""

from __future__ import annotations

from typing import Any

import pytest
import typer

from nexus.cli.prompts import PromptExhaustedError, PromptSource, TyperPromptSource
from tests.fakes.scripted_prompt import ScriptedPromptSource


def test_prompt_source_typer_impl_satisfies_protocol() -> None:
    assert isinstance(TyperPromptSource(), PromptSource)


def test_prompt_source_scripted_impl_satisfies_protocol() -> None:
    assert isinstance(ScriptedPromptSource([]), PromptSource)


def test_typer_prompt_source_ask_forwards_to_prompt_fn() -> None:
    captured: dict[str, Any] = {}

    def fake_prompt(message: str, **kwargs: Any) -> str:
        captured["message"] = message
        captured.update(kwargs)
        return "typed-value"

    source = TyperPromptSource(prompt_fn=fake_prompt)
    assert source.ask("Username") == "typed-value"
    assert captured["message"] == "Username"
    assert captured["hide_input"] is False
    assert captured["confirmation_prompt"] is False


def test_typer_prompt_source_ask_with_hide_sets_hide_input_true() -> None:
    captured: dict[str, Any] = {}

    def fake_prompt(message: str, **kwargs: Any) -> str:
        del message  # not under test here
        captured.update(kwargs)
        return "pw"

    source = TyperPromptSource(prompt_fn=fake_prompt)
    source.ask("Password", hide=True)
    assert captured["hide_input"] is True


def test_typer_prompt_source_confirm_forwards_to_confirm_fn() -> None:
    captured: dict[str, str] = {}

    def fake_confirm(message: str) -> bool:
        captured["message"] = message
        return True

    source = TyperPromptSource(confirm_fn=fake_confirm)
    assert source.confirm("Proceed?") is True
    assert captured["message"] == "Proceed?"


def test_typer_prompt_source_default_prompt_fn_is_typer_prompt() -> None:
    source = TyperPromptSource()
    assert source.prompt_fn is typer.prompt
    assert source.confirm_fn is typer.confirm


def test_scripted_prompt_source_ask_pops_answers_in_order() -> None:
    source = ScriptedPromptSource(["alpha", "beta", "gamma"])
    assert source.ask("first") == "alpha"
    assert source.ask("second") == "beta"
    assert source.ask("third") == "gamma"


def test_scripted_prompt_source_ask_ignores_hide_flag() -> None:
    source = ScriptedPromptSource(["secret"])
    assert source.ask("Password", hide=True) == "secret"


def test_scripted_prompt_source_ask_raises_prompt_exhausted_when_empty() -> None:
    source = ScriptedPromptSource(["only-one"])
    source.ask("first")
    with pytest.raises(PromptExhaustedError) as excinfo:
        source.ask("second")
    assert "second" in str(excinfo.value)


@pytest.mark.parametrize("yes_token", ["y", "yes", "Y", "YES", " yes ", "Yes"])
def test_scripted_prompt_source_confirm_returns_true_for_yes_tokens(
    yes_token: str,
) -> None:
    source = ScriptedPromptSource([yes_token])
    assert source.confirm("ok?") is True


@pytest.mark.parametrize("no_token", ["n", "no", "anything-else", "", "false"])
def test_scripted_prompt_source_confirm_returns_false_for_non_yes_tokens(
    no_token: str,
) -> None:
    source = ScriptedPromptSource([no_token])
    assert source.confirm("ok?") is False


def test_scripted_prompt_source_confirm_raises_prompt_exhausted_when_empty() -> None:
    source = ScriptedPromptSource([])
    with pytest.raises(PromptExhaustedError):
        source.confirm("ok?")


def test_scripted_prompt_source_mixes_ask_and_confirm_in_order() -> None:
    source = ScriptedPromptSource(["host.example", "admin", "y", "secret"])
    assert source.ask("Host") == "host.example"
    assert source.ask("User") == "admin"
    assert source.confirm("Continue?") is True
    assert source.ask("Password", hide=True) == "secret"
