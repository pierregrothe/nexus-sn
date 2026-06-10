# tests/api/test_kroki_client.py
# Tests for KrokiClient against an httpx MockTransport.
# Author: Pierre Grothe
# Date: 2026-06-08
"""KrokiClient POSTs Mermaid source and returns image bytes."""

import httpx
import pytest

from nexus.api.errors import KrokiError
from nexus.api.kroki_client import ImageFormat, KrokiClient

_SVG = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"


@pytest.mark.asyncio
async def test_render_returns_image_bytes() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=_SVG))
    client = KrokiClient("https://kroki.io", transport=transport)
    assert await client.render("mindmap\n  root((X))", fmt=ImageFormat.svg) == _SVG


@pytest.mark.asyncio
async def test_render_posts_source_to_typed_endpoint() -> None:
    seen: dict[str, object] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["method"] = req.method
        seen["body"] = req.content
        return httpx.Response(200, content=_SVG)

    client = KrokiClient("https://kroki.io/", transport=httpx.MockTransport(handler))
    await client.render("erDiagram", fmt=ImageFormat.png)
    assert seen["url"] == "https://kroki.io/mermaid/png"
    assert seen["method"] == "POST"
    assert seen["body"] == b"erDiagram"


@pytest.mark.asyncio
async def test_render_non_2xx_raises_kroki_error() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(400, text="bad diagram"))
    client = KrokiClient("https://kroki.io", transport=transport)
    with pytest.raises(KrokiError) as exc:
        await client.render("not a diagram", fmt=ImageFormat.svg)
    assert exc.value.status_code == 400
    assert "bad diagram" in exc.value.message


@pytest.mark.asyncio
async def test_render_honors_custom_timeout() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=_SVG))
    client = KrokiClient("https://kroki.io", timeout=5.0, transport=transport)
    assert await client.render("mindmap", fmt=ImageFormat.svg) == _SVG


@pytest.mark.asyncio
async def test_render_transport_error_wrapped_as_kroki_error() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=req)

    client = KrokiClient("https://kroki.io", transport=httpx.MockTransport(handler))
    with pytest.raises(KrokiError) as exc:
        await client.render("erDiagram", fmt=ImageFormat.svg)
    assert exc.value.status_code is None
    assert "https://kroki.io" in exc.value.message
    assert "connection refused" in exc.value.message


@pytest.mark.asyncio
async def test_render_non_200_success_status_returns_bytes() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(201, content=_SVG))
    client = KrokiClient("https://kroki.io", transport=transport)
    assert await client.render("erDiagram", fmt=ImageFormat.svg) == _SVG
