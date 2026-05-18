# src/nexus/plugins/error_classification.py
# Pattern matchers for SN-side errors the executor converts into typed outcomes.
# Author: Pierre Grothe
# Date: 2026-05-16
"""Substring-based classification of SN response bodies.

The plugin executor wraps SN errors in ``OperationResult`` rows. A few
SN-side conditions deserve specific outcomes rather than the raw error
body:

* **Already installed** (HTTP 400 "Application version is currently
  installed") -- a true no-op success.
* **Offering plugin required** (HTTP 500 wrapping "Offering plugin id
  must be specified for application") -- a clean failure with an
  actionable message instead of the glide stack trace.

Both conditions surface from two places (the ``submit_*`` call and the
progress-poll terminal status) so the matchers live here rather than
being duplicated inline. Markers are lowercase substring matches:
permissive enough to survive SN release wording changes without
silently regressing.
"""

from __future__ import annotations

__all__ = [
    "OFFERING_PLUGIN_FAILURE_MESSAGE",
    "is_already_installed_error",
    "is_offering_plugin_error",
]


_ALREADY_INSTALLED_MARKERS = ("application version is currently installed",)


# SN's app-manager refuses to install/upgrade "offering plugins" (e.g.
# Healthcare Solutions sn_hs_* family, Financial Services sn_fs_* family)
# from the REST endpoint NEXUS calls. The real offering install path
# lives in AppUpgradeAjaxProcessor.install and is reachable only via
# /xmlhttp.do with session-cookie auth, which OAuth Bearer cannot
# obtain. We detect the failure here and surface a clean message that
# tells the user to use the SN UI.
_OFFERING_PLUGIN_MARKERS = ("offering plugin id must be specified",)


OFFERING_PLUGIN_FAILURE_MESSAGE = (
    "Offering plugin (install via SN UI -- AJAX-only path, OAuth/REST cannot dispatch)"
)
"""User-facing message for offering-plugin install/upgrade failures.

SN's offering install code path lives in ``AppUpgradeAjaxProcessor.install``
(scope ``sn_appclient``) and is reachable only via ``/xmlhttp.do`` with
session-cookie auth. Bearer-token OAuth is rejected (``401 invalid token``).
The REST endpoint NEXUS calls -- ``/api/sn_appclient/appmanager/app/install``
-- routes through ``AppUpgrader.installAndUpdateApps``, which hardcodes
``jumboAppArgs=undefined`` (line 1042 as of Zurich). The offering id has
nowhere to land on that code path. Documented so future contributors
don't re-walk the search.
"""


def is_already_installed_error(exc: Exception) -> bool:
    """Return True when SN reports the target version is already live.

    Args:
        exc: Exception raised by ``submit_install`` / ``submit_upgrade``
            or by the progress poller.

    Returns:
        True when the wrapped error body matches an already-installed marker.
    """
    message = str(exc).lower()
    return any(marker in message for marker in _ALREADY_INSTALLED_MARKERS)


def is_offering_plugin_error(exc: Exception) -> bool:
    """Return True when SN reports an offering plugin id is required.

    Offering plugins (Healthcare Solutions, Financial Services, etc.)
    cannot be installed/upgraded via the standard appmanager endpoint;
    they need a separate offering-aware endpoint NEXUS does not yet
    implement.

    Args:
        exc: Exception raised by ``submit_install`` / ``submit_upgrade``
            or by the progress poller.

    Returns:
        True when the wrapped error body matches an offering-plugin marker.
    """
    message = str(exc).lower()
    return any(marker in message for marker in _OFFERING_PLUGIN_MARKERS)
