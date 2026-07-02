# tests/capture/test_xml_builder.py
# Tests for UpdateSetXmlBuilder.
# Author: Pierre Grothe
# Date: 2026-05-09

"""Tests for the UpdateSetXmlBuilder component."""

import xml.etree.ElementTree as ET
from datetime import UTC, datetime

from nexus.capture.models import ConfigRecord, SnRecord, SnRefField
from nexus.capture.xml_builder import UpdateSetXmlBuilder

_NOW = datetime(2026, 5, 9, tzinfo=UTC)


def _record(fields: SnRecord) -> ConfigRecord:
    return ConfigRecord(
        sys_id="abc123",
        table="ai_skill",
        scope_sys_id="scope001",
        scope_name="x_app",
        captured_at=_NOW,
        fields=fields,
        parent_sys_id=None,
    )


def test_xml_builder_output_parses_as_valid_xml() -> None:
    builder = UpdateSetXmlBuilder()
    xml_str = builder.build(_record({"name": "My Skill"}))
    root = ET.fromstring(xml_str)
    assert root is not None


def test_xml_builder_outer_element_has_correct_table_and_sys_id() -> None:
    builder = UpdateSetXmlBuilder()
    xml_str = builder.build(_record({"name": "My Skill"}))
    root = ET.fromstring(xml_str)
    assert root.tag == "record_update"
    assert root.attrib["table"] == "ai_skill"
    assert root.attrib["sys_id"] == "abc123"


def test_xml_builder_inner_element_named_after_table_with_action() -> None:
    builder = UpdateSetXmlBuilder()
    xml_str = builder.build(_record({"name": "My Skill"}))
    root = ET.fromstring(xml_str)
    inner = root.find("ai_skill")
    assert inner is not None
    assert inner.attrib["action"] == "INSERT_OR_UPDATE"


def test_xml_builder_plain_string_field_produces_text_element() -> None:
    builder = UpdateSetXmlBuilder()
    xml_str = builder.build(_record({"name": "My Skill"}))
    root = ET.fromstring(xml_str)
    name_el = root.find("ai_skill/name")
    assert name_el is not None
    assert name_el.text == "My Skill"


def test_xml_builder_ref_field_includes_display_value_attribute() -> None:
    ref: SnRefField = {"value": "global", "display_value": "Global"}
    builder = UpdateSetXmlBuilder()
    xml_str = builder.build(_record({"sys_scope": ref}))
    root = ET.fromstring(xml_str)
    scope_el = root.find("ai_skill/sys_scope")
    assert scope_el is not None
    assert scope_el.text == "global"
    assert scope_el.attrib["display_value"] == "Global"


def test_xml_builder_none_field_produces_empty_element() -> None:
    builder = UpdateSetXmlBuilder()
    xml_str = builder.build(_record({"description": None}))
    root = ET.fromstring(xml_str)
    el = root.find("ai_skill/description")
    assert el is not None
    assert el.text is None


def test_xml_builder_true_bool_field_serializes_lowercase_true() -> None:
    builder = UpdateSetXmlBuilder()
    xml_str = builder.build(_record({"active": True}))
    root = ET.fromstring(xml_str)
    el = root.find("ai_skill/active")
    assert el is not None
    assert el.text == "true"


def test_xml_builder_false_bool_field_serializes_lowercase_false() -> None:
    builder = UpdateSetXmlBuilder()
    xml_str = builder.build(_record({"active": False}))
    root = ET.fromstring(xml_str)
    el = root.find("ai_skill/active")
    assert el is not None
    assert el.text == "false"


def test_xml_builder_int_field_serializes_as_str() -> None:
    builder = UpdateSetXmlBuilder()
    xml_str = builder.build(_record({"order": 100}))
    root = ET.fromstring(xml_str)
    el = root.find("ai_skill/order")
    assert el is not None
    assert el.text == "100"


def test_xml_builder_float_field_serializes_as_str() -> None:
    builder = UpdateSetXmlBuilder()
    xml_str = builder.build(_record({"weight": 2.5}))
    root = ET.fromstring(xml_str)
    el = root.find("ai_skill/weight")
    assert el is not None
    assert el.text == "2.5"
