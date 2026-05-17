# tests/test_render_context.py
# Tests for RenderContext + get_render_context helper.
# Author: Pierre Grothe
# Date: 2026-05-15

"""Cover the Typer-context retrieval helper and missing-context guard."""

from io import StringIO

import click
import pytest
import typer
from rich.console import Console
from typer.models import Context as TyperContext

from nexus.ui.capabilities import ColorDepth, RenderProfile, TerminalCapabilities
from nexus.ui.render_context import (
    RenderContext,
    RenderContextMissingError,
    get_render_context,
)


def _make_render_context() -> RenderContext:
    caps = TerminalCapabilities(
        is_tty=False,
        is_ci=False,
        color_depth=ColorDepth.NONE,
        cols=80,
        rows=24,
        legacy_windows=False,
        term_program="",
        is_dumb_terminal=False,
        is_multiplexer=False,
        no_color_env=False,
        forced_plain=True,
        supports_hyperlinks=False,
    )
    console = Console(file=StringIO(), force_terminal=False)
    return RenderContext(console=console, caps=caps, profile=RenderProfile.PLAIN)


def _make_typer_context(obj: object) -> typer.Context:
    command = click.Command(name="x", callback=lambda: None)
    return TyperContext(command, obj=obj)


def test_getrendercontext_returns_attached_object() -> None:
    ctx_obj = _make_render_context()
    typer_ctx = _make_typer_context(ctx_obj)
    assert get_render_context(typer_ctx) is ctx_obj


def test_getrendercontext_raises_when_obj_missing() -> None:
    typer_ctx = _make_typer_context(None)
    with pytest.raises(RenderContextMissingError):
        get_render_context(typer_ctx)


def test_getrendercontext_raises_when_obj_wrong_type() -> None:
    typer_ctx = _make_typer_context("not a context")
    with pytest.raises(RenderContextMissingError):
        get_render_context(typer_ctx)


def test_rendercontext_is_frozen() -> None:
    rc = _make_render_context()
    with pytest.raises((AttributeError, TypeError, ValueError)):
        setattr(rc, "profile", RenderProfile.RICH)
