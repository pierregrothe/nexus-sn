# tests/fakes/scripted_prompt.py
# Scripted PromptSource for testing wizard flows without mocks.
# Author: Pierre Grothe
# Date: 2026-05-18
"""ScriptedPromptSource pops pre-queued answers in order.

Designed to drive ``nexus.cli.prompts.PromptSource`` consumers from
tests. Exhausting the queue raises ``PromptExhaustedError`` so an
under-specified test fails loudly instead of hanging on stdin.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from nexus.cli.prompts import PromptExhaustedError

__all__ = ["ScriptedPromptSource"]

_TRUE_TOKENS = frozenset({"y", "yes"})


class ScriptedPromptSource:
    """PromptSource that returns pre-queued answers in order.

    Args:
        answers: Iterable of strings to return on successive ``ask`` and
            ``confirm`` calls. ``confirm`` interprets the popped value as
            a boolean (``"y"`` / ``"yes"`` case-insensitive -> True,
            anything else -> False).
    """

    def __init__(self, answers: Iterable[str]) -> None:
        """See class docstring."""
        self._answers: deque[str] = deque(answers)

    def ask(self, message: str, *, hide: bool = False) -> str:
        """Pop and return the next scripted answer.

        Args:
            message: Ignored. Present for Protocol compatibility and
                surfaced in the exhaustion error for easier debugging.
            hide: Ignored. Present for Protocol compatibility.

        Returns:
            The next scripted answer.

        Raises:
            PromptExhaustedError: When no scripted answers remain.
        """
        del hide  # unused -- the scripted impl does not echo input
        if not self._answers:
            raise PromptExhaustedError(f"no scripted answer for prompt: {message!r}")
        return self._answers.popleft()

    def confirm(self, message: str) -> bool:
        """Pop the next scripted answer and interpret it as a boolean.

        Args:
            message: Ignored. Surfaced in the exhaustion error.

        Returns:
            True when the popped value is ``"y"`` or ``"yes"`` (case
            insensitive after ``strip``); False otherwise.

        Raises:
            PromptExhaustedError: When no scripted answers remain.
        """
        if not self._answers:
            raise PromptExhaustedError(f"no scripted answer for confirm: {message!r}")
        return self._answers.popleft().strip().lower() in _TRUE_TOKENS
