# src/nexus/capture/xml_builder.py
# Converts captured ConfigRecords to ServiceNow update set XML payloads.
# Author: Pierre Grothe
# Date: 2026-05-09

"""UpdateSetXmlBuilder: generates SN sys_update_xml payload per ConfigRecord."""

import xml.etree.ElementTree as ET

from nexus.capture.models import ConfigRecord

__all__ = ["UpdateSetXmlBuilder"]


class UpdateSetXmlBuilder:
    """Converts a ConfigRecord to a ServiceNow update set XML payload string.

    The output format matches what ServiceNow sys_update_xml.payload expects:

        <record_update table="{table}" sys_id="{sys_id}">
          <{table} action="INSERT_OR_UPDATE">
            <field_name>value</field_name>
            <ref_field display_value="Label">sys_id</ref_field>
          </{table}>
        </record_update>
    """

    def build(self, record: ConfigRecord) -> str:
        """Generate the XML payload for one ConfigRecord.

        Args:
            record: The captured record to serialize.

        Returns:
            XML string suitable for the sys_update_xml.payload field.
        """
        outer = ET.Element(
            "record_update",
            attrib={"table": record.table, "sys_id": record.sys_id},
        )
        inner = ET.SubElement(
            outer,
            record.table,
            attrib={"action": "INSERT_OR_UPDATE"},
        )
        for field_name, field_value in record.fields.items():
            el = ET.SubElement(inner, field_name)
            if isinstance(field_value, dict):
                el.text = field_value["value"]
                el.set("display_value", field_value["display_value"])
            elif field_value is None:
                el.text = None
            elif isinstance(field_value, bool):
                el.text = "true" if field_value else "false"
            else:
                el.text = str(field_value)

        return ET.tostring(outer, encoding="unicode", xml_declaration=False)
