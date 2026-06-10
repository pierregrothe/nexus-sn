# tests/fakes/fake_kroki_client.py
# Test double for KrokiClientProtocol -- no HTTP.
# Author: Pierre Grothe
# Date: 2026-06-08
"""FakeKrokiClient: implements KrokiClientProtocol for unit tests."""

from dataclasses import dataclass, field

from nexus.api.kroki_client import ImageFormat


def _make_calls() -> list[dict[str, object]]:
    return []


__all__ = ["FakeKrokiClient"]


@dataclass(slots=True)
class FakeKrokiClient:
    """Test double for KrokiClientProtocol.

    Records every call and returns canned bytes. No HTTP.

    Attributes:
        calls: List of dicts capturing every render() invocation.
        canned: Bytes returned by render() on success.
        side_effect: Optional exception to raise instead of returning.
    """

    calls: list[dict[str, object]] = field(default_factory=_make_calls)
    canned: bytes = b"<svg/>"
    side_effect: BaseException | None = None

    async def render(
        self, source: str, *, fmt: ImageFormat, diagram_type: str = "mermaid"
    ) -> bytes:
        """Record the call and return canned bytes (or raise side_effect).

        Args:
            source: Diagram source text.
            fmt: Output image format.
            diagram_type: Kroki diagram type.

        Returns:
            The canned bytes.

        Raises:
            BaseException: If side_effect is set.
        """
        self.calls.append({"source": source, "fmt": fmt, "diagram_type": diagram_type})
        if self.side_effect is not None:
            raise self.side_effect
        return self.canned
