# tests/fakes/fake_agent_client.py
# Test double for AgentClientProtocol -- no Agent SDK / subprocess.
# Author: Pierre Grothe
# Date: 2026-05-08

"""FakeAgentClient: implements AgentClientProtocol for unit tests."""

from dataclasses import dataclass, field


def _make_calls() -> list[dict[str, object]]:
    return []


__all__ = ["FakeAgentClient"]


@dataclass(slots=True)
class FakeAgentClient:
    """Test double for AgentClientProtocol.

    Records every call and returns canned_response. No subprocess, no Agent SDK.

    Attributes:
        calls: List of dicts capturing every complete() invocation.
        canned_response: String returned by complete() on success.
        side_effect: Optional exception to raise instead of returning.
    """

    calls: list[dict[str, object]] = field(default_factory=_make_calls)
    canned_response: str = "ok"
    side_effect: BaseException | None = None

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        max_turns: int = 1,
    ) -> str:
        """Record the call and return canned_response (or raise side_effect).

        Args:
            prompt: User-facing prompt sent to the agent.
            system: Optional system prompt.
            model: Optional model ID.
            max_turns: Maximum agent turns.

        Returns:
            canned_response string.

        Raises:
            BaseException: If side_effect is set.
        """
        self.calls.append(
            {
                "prompt": prompt,
                "system": system,
                "model": model,
                "max_turns": max_turns,
            }
        )
        if self.side_effect is not None:
            raise self.side_effect
        return self.canned_response
