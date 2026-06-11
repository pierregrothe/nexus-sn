#!/usr/bin/env python
# scripts/_test_direct_write.py
# Settle 3 adversarial-blocker questions empirically against alectri.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Test direct Table API writes to sys_user_role.

Q1: Does POST /api/now/table/sys_user_role with body containing sys_id
    accept the client-supplied sys_id?
Q2: Does a second POST with the same sys_id REJECT/UPSERT/CREATE-DUP?
Q3: Does a successful write produce a sys_update_xml row (auto-tracking
    via OAuth Bearer session)?
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import httpx  # noqa: E402

from nexus.cli.auth import acquire_token, oauth_for  # noqa: E402

__all__ = ["main"]


TEST_SYS_ID = "nexus0test0d1b12eacc16d58d087d5ea"  # 32 hex chars-ish (NEXUS sentinel)
TEST_NAME = "NEXUS-direct-write-test"


async def _run() -> int:
    _, meta, token, _ = acquire_token("")
    oauth = oauth_for(meta.profile, meta)
    _ = oauth
    base = meta.url.rstrip("/")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as raw:
        # Cleanup any prior test record
        existing = await raw.get(
            f"{base}/api/now/table/sys_user_role",
            headers=headers,
            params={"sysparm_query": f"name={TEST_NAME}", "sysparm_limit": "5"},
            timeout=30.0,
        )
        for row in existing.json().get("result", []):
            sys_id = row.get("sys_id")
            del_resp = await raw.delete(
                f"{base}/api/now/table/sys_user_role/{sys_id}",
                headers=headers,
                timeout=30.0,
            )
            print(
                f"cleanup: DELETE sys_user_role/{sys_id} -> {del_resp.status_code}",
                flush=True,
            )

        payload_with_sys_id = {
            "sys_id": TEST_SYS_ID,
            "name": TEST_NAME,
            "description": "live-test from NEXUS smoke",
        }

        # Q1 + Q3: first POST with sys_id
        r1 = await raw.post(
            f"{base}/api/now/table/sys_user_role",
            headers=headers,
            json=payload_with_sys_id,
            timeout=30.0,
        )
        print(f"Q1 first POST sys_user_role (sys_id={TEST_SYS_ID}) -> {r1.status_code}", flush=True)
        actual_sys_id: str | None = None
        if r1.status_code in (200, 201):
            try:
                body = r1.json()
            except Exception:  # noqa: BLE001
                print(f"   non-JSON body: {r1.text[:300]}", flush=True)
                return 1
            actual_sys_id = str(body.get("result", {}).get("sys_id", ""))
            print(f"   accepted: actual_sys_id={actual_sys_id!r}", flush=True)
            print(f"   matches requested: {actual_sys_id == TEST_SYS_ID}", flush=True)
        else:
            print(f"   error body: {r1.text[:300]}", flush=True)
            return 1

        # Q3: check sys_update_xml for our record
        await asyncio.sleep(0.5)  # SN async update-xml write
        xml_check = await raw.get(
            f"{base}/api/now/table/sys_update_xml",
            headers=headers,
            params={
                "sysparm_query": f"target_name={TEST_NAME}",
                "sysparm_limit": "5",
                "sysparm_fields": "sys_id,name,type,update_set,action",
            },
            timeout=30.0,
        )
        if xml_check.status_code == 200:
            xml_rows = xml_check.json().get("result", [])
            print(f"Q3 sys_update_xml rows for {TEST_NAME!r}: {len(xml_rows)}", flush=True)
            for row in xml_rows:
                print(f"   {row}", flush=True)
        else:
            print(f"Q3 sys_update_xml query failed: {xml_check.status_code}", flush=True)

        # Q2: second POST with same sys_id -- UPSERT? REJECT? CREATE-DUP?
        payload_v2 = {**payload_with_sys_id, "instructions": "second-run prompt"}
        r2 = await raw.post(
            f"{base}/api/now/table/sys_user_role",
            headers=headers,
            json=payload_v2,
            timeout=30.0,
        )
        print(f"Q2 second POST same sys_id -> {r2.status_code}", flush=True)
        if r2.status_code in (200, 201):
            body = r2.json()
            new_sys_id = str(body.get("result", {}).get("sys_id", ""))
            print(f"   sys_id={new_sys_id!r}  same_as_first={new_sys_id == actual_sys_id}", flush=True)
            # Count current sys_user_role rows with our name
            count = await raw.get(
                f"{base}/api/now/table/sys_user_role",
                headers=headers,
                params={"sysparm_query": f"name={TEST_NAME}", "sysparm_limit": "10"},
                timeout=30.0,
            )
            rows = count.json().get("result", []) if count.status_code == 200 else []
            print(f"   sys_user_role rows now matching name: {len(rows)}", flush=True)
        else:
            print(f"   error body: {r2.text[:300]}", flush=True)

        # Cleanup
        if actual_sys_id:
            cleanup = await raw.delete(
                f"{base}/api/now/table/sys_user_role/{actual_sys_id}",
                headers=headers,
                timeout=30.0,
            )
            print(f"final cleanup: DELETE sys_user_role/{actual_sys_id} -> {cleanup.status_code}", flush=True)

    return 0


def main() -> int:
    """Entry point."""
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
