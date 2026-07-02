# tests/fakes/spike_s0_fixtures.py
# Small JSON-shaped fixtures for the S0 closure-scale spike harness tests.
# Author: Pierre Grothe
# Date: 2026-07-02
"""Builders for tiny UseCaseInventory- and SchemaGraph-shaped dicts.

``scripts/spike_s0_closure_scale.py`` parses both file shapes with plain
``json.loads`` (see that module's docstring for why), so these builders
return plain dicts rather than the pydantic models -- tests write them to a
``tmp_path`` file and hand the path to the harness's ``load_*`` functions.
The shapes mirror the real
``artifacts/replatform-proof/inventory-*-v2.json`` and schema-archive JSON,
just with a handful of rows instead of 30K.
"""

from __future__ import annotations

from collections.abc import Mapping

__all__ = ["make_fixture_inventory", "make_fixture_schema_archive"]


def make_fixture_inventory() -> Mapping[str, object]:
    """Build a tiny UseCaseInventory-shaped dict with a scoped and a global use case.

    Returns:
        A dict matching the real inventory JSON's top-level shape:
        profile/captured_at/coverage/use_cases/skipped_tables.
    """
    return {
        "profile": "fixture",
        "captured_at": "2026-07-02T00:00:00Z",
        "coverage": ["ai_automation"],
        "use_cases": [
            {
                "key": "x_acme_app",
                "name": "Acme App",
                "domain": "Acme",
                "workflows": [
                    {
                        "key": "x_acme_app|sys_script|foo",
                        "name": "Foo",
                        "type": "sys_script",
                        "scope": "x_acme_app",
                    },
                    {
                        "key": "x_acme_app|sys_hub_flow|bar",
                        "name": "Bar",
                        "type": "sys_hub_flow",
                        "scope": "x_acme_app",
                    },
                ],
                "evidence": ["x_acme_app"],
            },
            {
                "key": "global|sys_script_include|baz",
                "name": "Global App",
                "domain": "Global App",
                "workflows": [
                    {
                        "key": "global|sys_script|baz",
                        "name": "Baz",
                        "type": "sys_script",
                        "scope": "global",
                    }
                ],
                "evidence": ["global"],
            },
        ],
        "skipped_tables": [],
    }


def make_fixture_schema_archive() -> Mapping[str, object]:
    """Build a tiny SchemaGraph-shaped dict with expansion and stop-list edges.

    ``sys_script -> sys_script`` (self-reference) and
    ``sys_script -> sys_rest_message`` are ordinary expansion candidates.
    ``sys_script -> sys_user`` and ``sys_hub_flow -> sys_user_group`` are
    the ones a seed stop-list of ``{"sys_user", "sys_user_group"}`` dampens.

    Returns:
        A dict matching the real schema-archive JSON's top-level shape.
    """
    return {
        "instance_id": "fixture",
        "area_key": "s0-platform-artifacts",
        "discovered_at": "2026-07-02T00:00:00Z",
        "scope_keys": [],
        "tables": [],
        "reference_edges": [
            {
                "from_table": "sys_script",
                "field": "sys_overrides",
                "to_table": "sys_script",
                "cross_scope": False,
                "is_list": False,
            },
            {
                "from_table": "sys_script",
                "field": "rest_service",
                "to_table": "sys_rest_message",
                "cross_scope": False,
                "is_list": False,
            },
            {
                "from_table": "sys_script",
                "field": "assigned_to",
                "to_table": "sys_user",
                "cross_scope": False,
                "is_list": False,
            },
            {
                "from_table": "sys_hub_flow",
                "field": "run_as_group",
                "to_table": "sys_user_group",
                "cross_scope": False,
                "is_list": False,
            },
        ],
        "inheritance_edges": [],
        "relationship_edges": [],
    }
