# src/nexus/updater/__init__.py
# NEXUS self-update package (ADR-020).
# Author: Pierre Grothe
# Date: 2026-05-08
"""NEXUS auto-updater.

check_and_maybe_update() is invoked by the CLI callback before every command.
On non-editable installs, it queries the GitHub Releases API for a newer
version, downloads the wheel, runs pip install, and re-execs the user's
command with the new code.
"""

from nexus.updater.current import current_version, is_editable_install
from nexus.updater.errors import UpdaterError

__all__ = ["UpdaterError", "current_version", "is_editable_install"]
