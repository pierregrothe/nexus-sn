# scripts/dump_sn_api_catalog.py
# Dump ServiceNow internal Scripted REST API catalog as Markdown.
# Author: Pierre Grothe
# Date: 2026-05-13

"""Reverse-engineer the full Scripted REST surface of an SN instance.

Queries ``sys_ws_definition`` and ``sys_ws_operation``, joins them in
memory, groups by namespace prefix, and writes a Markdown reference
to ``docs/sn-internal-api-catalog.md``.

Usage:
    python scripts/dump_sn_api_catalog.py [--profile alectri]

Requires an active OAuth token for the given profile. Run
``nexus instance connect <profile>`` first if the token has expired.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import httpx
import keyring


def _load_meta(profile: str) -> dict[str, str]:
    """Read the instance's stored meta.json."""
    home_meta = Path.home() / ".nexus" / "instances" / profile / "meta.json"
    raw: dict[str, str] = json.loads(home_meta.read_text(encoding="utf-8"))
    return raw


async def _fetch_page(
    client: httpx.AsyncClient, table: str, query: str, fields: str, offset: int, limit: int
) -> list[dict[str, object]]:
    """Fetch one page of rows from ``table``."""
    resp = await client.get(
        f"/api/now/table/{table}",
        params={
            "sysparm_query": query,
            "sysparm_fields": fields,
            "sysparm_limit": limit,
            "sysparm_offset": offset,
        },
    )
    resp.raise_for_status()
    result = resp.json().get("result", [])
    return result if isinstance(result, list) else []


async def _fetch_all(
    client: httpx.AsyncClient, table: str, query: str, fields: str
) -> list[dict[str, object]]:
    """Paginate ``table`` until exhausted."""
    rows: list[dict[str, object]] = []
    offset = 0
    while True:
        batch = await _fetch_page(client, table, query, fields, offset, 500)
        rows.extend(batch)
        if len(batch) < 500:
            break
        offset += 500
    return rows


def _build_markdown(defs: list[dict[str, object]], ops: list[dict[str, object]]) -> str:
    """Group defs+ops by namespace prefix and render Markdown."""
    ops_by_def: dict[str, list[dict[str, object]]] = defaultdict(list)
    for op in ops:
        link = op.get("web_service_definition", {})
        if isinstance(link, dict):
            did = str(link.get("value", ""))
            if did:
                ops_by_def[did].append(op)

    services: list[dict[str, object]] = []
    for d in defs:
        ns = str(d.get("namespace", ""))
        if not ns or ns in ("now", "now/ide"):
            continue
        sid = str(d.get("sys_id", ""))
        svc_ops = ops_by_def.get(sid, [])
        if not svc_ops:
            continue
        services.append(
            {
                "namespace": ns,
                "name": str(d.get("name", "")),
                "base_uri": str(d.get("base_uri", "")),
                "desc": str(d.get("short_description", "") or ""),
                "ops": svc_ops,
            }
        )

    cats: dict[str, list[dict[str, object]]] = defaultdict(list)
    for svc in services:
        ns_str = str(svc["namespace"])
        parts = ns_str.split("_")
        cat = f"sn_{parts[1]}" if parts[0] == "sn" and len(parts) >= 2 else ns_str
        cats[cat].append(svc)

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    out: list[str] = [
        "# ServiceNow Internal Scripted REST API Catalog",
        "",
        f"Reverse-engineered from a Zurich PDI on {today}. "
        "Discovered via `sys_ws_definition` + `sys_ws_operation` tables -- both "
        "readable with regular admin auth, no special role needed.",
        "",
        f"**Totals:** {len(services)} services, "
        f"{sum(len(s['ops']) for s in services)} operations, "
        f"{len(cats)} categories.",
        "",
        "These endpoints are NOT documented in SN's public REST API reference. "
        "They power SN's own UI Builder apps (Application Manager, Now Assist "
        "panels, Admin Center, etc.) and side-step table-level ACLs that block "
        "direct REST table access.",
        "",
        "Use them at your own risk -- they can change between SN releases.",
        "",
        "## Discovery method",
        "",
        "```bash",
        "# 1. Find all active scripted REST API definitions",
        "GET /api/now/table/sys_ws_definition?sysparm_query=active=true",
        "",
        "# 2. Find all operations linked to one definition",
        "GET /api/now/table/sys_ws_operation?sysparm_query=web_service_definition={sys_id}",
        "",
        "# 3. The base_uri + relative_path forms the callable URL",
        "```",
        "",
        "## Catalog (grouped by namespace prefix)",
        "",
    ]
    for cat in sorted(cats):
        svcs = cats[cat]
        op_total = sum(len(s["ops"]) for s in svcs)
        out.append(f"### `{cat}` ({len(svcs)} services, {op_total} ops)")
        out.append("")
        for svc in sorted(svcs, key=lambda s: str(s["base_uri"])):
            out.append(f"**{svc['name']}** -- `{svc['base_uri']}`")
            if svc["desc"]:
                out.append(f"> {svc['desc']}")
            svc_ops = svc["ops"]
            assert isinstance(svc_ops, list)
            for op in sorted(
                svc_ops,
                key=lambda o: (str(o.get("http_method", "")), str(o.get("relative_path", ""))),
            ):
                method = str(op.get("http_method", ""))
                path = str(op.get("relative_path", ""))
                name = str(op.get("name", ""))
                out.append(f"- `{method} {svc['base_uri']}{path}` -- {name}")
            out.append("")
    return "\n".join(out) + "\n"


async def _main(profile: str) -> int:
    """Dump the SN scripted REST catalog for the given profile."""
    meta = _load_meta(profile)
    url = meta["url"]
    token = keyring.get_password(f"nexus-sn-{profile}", "access-token")
    if not token:
        print(f"No access token for profile {profile!r}.", file=sys.stderr)
        print(f"Run: nexus instance connect {profile}", file=sys.stderr)
        return 1
    async with httpx.AsyncClient(
        base_url=url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=60.0,
    ) as client:
        defs = await _fetch_all(
            client,
            "sys_ws_definition",
            "active=true^ORDERBYnamespace",
            "sys_id,name,namespace,base_uri,short_description",
        )
        ops = await _fetch_all(
            client,
            "sys_ws_operation",
            "active=true",
            "web_service_definition,relative_path,http_method,name",
        )
    md = _build_markdown(defs, ops)
    out_path = Path("docs/sn-internal-api-catalog.md")
    out_path.write_text(md, encoding="utf-8")
    print(f"Wrote {out_path} ({len(md):,} chars).")
    return 0


def main() -> int:
    """CLI entry point -- parse ``--profile`` and run the dumper."""
    profile = sys.argv[2] if len(sys.argv) >= 3 and sys.argv[1] == "--profile" else "alectri"
    return asyncio.run(_main(profile))


if __name__ == "__main__":
    raise SystemExit(main())
