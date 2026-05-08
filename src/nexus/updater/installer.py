# src/nexus/updater/installer.py
# Download wheel + pip subprocess install.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Download a wheel from a URL, then `pip install --upgrade <wheel>`."""

import logging
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx

from nexus.updater.errors import UpdaterError

log = logging.getLogger(__name__)

__all__ = ["download_wheel", "pip_install_wheel"]

_DOWNLOAD_TIMEOUT_SECONDS = 30.0


def download_wheel(
    url: str,
    *,
    dest_dir: Path,
    httpx_client: httpx.Client | None = None,
) -> Path:
    """Download the wheel at ``url`` to ``dest_dir / <filename-from-url>``.

    GitHub Releases asset URLs redirect (302) to ``objects.githubusercontent.com``;
    follow_redirects=True is required for the production path.

    Args:
        url: HTTPS URL of the wheel.
        dest_dir: Directory to write to (typically a tempfile.TemporaryDirectory).
        httpx_client: Optional pre-built client (for tests). Default: new
            short-lived client.

    Returns:
        Local path to the downloaded wheel.

    Raises:
        UpdaterError: On network failure or non-200 response.
    """
    filename = Path(urlparse(url).path).name
    target = dest_dir / filename
    try:
        if httpx_client is not None:
            response = httpx_client.get(url, follow_redirects=True)
        else:
            with httpx.Client(timeout=_DOWNLOAD_TIMEOUT_SECONDS) as client:
                response = client.get(url, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise UpdaterError(f"network error downloading wheel: {exc}") from exc
    if response.status_code != 200:
        raise UpdaterError(f"wheel download returned status={response.status_code} url={url}")
    target.write_bytes(response.content)
    log.info("downloaded wheel: %s (%d bytes)", target.name, len(response.content))
    return target


def pip_install_wheel(wheel_path: Path) -> None:
    """Run `<python> -m pip install --upgrade <wheel_path>`.

    Args:
        wheel_path: Local path to a downloaded .whl file.

    Raises:
        UpdaterError: When pip exits non-zero. Includes stderr in the message.
    """
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", str(wheel_path)]
    log.info("running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise UpdaterError(
            f"pip install failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    log.info("pip install succeeded")
