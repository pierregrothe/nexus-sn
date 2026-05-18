# src/nexus/cli/prompts.py
# Typed prompt abstraction for testable wizard flows.
# Author: Pierre Grothe
# Date: 2026-05-18
"""PromptSource Protocol + Typer-backed and scripted implementations.

The wizard code in ``nexus setup`` / ``nexus instance register`` takes
a ``PromptSource`` parameter instead of calling ``typer.prompt``
directly, so tests can drive the flow with a ``ScriptedPromptSource``
without patching the ``typer`` module. The no-mocks rule forbids
patching; this abstraction is how we comply.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import typer

__all__ = [
    "PromptExhaustedError",
    "PromptSource",
    "TyperPromptSource",
]


class PromptExhaustedError(RuntimeError):
    """Raised by scripted PromptSource impls when no more answers are queued.

    Existence of this exception means a test under-specified its scripted
    answers. Tests should fail loudly here rather than hang in production
    code waiting on stdin.
    """


@runtime_checkable
class PromptSource(Protocol):
    """Interactive input contract used by the setup / register wizards.

    Implementations:
        * ``TyperPromptSource`` -- production, forwards to ``typer.prompt``.
        * ``ScriptedPromptSource`` (in tests/fakes) -- scripted answers.
    """

    def ask(self, message: str, *, hide: bool = False) -> str:
        """Return the user's answer to ``message``.

        Args:
            message: Prompt label shown to the user.
            hide: When True, suppress echo (for passwords and secrets).

        Returns:
            The user's input as a string.
        """
        ...  # pragma: no cover -- Protocol stub, never executed

    def confirm(self, message: str) -> bool:
        """Return True if the user confirms ``message``, else False.

        Args:
            message: Yes/no question label shown to the user.

        Returns:
            True for an affirmative answer, False otherwise.
        """
        ...  # pragma: no cover -- Protocol stub, never executed


@dataclass(frozen=True, slots=True)
class TyperPromptSource:
    """Production ``PromptSource`` -- forwards to ``typer.prompt`` / ``typer.confirm``.

    Attributes:
        prompt_fn: Callable invoked for ``ask``. Defaults to
            ``typer.prompt``. Tests of this class inject a lightweight
            callable instead of patching the ``typer`` module.
        confirm_fn: Callable invoked for ``confirm``. Defaults to
            ``typer.confirm``.
    """

    prompt_fn: Callable[..., str] = field(default=typer.prompt)
    confirm_fn: Callable[..., bool] = field(default=typer.confirm)

    def ask(self, message: str, *, hide: bool = False) -> str:
        """Forward to ``prompt_fn`` with ``hide_input`` mapped from ``hide``."""
        return self.prompt_fn(message, hide_input=hide, confirmation_prompt=False)

    def confirm(self, message: str) -> bool:
        """Forward to ``confirm_fn``."""
        return self.confirm_fn(message)
