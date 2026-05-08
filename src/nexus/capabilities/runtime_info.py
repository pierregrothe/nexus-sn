# src/nexus/capabilities/runtime_info.py
# Collects runtime + environment metadata used by `nexus status`.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Collect runtime metadata for `nexus status`.

Surfaces nexus version, Python, platform, install mode, cache size, and
auto-update timing. All getters defend against missing files / malformed
state and return None or zero rather than raising; `nexus status` must
never crash on missing data.
"""

import logging
import os
import platform
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from nexus.config.paths import NexusPaths
from nexus.updater.current import current_version, is_editable_install

log = logging.getLogger(__name__)

__all__ = ["RuntimeInfo", "collect_runtime_info"]

_AUTO_UPDATE_DISABLE_VAR = "NEXUS_AUTO_UPDATE"
_LAST_CHECK_FILE = "update.last_check"


@dataclass(slots=True, frozen=True)
class RuntimeInfo:
    """Snapshot of NEXUS runtime metadata for `nexus status`.

    Attributes:
        nexus_version: Installed nexus-sn version, or None if not installed.
        python_version: Three-component Python version string ("3.14.3").
        platform_label: Human-readable platform string ("Darwin 25.4.0 arm64").
        install_mode: "editable" (pip install -e .), "wheel" (regular install),
            or "source" (running from a checkout without `pip install`).
        config_root: NexusPaths.from_env().root.
        cache_size_bytes: Sum of file sizes under ~/.nexus/cache.
        auto_update_enabled: False when NEXUS_AUTO_UPDATE=0.
        last_update_check_ago_seconds: Seconds since the auto-updater last
            queried GitHub. None when the marker file is absent.
    """

    nexus_version: str | None
    python_version: str
    platform_label: str
    install_mode: str
    config_root: Path
    cache_size_bytes: int
    auto_update_enabled: bool
    last_update_check_ago_seconds: float | None


def collect_runtime_info() -> RuntimeInfo:
    """Build a RuntimeInfo from the current process + filesystem state.

    Returns:
        Best-effort runtime snapshot. Never raises.
    """
    paths = NexusPaths.from_env()
    return RuntimeInfo(
        nexus_version=current_version(),
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        platform_label=_platform_label(),
        install_mode=_install_mode(),
        config_root=paths.root,
        cache_size_bytes=_cache_size_bytes(paths.cache_dir),
        auto_update_enabled=os.environ.get(_AUTO_UPDATE_DISABLE_VAR) != "0",
        last_update_check_ago_seconds=_last_check_age(paths.cache_dir),
    )


def _platform_label() -> str:
    return f"{platform.system()} {platform.release()} {platform.machine()}"


def _install_mode() -> str:
    if current_version() is None:
        return "source"
    return "editable" if is_editable_install() else "wheel"


def _cache_size_bytes(cache_dir: Path) -> int:
    if not cache_dir.is_dir():
        return 0
    total = 0
    try:
        for entry in cache_dir.rglob("*"):
            if entry.is_file():
                total += entry.stat().st_size
    except OSError as exc:
        log.debug("cache size read failed: %s", exc)
        return 0
    return total


def _last_check_age(cache_dir: Path) -> float | None:
    marker = cache_dir / _LAST_CHECK_FILE
    try:
        return time.time() - marker.stat().st_mtime
    except FileNotFoundError:
        return None
    except OSError as exc:
        log.debug("last-check stat failed: %s", exc)
        return None
