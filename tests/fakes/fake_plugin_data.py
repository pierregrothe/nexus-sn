# tests/fakes/fake_plugin_data.py
# Canned SN Table API rows for v_plugin and sys_store_app.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Canned plugin rows used by PluginScanner tests.

Covers the cases the scanner must handle:
- An ITSM plugin present in both tables (dedup case).
- An ITOM plugin present only in v_plugin (legacy-only).
- A Store app present only in sys_store_app (third-party vendor).
- A custom scoped app whose scope starts with x_ (source=custom).
- An inactive plugin (state=inactive).
- A plugin not in the curated YAML (product_family=Uncategorized).
"""

__all__ = ["SYS_STORE_APP_ROWS", "V_PLUGIN_ROWS"]


V_PLUGIN_ROWS: list[dict[str, object]] = [
    {
        "sys_id": "abc111",
        "id": "com.snc.incident",
        "name": "Incident Management",
        "version": "1.2.3",
        "active": "true",
        "dependencies": "",
        "installed_on": "2024-01-15 12:00:00",
    },
    {
        "sys_id": "abc222",
        "id": "com.snc.discovery",
        "name": "Discovery",
        "version": "2.0.0",
        "active": "true",
        "dependencies": "com.snc.cmdb",
        "installed_on": "2024-02-20 09:30:00",
    },
    {
        "sys_id": "abc333",
        "id": "com.snc.legacy_only",
        "name": "Legacy Plugin",
        "version": "0.5.0",
        "active": "false",
        "dependencies": "",
        "installed_on": "",
    },
]


SYS_STORE_APP_ROWS: list[dict[str, object]] = [
    {
        "sys_id": "abc111",
        "scope": "com.snc.incident",
        "name": "Incident Management",
        "version": "1.2.3",
        "active": "true",
        "vendor": "ServiceNow",
        "dependencies": "",
        "sys_created_on": "2024-01-15 12:00:00",
    },
    {
        "sys_id": "store001",
        "scope": "com.acme.helper",
        "name": "Acme Helper",
        "version": "3.1.0",
        "active": "true",
        "vendor": "Acme Corp",
        "dependencies": "",
        "sys_created_on": "2024-03-01 10:00:00",
        "latest_version": "3.2.0",
    },
    {
        "sys_id": "custom001",
        "scope": "x_company_app",
        "name": "Internal Company App",
        "version": "0.1.0",
        "active": "true",
        "vendor": "",
        "dependencies": "",
        "sys_created_on": "2024-04-05 16:45:00",
    },
]
