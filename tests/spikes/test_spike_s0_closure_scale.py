# tests/spikes/test_spike_s0_closure_scale.py
# Tests for the S0 closure-scale spike harness's pure functions.
# Author: Pierre Grothe
# Date: 2026-07-02
"""Unit tests for scripts/spike_s0_closure_scale.py.

Exercises the harness against a tiny fixture inventory + fixture schema
archive (``tests/fakes/spike_s0_fixtures.py``), never the real 30K-artifact
dataset -- those files are untracked and regenerable, so CI must not depend
on them (see the story's Testing Approach). The full-scale timed run is a
documented, human-run command instead (s0-spike-results.md).

``scripts/`` is a real package here (``pythonpath = ["src", "scripts"]`` in
pyproject.toml, plus ``scripts/__init__.py``), so this imports the harness
the same way ``tests/test_check_file_sizes.py`` already imports
``scripts.check_file_sizes`` -- no ``importlib.util.spec_from_file_location``
needed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.spike_s0_closure_scale import (
    ClosureWalkResult,
    WorkflowEntry,
    _assert_no_network_client,
    _find_latest_archive,
    count_lane_units,
    load_inventory_workflows,
    load_schema_edges,
    load_stop_list,
    walk_closure,
)
from tests.fakes.spike_s0_fixtures import make_fixture_inventory, make_fixture_schema_archive

__all__: list[str] = []

# The fixture inventory's 3 workflows, as WorkflowEntry tuples -- used directly
# by the walk_closure/count_lane_units tests so they don't have to round-trip
# through a JSON file just to get test data.
_FIXTURE_WORKFLOWS = (
    WorkflowEntry(use_case_key="x_acme_app", table="sys_script", scope="x_acme_app"),
    WorkflowEntry(use_case_key="x_acme_app", table="sys_hub_flow", scope="x_acme_app"),
    WorkflowEntry(use_case_key="global|sys_script_include|baz", table="sys_script", scope="global"),
)
# The fixture schema archive's edges, as an EdgeMap -- mirrors load_schema_edges'
# output shape for make_fixture_schema_archive().
_FIXTURE_EDGES = {
    "sys_script": (
        ("sys_overrides", "sys_script"),
        ("rest_service", "sys_rest_message"),
        ("assigned_to", "sys_user"),
    ),
    "sys_hub_flow": (("run_as_group", "sys_user_group"),),
}


def _write_json(path: Path, payload: object) -> Path:
    """Write ``payload`` as JSON to ``path`` and return the path."""
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# -- load_inventory_workflows -------------------------------------------------


def test_load_inventory_workflows_parses_use_cases_and_workflows(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "inventory.json", make_fixture_inventory())
    assert load_inventory_workflows(path) == _FIXTURE_WORKFLOWS


def test_load_inventory_workflows_empty_use_cases_returns_empty_tuple(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "inventory.json", {"use_cases": []})
    assert load_inventory_workflows(path) == ()


# -- load_schema_edges ---------------------------------------------------------


def test_load_schema_edges_parses_reference_edges_into_table_map(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "archive.json", make_fixture_schema_archive())
    assert load_schema_edges(path) == _FIXTURE_EDGES


def test_load_schema_edges_missing_reference_edges_key_returns_empty_dict(
    tmp_path: Path,
) -> None:
    path = _write_json(tmp_path / "archive.json", {})
    assert load_schema_edges(path) == {}


# -- load_stop_list -------------------------------------------------------------


def test_load_stop_list_parses_flat_list_skipping_comments_and_blanks(tmp_path: Path) -> None:
    path = tmp_path / "stop-list.yaml"
    path.write_text(
        "# header comment\n\n- sys_user\n- sys_user_group\n\n# trailing comment\n",
        encoding="utf-8",
    )
    assert load_stop_list(path) == frozenset({"sys_user", "sys_user_group"})


def test_load_stop_list_comment_only_file_returns_empty_frozenset(tmp_path: Path) -> None:
    path = tmp_path / "stop-list.yaml"
    path.write_text("# nothing here yet\n", encoding="utf-8")
    assert load_stop_list(path) == frozenset()


# -- walk_closure ---------------------------------------------------------------


def test_walk_closure_empty_stop_list_all_candidates_are_expansion() -> None:
    result = walk_closure(_FIXTURE_WORKFLOWS, _FIXTURE_EDGES, frozenset())
    assert result.raw_expansion == 7
    assert result.raw_data_prerequisite == 0
    assert len(result.dedup_expansion) == 7
    assert len(result.dedup_data_prerequisite) == 0
    assert result.raw_total == 7
    assert result.dedup_total == 7
    assert result.stop_tables_hit == frozenset()


def test_walk_closure_seed_stop_list_dampens_matching_edges() -> None:
    stop_list = frozenset({"sys_user", "sys_user_group"})
    result = walk_closure(_FIXTURE_WORKFLOWS, _FIXTURE_EDGES, stop_list)
    assert result.raw_expansion == 4
    assert result.raw_data_prerequisite == 3
    # Raw total is a property of the artifact/edge pairs, not the stop-list:
    # dampening only moves candidates between buckets, it never drops them.
    assert result.raw_total == 7
    assert len(result.dedup_expansion) == 4
    assert len(result.dedup_data_prerequisite) == 3
    assert result.dedup_total == 7
    assert result.stop_tables_hit == stop_list


def test_walk_closure_dedup_collapses_duplicate_use_case_table_field_target() -> None:
    workflows = (
        WorkflowEntry(use_case_key="uc1", table="sys_script", scope="x_a"),
        WorkflowEntry(use_case_key="uc1", table="sys_script", scope="x_a"),
    )
    edges = {"sys_script": (("f", "t"),)}
    result = walk_closure(workflows, edges, frozenset())
    assert result.raw_expansion == 2
    assert len(result.dedup_expansion) == 1


def test_walk_closure_table_with_no_edges_contributes_nothing() -> None:
    workflows = (WorkflowEntry(use_case_key="uc1", table="sys_script_include", scope="x_a"),)
    result = walk_closure(workflows, edges_by_table={}, stop_list=frozenset())
    assert result.raw_total == 0
    assert result.dedup_total == 0


def test_closure_walk_result_stop_tables_hit_dedupes_across_use_cases() -> None:
    result = ClosureWalkResult(
        raw_expansion=0,
        raw_data_prerequisite=2,
        dedup_expansion=frozenset(),
        dedup_data_prerequisite=frozenset(
            {
                ("uc1", "sys_script", "assigned_to", "sys_user"),
                ("uc2", "sys_script", "assigned_to", "sys_user"),
            }
        ),
    )
    assert result.stop_tables_hit == frozenset({"sys_user"})


# -- count_lane_units -------------------------------------------------------------


def test_count_lane_units_counts_scoped_apps_global_use_cases_and_data_batches() -> None:
    result = count_lane_units(_FIXTURE_WORKFLOWS, frozenset({"sys_user", "sys_user_group"}))
    assert result.scoped_apps == 1
    assert result.global_use_cases == 1
    assert result.data_batches == 2
    assert result.total == 4


def test_count_lane_units_dedupes_multiple_artifacts_in_same_scoped_app() -> None:
    workflows = (
        WorkflowEntry(use_case_key="uc1", table="sys_script", scope="x_acme_app"),
        WorkflowEntry(use_case_key="uc1", table="sys_hub_flow", scope="x_acme_app"),
        WorkflowEntry(use_case_key="uc2", table="sys_script", scope="x_other_app"),
    )
    result = count_lane_units(workflows, frozenset())
    assert result.scoped_apps == 2
    assert result.global_use_cases == 0
    assert result.data_batches == 0


def test_count_lane_units_u_prefixed_scope_counts_as_scoped_app() -> None:
    workflows = (WorkflowEntry(use_case_key="uc1", table="sys_script", scope="u_myapp"),)
    result = count_lane_units(workflows, frozenset())
    assert result.scoped_apps == 1


# -- _find_latest_archive -------------------------------------------------------


def test_find_latest_archive_returns_none_when_directory_absent(tmp_path: Path) -> None:
    assert _find_latest_archive(tmp_path, "alectri") is None


def test_find_latest_archive_picks_lexicographically_last_file(tmp_path: Path) -> None:
    instance_dir = tmp_path / "alectri"
    instance_dir.mkdir()
    older = instance_dir / "s0-platform-artifacts-20260701-000000.json"
    newer = instance_dir / "s0-platform-artifacts-20260702-130037.json"
    older.write_text("{}", encoding="utf-8")
    newer.write_text("{}", encoding="utf-8")
    assert _find_latest_archive(tmp_path, "alectri") == newer


# -- _assert_no_network_client ---------------------------------------------------


def test_assert_no_network_client_passes_when_modules_clean() -> None:
    result = _assert_no_network_client({"json": object(), "pathlib": object()})
    assert result.startswith("AC5 guard: PASS")


def test_assert_no_network_client_raises_when_httpx_present() -> None:
    with pytest.raises(AssertionError):
        _assert_no_network_client({"httpx": object()})


def test_assert_no_network_client_raises_when_connectors_module_present() -> None:
    with pytest.raises(AssertionError):
        _assert_no_network_client({"nexus.connectors.servicenow.client": object()})


def test_assert_no_network_client_raises_when_api_module_present() -> None:
    with pytest.raises(AssertionError):
        _assert_no_network_client({"nexus.api.kroki_client": object()})
