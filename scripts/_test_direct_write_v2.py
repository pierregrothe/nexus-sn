#!/usr/bin/env python
# scripts/_test_direct_write_v2.py
# Resilient direct-write probe -- Q1 sys_id accept, Q2 re-POST, Q3 auto-tracking.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Direct Table API probe on a baseline writable table."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import httpx  # noqa: E402

from nexus.cli.auth import acquire_token  # noqa: E402

__all__ = ["main"]


TEST_SYS_ID = "nexus0test0d1b12eacc16d58d087d5e"  # 32 hex chars
TEST_NAME = "NEXUS-direct-write-test"
TABLE = "sys_user_role"


async def _delete_existing(raw: httpx.AsyncClient, base: str, headers: dict[str, str]) -> None:
    existing = await raw.get(
        f"{base}/api/now/table/{TABLE}",
        headers=headers,
        params={"sysparm_query": f"name={TEST_NAME}", "sysparm_limit": "5"},
        timeout=30.0,
    )
    if existing.status_code != 200:
        return
    rows = existing.json().get("result", [])
    for row in rows:
        sys_id = row.get("sys_id")
        await raw.delete(
            f"{base}/api/now/table/{TABLE}/{sys_id}", headers=headers, timeout=30.0
        )
        print(f"   cleanup: removed {sys_id}", flush=True)


async def _query_sys_id(raw: httpx.AsyncClient, base: str, headers: dict[str, str]) -> str | None:
    response = await raw.get(
        f"{base}/api/now/table/{TABLE}",
        headers=headers,
        params={"sysparm_query": f"name={TEST_NAME}", "sysparm_limit": "1"},
        timeout=30.0,
    )
    rows = response.json().get("result", []) if response.status_code == 200 else []
    return str(rows[0].get("sys_id")) if rows else None


async def _query_update_xml(raw: httpx.AsyncClient, base: str, headers: dict[str, str], sys_id: str) -> int:
    response = await raw.get(
        f"{base}/api/now/table/sys_update_xml",
        headers=headers,
        params={
            "sysparm_query": f"target_name={sys_id}^ORtarget_name={TEST_NAME}",
            "sysparm_limit": "5",
        },
        timeout=30.0,
    )
    rows = response.json().get("result", []) if response.status_code == 200 else []
    return len(rows)


async def _run() -> int:
    _, meta, token, _ = acquire_token("")
    base = meta.url.rstrip("/")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as raw:
        await _delete_existing(raw, base, headers)

        # Q1: POST with explicit sys_id
        r1 = await raw.post(
            f"{base}/api/now/table/{TABLE}",
            headers=headers,
            json={
                "sys_id": TEST_SYS_ID,
                "name": TEST_NAME,
                "description": "Q1 first write",
            },
            timeout=30.0,
        )
        print(f"Q1 first POST -> http {r1.status_code}", flush=True)
        actual = await _query_sys_id(raw, base, headers)
        print(f"   after Q1: actual sys_id={actual!r}", flush=True)
        print(f"   sys_id-honored: {actual == TEST_SYS_ID}", flush=True)

        # Q3: did the platform write a sys_update_xml row for our change?
        await asyncio.sleep(1.0)
        xml_count = await _query_update_xml(raw, base, headers, TEST_SYS_ID)
        print(f"Q3 sys_update_xml rows referencing this change: {xml_count}", flush=True)

        # Q2: POST again with same sys_id
        r2 = await raw.post(
            f"{base}/api/now/table/{TABLE}",
            headers=headers,
            json={
                "sys_id": TEST_SYS_ID,
                "name": TEST_NAME,
                "description": "Q2 second write (same sys_id)",
            },
            timeout=30.0,
        )
        print(f"Q2 second POST -> http {r2.status_code}", flush=True)
        if r2.status_code in (200, 201):
            print(f"   body preview: {r2.text[:200]}", flush=True)
        else:
            print(f"   error body: {r2.text[:200]}", flush=True)

        # Q2 follow-up: how many rows exist now?
        all_rows = await raw.get(
            f"{base}/api/now/table/{TABLE}",
            headers=headers,
            params={"sysparm_query": f"name={TEST_NAME}", "sysparm_limit": "10"},
            timeout=30.0,
        )
        if all_rows.status_code == 200:
            rows = all_rows.json().get("result", [])
            print(f"   after Q2: rows matching name = {len(rows)}", flush=True)
            for row in rows:
                print(f"      sys_id={row.get('sys_id')!r} desc={row.get('description')!r}", flush=True)

        # PATCH probe: would PATCH with sys_id give us UPSERT semantics?
        r3 = await raw.patch(
            f"{base}/api/now/table/{TABLE}/{TEST_SYS_ID}",
            headers=headers,
            json={"description": "Q4 PATCH update"},
            timeout=30.0,
        )
        print(f"Q4 PATCH same sys_id -> http {r3.status_code}", flush=True)

        # Final cleanup
        await _delete_existing(raw, base, headers)

    return 0


def main() -> int:
    """Entry point."""
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
