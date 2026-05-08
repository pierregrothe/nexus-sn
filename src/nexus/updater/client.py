# src/nexus/updater/client.py
# Tiny GitHub Releases API client. Never raises -- failures return None.
# Author: Pierre Grothe
# Date: 2026-05-08
"""GitHubReleasesClient: read /repos/<owner>/<name>/releases/latest.

Returns ReleaseInfo with the tag and wheel URL, or None on any failure
(network down, 404, 403 rate limit, malformed JSON, missing tag_name).
"""

import logging
from dataclasses import dataclass
from typing import cast

import httpx

log = logging.getLogger(__name__)

__all__ = ["GitHubReleasesClient", "ReleaseInfo"]

_DEFAULT_REPO = "pierregrothe/nexus-sn"
_DEFAULT_TIMEOUT_SECONDS = 3.0


@dataclass(slots=True, frozen=True)
class ReleaseInfo:
    """Subset of GitHub Releases API response we use.

    Attributes:
        tag_name: Release tag (e.g., "2026.06.0").
        wheel_url: HTTPS URL of the .whl asset, or None if the release
            has no wheel attached.
    """

    tag_name: str
    wheel_url: str | None


class GitHubReleasesClient:
    """Read /repos/<repo>/releases/latest. Never raises.

    Args:
        repo: "<owner>/<name>" string. Default "pierregrothe/nexus-sn".
        timeout_seconds: HTTP timeout. Default 3.0.
        httpx_client: Optional pre-built client (for tests with MockTransport).
            If None, a default client is constructed at fetch time.
    """

    def __init__(
        self,
        *,
        repo: str = _DEFAULT_REPO,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        httpx_client: httpx.Client | None = None,
    ) -> None:
        """See class docstring."""
        self._repo = repo
        self._timeout = timeout_seconds
        self._injected_client = httpx_client

    def fetch_latest(self) -> ReleaseInfo | None:
        """GET /repos/<repo>/releases/latest. Return None on any failure.

        Returns:
            ReleaseInfo with tag_name and optional wheel_url, or None on
            any network error, non-200 status, malformed JSON, or missing
            tag_name field.
        """
        url = f"https://api.github.com/repos/{self._repo}/releases/latest"
        try:
            if self._injected_client is not None:
                response = self._injected_client.get(url)
            else:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.get(url)
        except httpx.HTTPError as exc:
            log.info("GitHub Releases fetch failed: %s", exc)
            return None
        if response.status_code != 200:
            log.warning(
                "GitHub Releases returned status=%d body=%r",
                response.status_code,
                response.text[:200],
            )
            return None
        try:
            data = response.json()
        except ValueError:
            log.warning("GitHub Releases returned non-JSON body")
            return None
        if not isinstance(data, dict):
            log.warning("GitHub Releases response is not a JSON object")
            return None
        payload = cast("dict[str, object]", data)
        tag = payload.get("tag_name")
        if not isinstance(tag, str):
            log.warning("GitHub Releases response missing tag_name")
            return None
        wheel_url = _extract_wheel_url(payload)
        return ReleaseInfo(tag_name=tag, wheel_url=wheel_url)


def _extract_wheel_url(payload: dict[str, object]) -> str | None:
    """Find the first asset whose name ends in .whl and return its download URL.

    Args:
        payload: Parsed JSON object from the GitHub Releases API response.

    Returns:
        The browser_download_url of the first .whl asset, or None if no
        such asset exists or the assets field is malformed.
    """
    assets_raw = payload.get("assets", [])
    if not isinstance(assets_raw, list):
        return None
    for entry in cast("list[object]", assets_raw):
        if not isinstance(entry, dict):
            continue
        asset = cast("dict[str, object]", entry)
        name = asset.get("name")
        url = asset.get("browser_download_url")
        if isinstance(name, str) and name.endswith(".whl") and isinstance(url, str):
            return url
    return None
