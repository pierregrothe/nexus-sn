# src/nexus/api/kroki_client.py
# KrokiClient: async HTTP client that renders diagram source to image bytes.
# Author: Pierre Grothe
# Date: 2026-06-08
"""KrokiClient: POST Mermaid source to a Kroki service, return image bytes."""

from __future__ import annotations

import logging
from typing import Protocol

import httpx

from nexus.api.errors import KrokiError

log = logging.getLogger(__name__)

__all__ = ["KrokiClient", "KrokiClientProtocol"]

_DEFAULT_TIMEOUT = 60.0
_ERR_BODY_CHARS = 500


class KrokiClientProtocol(Protocol):
    """Renders diagram source text to image bytes via a Kroki service."""

    async def render(self, source: str, *, fmt: str, diagram_type: str = "mermaid") -> bytes:
        """Render diagram source to image bytes.

        Args:
            source: Diagram source text (e.g. a Mermaid block body).
            fmt: Output format, e.g. "svg" or "png".
            diagram_type: Kroki diagram type. Defaults to "mermaid".

        Returns:
            The rendered image bytes.

        Raises:
            KrokiError: When the service returns a non-2xx status.
        """
        ...


class KrokiClient:
    """Async Kroki client. Opens a short-lived httpx client per render call.

    Args:
        base_url: Kroki endpoint root, e.g. "https://kroki.io".
        timeout: Per-request timeout in seconds. Dense diagrams on a busy
            endpoint can be slow; raise this (or self-host) if renders time out.
        transport: Optional httpx transport (test seam; house pattern).
    """

    def __init__(
        self,
        base_url: str = "https://kroki.io",
        *,
        timeout: float = _DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Initialize with a base URL, request timeout, and optional transport."""
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport

    async def render(self, source: str, *, fmt: str, diagram_type: str = "mermaid") -> bytes:
        """Render diagram source to image bytes via POST.

        Args:
            source: Diagram source text.
            fmt: Output format ("svg" or "png").
            diagram_type: Kroki diagram type. Defaults to "mermaid".

        Returns:
            The rendered image bytes.

        Raises:
            KrokiError: When the service returns a non-2xx status.
        """
        url = f"{self._base_url}/{diagram_type}/{fmt}"
        log.debug("Kroki render %s (%d chars)", url, len(source))
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            response = await client.post(
                url, content=source.encode("utf-8"), headers={"Content-Type": "text/plain"}
            )
        if response.status_code != 200:
            raise KrokiError(response.status_code, response.text[:_ERR_BODY_CHARS])
        return response.content
