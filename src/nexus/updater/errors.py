# src/nexus/updater/errors.py
# Updater-layer exceptions. All caught by check_and_maybe_update; never escape.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Exception types for the auto-updater."""

__all__ = ["UpdaterError"]


class UpdaterError(Exception):
    """Raised by updater internals when an update step fails.

    The runner catches this and falls back to running the current version.
    Never escapes user-facing code.
    """
