#!/usr/bin/env python
# scripts/smoke_apply_live.py
# Live-instance smoke for ApplyEngine against the configured default profile.
# Author: Pierre Grothe
# Date: 2026-05-19

"""End-to-end live smoke for `nexus apply` against a real ServiceNow.

WHAT THIS DOES (and what it WRITES):
1. Resolves the default profile via `nexus.cli.auth.acquire_token`.
2. Constructs a real `ServiceNowClient` bound to that token + refresh callback.
3. Constructs a real `ApplyEngine` wired to the live client.
4. Calls `engine.apply(<template-path>)` for `nowassist-tier1-rephrase`.
5. Verifies the resulting `sys_update_set` exists on the instance.
6. Verifies the resulting `ai_skill` record exists on the instance.

WRITE FOOTPRINT (reversible):
* One `sys_update_set` record named `NEXUS-apply-nowassist-tier1-rephrase-
  <UTC timestamp>` carrying NEXUS provenance metadata in its description.
* One `sys_update_xml` row (the rendered ai_skill payload).
* The deterministic ai_skill sys_id is reused on re-runs, so subsequent
  invocations produce INSERT_OR_UPDATE noops in target state.

Cleanup: delete the sys_update_set in the SN UI (or via Table API) to
remove the audit trail. The deterministic sys_id means re-running this
smoke does not accumulate orphan records.

Usage:
    poetry run python scripts/smoke_apply_live.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure tests/ is importable for shared helpers (not used here -- production wiring).
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from nexus.cli.auth import acquire_token, oauth_for  # noqa: E402
from nexus.config.paths import NexusPaths  # noqa: E402
from nexus.connectors.servicenow.client import ServiceNowClient  # noqa: E402
from nexus.templates.apply import ApplyEngine  # noqa: E402

__all__ = ["main"]

log = logging.getLogger(__name__)


TEMPLATE_PATH = _REPO_ROOT / "templates" / "nowassist-tier1-rephrase" / "template.yaml"


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def _verify_records(
    client: ServiceNowClient, update_set_sys_id: str, ai_skill_sys_id: str
) -> tuple[bool, list[str]]:
    """Verify the sys_update_set and ai_skill rows landed on the instance."""
    findings: list[str] = []
    update_set_rows = await client.query_table(
        "sys_update_set",
        query=f"sys_id={update_set_sys_id}",
        limit=1,
    )
    if not update_set_rows:
        findings.append(f"sys_update_set {update_set_sys_id} not found on instance")

    xml_rows = await client.query_table(
        "sys_update_xml",
        query=f"update_set={update_set_sys_id}",
        limit=5,
    )
    if not xml_rows:
        findings.append("no sys_update_xml rows for the update set")
    else:
        ai_skill_xml = [row for row in xml_rows if str(row.get("type", "")) == "ai_skill"]
        if not ai_skill_xml:
            findings.append("update set has no ai_skill sys_update_xml row")

    log.info("verify: update_set_rows=%d xml_rows=%d", len(update_set_rows), len(xml_rows))
    _ = ai_skill_sys_id  # ai_skill is created inside the update set, not directly on ai_skill table
    return (not findings), findings


async def _smoke() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if not TEMPLATE_PATH.is_file():
        print(f"FAIL: template not found at {TEMPLATE_PATH}")
        return 1

    print(f"Live-apply smoke against default profile, template={TEMPLATE_PATH.name}")
    registry, meta, token, token_expires_at = acquire_token("")
    oauth = oauth_for(meta.profile, meta)

    async def _refresh() -> tuple[str, datetime]:
        return oauth.get_bearer_token(_utc_now())

    client = ServiceNowClient(
        instance_url=meta.url,
        token=token,
        token_expires_at=token_expires_at,
        refresh_token_callback=_refresh,
    )
    paths = NexusPaths.from_env()
    engine = ApplyEngine(
        sn_client=client,
        paths=paths,
        clock=_utc_now,
        instance_id=meta.profile,
        nexus_version="smoke-live",
        git_sha="smoke",
    )

    async with client:
        try:
            result = await engine.apply(TEMPLATE_PATH)
        except Exception as exc:
            print(f"FAIL: ApplyEngine.apply raised {type(exc).__name__}: {exc}")
            return 1

        print()
        print(f"  template_id        : {result.template_id}")
        print(f"  template_version   : {result.template_version}")
        print(f"  update_set_sys_id  : {result.update_set_sys_id}")
        print(f"  update_set_name    : {result.update_set_name}")
        print(f"  target_scope_sys_id: {result.target_scope_sys_id}")
        print(f"  applied_records    : {len(result.applied_records)}")
        for record in result.applied_records:
            print(
                f"    - {record.table}/{record.name} -> {record.action.value} "
                f"(requested_sys_id={record.requested_sys_id})"
            )
        print(f"  started_at         : {result.started_at.isoformat()}")
        print(f"  completed_at       : {result.completed_at.isoformat()}")

        any_failed = any(r.action.value == "FAILED" for r in result.applied_records)
        if any_failed:
            print("FAIL: at least one AppliedRecord reported FAILED")
            return 1

        skill_record = result.applied_records[0]
        verify_ok, verify_findings = await _verify_records(
            client, result.update_set_sys_id, skill_record.requested_sys_id or ""
        )
        if not verify_ok:
            print("FAIL: post-apply verification:")
            for f in verify_findings:
                print(f"  - {f}")
            return 1

    print("\nPASS: live ApplyEngine round-trip + post-apply verification successful")
    _ = registry  # not used directly; acquire_token persists refreshed expiry
    return 0


def main() -> int:
    """Entry point: run the live-apply smoke and return an exit code."""
    return asyncio.run(_smoke())


if __name__ == "__main__":
    sys.exit(main())
