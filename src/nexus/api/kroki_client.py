# src/nexus/api/kroki_client.py
# KrokiClient: async HTTP client that renders diagram source to image bytes.
# Author: Pierre Grothe
# Date: 2026-06-08
"""KrokiClient: POST Mermaid source to a Kroki service, return image bytes."""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Protocol

import httpx

from nexus.api.errors import KrokiError

log = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_KROKI_TIMEOUT",
    "DEFAULT_KROKI_URL",
    "ImageFormat",
    "KrokiClient",
    "KrokiClientProtocol",
]

DEFAULT_KROKI_URL: str = "https://kroki.io"
DEFAULT_KROKI_TIMEOUT: float = 60.0

_ERR_BODY_CHARS = 500


class ImageFormat(StrEnum):
    """Supported diagram image formats for Kroki rendering."""

    svg = "svg"
    png = "png"


class KrokiClientProtocol(Protocol):
    """Renders diagram source text to image bytes via a Kroki service."""

    async def render(
        self, source: str, *, fmt: ImageFormat, diagram_type: str = "mermaid"
    ) -> bytes:
        """Render diagram source to image bytes.

        Args:
            source: Diagram source text (e.g. a Mermaid block body).
            fmt: Output image format.
            diagram_type: Kroki diagram type. Defaults to "mermaid".

        Returns:
            The rendered image bytes.

        Raises:
            KrokiError: When the service returns a non-2xx status, or when
                the request fails at the transport level (status_code None).
        """
        ...


class KrokiClient:
    """Async Kroki client. Opens a short-lived httpx client per render call.

    Args:
        base_url: Kroki endpoint root. Defaults to ``DEFAULT_KROKI_URL``.
        timeout: Per-request timeout in seconds. Dense diagrams on a busy
            endpoint can be slow; raise this (or self-host) if renders time out.
        transport: Optional httpx transport (test seam; house pattern).
    """

    def __init__(
        self,
        base_url: str = DEFAULT_KROKI_URL,
        *,
        timeout: float = DEFAULT_KROKI_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Initialize with a base URL, request timeout, and optional transport."""
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport

    async def render(
        self, source: str, *, fmt: ImageFormat, diagram_type: str = "mermaid"
    ) -> bytes:
        """Render diagram source to image bytes via POST.

        Args:
            source: Diagram source text.
            fmt: Output image format.
            diagram_type: Kroki diagram type. Defaults to "mermaid".

        Returns:
            The rendered image bytes.

        Raises:
            KrokiError: When the service returns a non-2xx status, or when
                the request fails at the transport level (status_code None).
        """
        url = f"{self._base_url}/{diagram_type}/{fmt}"
        log.debug("Kroki render %s (%d chars)", url, len(source))
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(
                    url, content=source.encode("utf-8"), headers={"Content-Type": "text/plain"}
                )
        except httpx.HTTPError as exc:
            raise KrokiError(None, f"could not reach Kroki at {self._base_url}: {exc}") from exc
        if not response.is_success:
            raise KrokiError(response.status_code, response.text[:_ERR_BODY_CHARS])
        return response.content
