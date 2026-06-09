# tests/schema/test_catalog_models.py
# Tests for mindmap catalog Pydantic models.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Verify catalog models are frozen and reject extras."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from nexus.schema.catalog import Domain, MindmapCatalog, Section, TableDescription


def _catalog() -> MindmapCatalog:
    return MindmapCatalog(
        instance_id="alectri",
        area_key="bcm",
        generated_at=datetime(2026, 6, 8, tzinfo=UTC),
        display="Business Continuity Management",
        sections=(
            Section(
                name="Planning",
                domains=(
                    Domain(
                        name="Plan Management",
                        tables=(
                            TableDescription(
                                table="sn_bcp_plan",
                                label="Plan",
                                description="Stores BC plans.",
                                source="ai",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


def test_mindmap_catalog_round_trips_through_json() -> None:
    catalog = _catalog()
    assert MindmapCatalog.model_validate_json(catalog.model_dump_json()) == catalog


def test_table_description_is_frozen() -> None:
    desc = TableDescription(table="t", label="T", description="d", source="ai")
    with pytest.raises(ValidationError):
        setattr(desc, "description", "other")


def test_domain_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        Domain(**{"name": "X", "tables": (), "bogus": 1})
