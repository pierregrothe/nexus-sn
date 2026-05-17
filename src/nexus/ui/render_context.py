# src/nexus/ui/render_context.py
# Frozen render context bundling Console + capabilities + profile.
# Author: Pierre Grothe
# Date: 2026-05-15

"""Thread the render context through Typer's ``ctx.obj``.

Components receive a single :class:`RenderContext` rather than reading
attributes off the Rich ``Console``. This keeps Pyright strict happy
(the Rich type stubs do not accept arbitrary attribute injection) and
matches the dependency-injection style used elsewhere in NEXUS for
``KeychainClient`` / ``FakeKeychainClient``.
"""

from dataclasses import dataclass

import typer
from rich.console import Console

from nexus.ui.capabilities import RenderProfile, TerminalCapabilities

__all__ = [
    "RenderContext",
    "RenderContextMissingError",
    "get_render_context",
]


@dataclass(frozen=True, slots=True)
class RenderContext:
    """Bundle of console, capability snapshot, and chosen render profile.

    Attributes:
        console: The Rich Console used for all output.
        caps: The frozen capability snapshot captured at startup.
        profile: The render profile picked from ``caps``.
    """

    console: Console
    caps: TerminalCapabilities
    profile: RenderProfile


class RenderContextMissingError(RuntimeError):
    """Raised when ``get_render_context`` finds no context on ``ctx.obj``."""


def get_render_context(ctx: typer.Context) -> RenderContext:
    """Retrieve the :class:`RenderContext` attached to the Typer context.

    Args:
        ctx: The Typer context passed to a command callback.

    Returns:
        The :class:`RenderContext` placed on ``ctx.obj`` by the root
        ``app.callback`` at process startup.

    Raises:
        RenderContextMissingError: If ``ctx.obj`` is missing or is not a
            :class:`RenderContext` (typically because the root callback
            did not run, e.g. in a misconfigured test).
    """
    obj = ctx.obj
    if not isinstance(obj, RenderContext):
        raise RenderContextMissingError(
            "Typer context is missing a RenderContext. "
            "Ensure the root app.callback ran before the command body."
        )
    return obj
