# src/nexus/updater/current.py
# Read installed nexus-sn version + detect editable installs.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Version detection helpers for the auto-updater."""

import logging
from importlib import metadata

log = logging.getLogger(__name__)

__all__ = ["current_version", "is_editable_install"]

_PACKAGE_NAME = "nexus-sn"


def current_version() -> str | None:
    """Return the installed nexus-sn version, or None if not installed.

    Returns:
        The version string (e.g., "2026.05.1") when nexus-sn is installed
        as a distribution. None when running directly from a source clone
        without `pip install`.
    """
    try:
        return metadata.version(_PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        log.debug("nexus-sn not installed as a distribution")
        return None


def is_editable_install() -> bool:
    """Return True if nexus-sn was installed via `pip install -e .` (PEP 660).

    Reads importlib.metadata.distribution("nexus-sn").origin.dir_info.editable.
    Returns False on any failure (package not installed, missing origin,
    older distribution metadata).
    """
    try:
        dist = metadata.distribution(_PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return False
    origin = getattr(dist, "origin", None)
    if origin is None:
        return False
    dir_info = getattr(origin, "dir_info", None)
    if dir_info is None:
        return False
    return bool(getattr(dir_info, "editable", False))
