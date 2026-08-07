"""Tests for the Lucidchart-friendliness post-process (PROJECT_SPEC.md section 8).

Fixture XML mirrors exactly what N2G's `drawio_diagram.add_link(src_label=...,
trgt_label=...)` emits: two sibling `<mxCell>` label vertices parented to the link's
`<object>` id, with relative geometry (`x="-0.5"` near the source, `x="0.5"` near the
target), and a doubled `;;` in their style from N2G's XML template.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from nettopo.render.lucidify import lucidify_xml

_N2G_STYLE_LINK_XML = """<mxfile type="device" compressed="false">
    <diagram id="diagram_1" name="diagram_1">
      <mxGraphModel dx="1360" dy="864" grid="1">
        <root>
          <mxCell id="0" />
          <mxCell id="1" parent="0" />
        <object id="sw1" label="sw1">
      <mxCell style="shape=mxgraph.cisco.switches.workgroup_switch;" vertex="1" parent="1">
          <mxGeometry x="200" y="150" width="120" height="60" as="geometry" />
      </mxCell>
    </object><object id="sw2" label="sw2">
      <mxCell style="shape=mxgraph.cisco.switches.workgroup_switch;" vertex="1" parent="1">
          <mxGeometry x="200" y="150" width="120" height="60" as="geometry" />
      </mxCell>
    </object><mxCell id="link1-src" value="Gi1/0/1" style="labelBackgroundColor=#ffffff;;" \
vertex="1" connectable="0" parent="link1">
      <mxGeometry x="-0.5" relative="1" as="geometry">
        <mxPoint as="offset" />
      </mxGeometry>
    </mxCell><mxCell id="link1-trgt" value="Gi1/0/24" style="labelBackgroundColor=#ffffff;;" \
vertex="1" connectable="0" parent="link1">
      <mxGeometry x="0.5" relative="-1" as="geometry">
        <mxPoint as="offset" />
      </mxGeometry>
    </mxCell><object id="link1" label="" src_label="Gi1/0/1" trgt_label="Gi1/0/24" \
source="sw1" target="sw2">
      <mxCell style="endArrow=none;" edge="1" parent="1" source="sw1" target="sw2">
          <mxGeometry relative="1" as="geometry" />
      </mxCell>
    </object></root>
      </mxGraphModel>
    </diagram></mxfile>"""


def test_result_is_well_formed_xml() -> None:
    ET.fromstring(lucidify_xml(_N2G_STYLE_LINK_XML))


def test_src_and_trgt_labels_are_collapsed_into_the_links_own_label_attribute() -> None:
    root = ET.fromstring(lucidify_xml(_N2G_STYLE_LINK_XML))
    link_object = root.find(".//object[@id='link1']")
    assert link_object is not None
    assert link_object.get("label") == "Gi1/0/1 — Gi1/0/24"


def test_the_now_redundant_label_child_cells_are_removed() -> None:
    root = ET.fromstring(lucidify_xml(_N2G_STYLE_LINK_XML))
    assert root.find(".//mxCell[@id='link1-src']") is None
    assert root.find(".//mxCell[@id='link1-trgt']") is None


def test_doubled_semicolons_in_style_strings_are_cleaned() -> None:
    root = ET.fromstring(lucidify_xml(_N2G_STYLE_LINK_XML))
    for element in root.iter():
        style = element.get("style")
        if style is not None:
            assert ";;" not in style


def test_nodes_and_the_link_object_itself_survive_unchanged_otherwise() -> None:
    root = ET.fromstring(lucidify_xml(_N2G_STYLE_LINK_XML))
    assert root.find(".//object[@id='sw1']") is not None
    assert root.find(".//object[@id='sw2']") is not None
    link_cell = root.find(".//object[@id='link1']/mxCell")
    assert link_cell is not None
    assert link_cell.get("source") == "sw1"
    assert link_cell.get("target") == "sw2"
