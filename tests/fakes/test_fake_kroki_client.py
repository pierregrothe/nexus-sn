# tests/fakes/test_fake_kroki_client.py
# Smoke test for FakeKrokiClient.
# Author: Pierre Grothe
# Date: 2026-06-08
"""FakeKrokiClient records calls and returns canned bytes."""

import pytest

from nexus.api.kroki_client import ImageFormat
from tests.fakes.fake_kroki_client import FakeKrokiClient


@pytest.mark.asyncio
async def test_render_records_call_and_returns_canned_bytes() -> None:
    fake = FakeKrokiClient(canned=b"<svg/>")
    out = await fake.render("erDiagram", fmt=ImageFormat.svg)
    assert out == b"<svg/>"
    assert fake.calls == [{"source": "erDiagram", "fmt": "svg", "diagram_type": "mermaid"}]


@pytest.mark.asyncio
async def test_render_raises_side_effect() -> None:
    fake = FakeKrokiClient(side_effect=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        await fake.render("x", fmt=ImageFormat.png)
