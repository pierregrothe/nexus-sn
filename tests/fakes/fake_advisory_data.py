# tests/fakes/fake_advisory_data.py
# In-memory AdvisoryDatabase factory for unit tests.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Build canned AdvisoryDatabase instances without touching the bundled YAMLs."""

from datetime import date

from nexus.plugins.advisories import (
    AdvisoryDatabase,
    CveEntry,
    EolEntry,
    LicensePolicy,
)
from nexus.plugins.models import Severity

__all__ = ["make_advisory_database"]


def make_advisory_database() -> AdvisoryDatabase:
    """Build a fixed AdvisoryDatabase with one entry per advisory type.

    Returns:
        AdvisoryDatabase with one EOL entry, one CVE entry, one allow-list
        vendor, and one forbid-list vendor. Used by the orchestrator and
        CLI tests.
    """
    eol: dict[str, EolEntry] = {
        "com.legacy": EolEntry(
            plugin_id="com.legacy",
            status="end_of_life",
            effective=date(2020, 1, 1),
            replacement="com.modern",
            notes="",
        ),
    }
    cves: dict[str, tuple[CveEntry, ...]] = {
        "com.cms": (
            CveEntry(
                cve_id="CVE-9999-1",
                plugin_id="com.cms",
                severity=Severity.HIGH,
                affected_versions=">=1.0,<2.0",
                fixed_in="2.0",
                summary="Example XSS",
            ),
        ),
    }
    licenses = LicensePolicy(
        allowed_vendors=("ServiceNow",),
        forbidden_vendors=("Sketchy LLC",),
    )
    return AdvisoryDatabase(eol=eol, cves=cves, licenses=licenses)
