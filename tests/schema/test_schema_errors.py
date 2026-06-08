# tests/schema/test_schema_errors.py
# Tests for the schema layer error hierarchy.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Verify schema error types carry their context attributes."""

from pathlib import Path

from nexus.schema.errors import (
    AreaNotFoundError,
    SchemaArchiveError,
    SchemaError,
    ScopeNotFoundError,
)


def test_area_not_found_error_carries_area_key() -> None:
    err = AreaNotFoundError("doc-designer")
    assert isinstance(err, SchemaError)
    assert err.area_key == "doc-designer"
    assert "doc-designer" in str(err)


def test_scope_not_found_error_carries_context() -> None:
    err = ScopeNotFoundError(["sn_bcm", "sn_bcp"], "alectri")
    assert isinstance(err, SchemaError)
    assert err.scopes == ["sn_bcm", "sn_bcp"]
    assert err.instance_id == "alectri"
    assert "alectri" in str(err)


def test_schema_archive_error_carries_path() -> None:
    err = SchemaArchiveError(Path("/tmp/x.json"))
    assert isinstance(err, SchemaError)
    assert err.path == Path("/tmp/x.json")
    assert "x.json" in str(err)
