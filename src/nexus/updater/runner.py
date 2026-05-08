# src/nexus/updater/runner.py
# The auto-update orchestrator. Called by the CLI callback before every command.
# Author: Pierre Grothe
# Date: 2026-05-08
"""check_and_maybe_update: runs the version check + install + re-exec.

Never raises. On any failure, logs and returns silently so the user's
command can continue with the current code.
"""

import io
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from packaging.version import InvalidVersion, parse

from nexus.config.paths import NexusPaths
from nexus.updater.client import GitHubReleasesClient, ReleaseInfo
from nexus.updater.current import current_version, is_editable_install
from nexus.updater.errors import UpdaterError
from nexus.updater.installer import download_wheel, pip_install_wheel

if sys.platform == "win32":
    import msvcrt  # pragma: no cover
else:
    import fcntl

log = logging.getLogger(__name__)

__all__ = ["check_and_maybe_update"]

_ENV_DISABLE = "NEXUS_AUTO_UPDATE"
_CHECK_INTERVAL_SECONDS = 24 * 60 * 60  # 24 hours
_LockHandle = io.IOBase


def check_and_maybe_update() -> None:
    """Entry point invoked by the CLI callback before every command.

    Returns silently on any non-actionable condition; logs and continues
    on any failure. Re-execs the process on successful install.
    """
    if is_editable_install():
        log.debug("editable install detected; skipping auto-update")
        return
    if os.environ.get(_ENV_DISABLE) == "0":
        log.debug("NEXUS_AUTO_UPDATE=0; skipping auto-update")
        return

    current = current_version()
    if current is None:
        log.debug("nexus-sn not installed as a distribution; skipping auto-update")
        return

    if not _should_check_now():
        log.debug("last update check is recent; skipping")
        return

    lock = _try_acquire_lock()
    if lock is None:
        log.debug("update lockfile held by another process; skipping")
        return

    try:
        _run_update_cycle(current)
    finally:
        _release_lock(lock)


def _run_update_cycle(current: str) -> None:
    """Inner update logic. Caller holds the lock.

    Args:
        current: The currently installed version string.
    """
    info = _build_client().fetch_latest()
    _record_check_attempt()
    if info is None:
        return
    if info.wheel_url is None:
        log.warning("latest release %s has no wheel asset; skipping", info.tag_name)
        return

    try:
        latest_v = parse(info.tag_name)
        current_v = parse(current)
    except InvalidVersion as exc:
        log.warning("could not parse version: %s", exc)
        return

    if latest_v <= current_v:
        log.debug("already on latest version %s", current)
        return

    print(f"NEXUS updating {current} -> {info.tag_name}...", flush=True)
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            wheel_path = download_wheel(info.wheel_url, dest_dir=Path(tmpdir))
            pip_install_wheel(wheel_path)
    except UpdaterError as exc:
        log.error("auto-update failed: %s", exc)
        return

    print(f"NEXUS updated to {info.tag_name}", flush=True)
    _re_exec(info)


def _re_exec(info: ReleaseInfo) -> None:
    """Re-run the user's command with the new code.

    On Linux/macOS: os.execv replaces the process.
    On Windows: subprocess.run + sys.exit (os.execv has shell-prompt quirks).

    Args:
        info: The release info that was just installed (used in the fallback log).
    """
    argv = list(sys.argv)
    try:
        if sys.platform == "win32":
            result = subprocess.run(argv, check=False)
            sys.exit(result.returncode)
        os.execv(argv[0], argv)
    except OSError as exc:
        log.error("could not re-exec after update: %s", exc)
        log.info("update %s installed; please re-run your command", info.tag_name)


def _build_client() -> GitHubReleasesClient:
    """Construct the production GitHubReleasesClient.

    Tests monkeypatch this to inject FakeGitHubReleasesClient.

    Returns:
        A GitHubReleasesClient pointed at the default repo.
    """
    return GitHubReleasesClient()


def _lock_path() -> Path:
    """Return the path of the update lockfile.

    Tests monkeypatch this to redirect to tmp_path. The parent directory
    is created on first access via NexusPaths.ensure_dirs() / mkdir below.

    Returns:
        Path to ~/.nexus/cache/update.lock.
    """
    cache_dir = NexusPaths.from_env().cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "update.lock"


def _last_check_path() -> Path:
    """Return the marker file whose mtime gates the next GitHub call."""
    return _lock_path().with_name("update.last_check")


def _should_check_now() -> bool:
    """True when the last successful (or attempted) check is older than the interval."""
    marker = _last_check_path()
    try:
        age = time.time() - marker.stat().st_mtime
    except FileNotFoundError:
        return True
    return age >= _CHECK_INTERVAL_SECONDS


def _record_check_attempt() -> None:
    """Update the marker so the next launch waits for the configured interval."""
    marker = _last_check_path()
    marker.touch(exist_ok=True)
    os.utime(marker, None)


def _try_acquire_lock() -> _LockHandle | None:
    """Try to acquire an exclusive lock. Return a handle or None if held.

    Cross-platform: fcntl on POSIX, msvcrt on Windows.

    Returns:
        The open file handle on success, or None if the lock is held.
    """
    # Mode "a" creates the file if missing without truncating concurrent writers.
    handle = _lock_path().open("a")
    try:
        if sys.platform == "win32":  # pragma: no cover
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def _release_lock(lock: _LockHandle) -> None:
    """Release the lock acquired by _try_acquire_lock."""
    try:
        if sys.platform == "win32":  # pragma: no cover
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    finally:
        lock.close()
