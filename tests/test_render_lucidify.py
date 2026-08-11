"""Tests for the draw.io link-label post-process (PROJECT_SPEC.md section 8).

Fixture XML mirrors exactly what N2G's `drawio_diagram.add_link(src_label=...,
trgt_label=...)` emits: two `<mxCell>` label vertices parented to the link's `<object>` id,
positioned along it by relative geometry -- including N2G's `relative="-1"` on the
target-end label, the defect this module normalizes -- and a doubled `;;` in their style
from N2G's XML template.
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
          <mxGeometry x="100" y="400" width="120" height="60" as="geometry" />
      </mxCell>
    </object><object id="sw2" label="sw2">
      <mxCell style="shape=mxgraph.cisco.switches.workgroup_switch;" vertex="1" parent="1">
          <mxGeometry x="700" y="400" width="120" height="60" as="geometry" />
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


def _label_cell(xml_text: str, cell_id: str) -> ET.Element:
    cell = ET.fromstring(lucidify_xml(xml_text)).find(f".//mxCell[@id='{cell_id}']")
    assert cell is not None
    return cell


def test_result_is_well_formed_xml() -> None:
    ET.fromstring(lucidify_xml(_N2G_STYLE_LINK_XML))


def test_n2gs_nonstandard_relative_flag_is_normalized_on_the_target_end() -> None:
    geometry = _label_cell(_N2G_STYLE_LINK_XML, "link1-trgt").find("./mxGeometry")
    assert geometry is not None
    assert geometry.get("relative") == "1"


def test_the_source_end_label_keeps_the_relative_flag_it_already_had() -> None:
    geometry = _label_cell(_N2G_STYLE_LINK_XML, "link1-src").find("./mxGeometry")
    assert geometry is not None
    assert geometry.get("relative") == "1"


def test_end_labels_stay_parented_to_their_link() -> None:
    # A vertex parented to the canvas is a node: draw.io's Arrange layouts would lay it out
    # as one, tearing the labels away from the links they describe. Parented to the edge it
    # is that edge's label, and travels with it.
    for cell_id in ("link1-src", "link1-trgt"):
        assert _label_cell(_N2G_STYLE_LINK_XML, cell_id).get("parent") == "link1"


def test_each_end_keeps_its_own_label_at_its_own_end_of_the_link() -> None:
    positions = {
        cell_id: _label_cell(_N2G_STYLE_LINK_XML, cell_id).find("./mxGeometry")
        for cell_id in ("link1-src", "link1-trgt")
    }

    assert positions["link1-src"] is not None
    assert positions["link1-trgt"] is not None
    assert float(positions["link1-src"].get("x", "")) < 0
    assert float(positions["link1-trgt"].get("x", "")) > 0


def test_the_links_own_label_attribute_is_left_alone() -> None:
    # The two ends are never merged into one centered string: in the STP view each carries
    # its own role/state, and joined up they say nothing about which switch is which.
    root = ET.fromstring(lucidify_xml(_N2G_STYLE_LINK_XML))
    link_object = root.find(".//object[@id='link1']")
    assert link_object is not None
    assert link_object.get("label") == ""


def test_the_canvas_root_cells_are_not_mistaken_for_link_labels() -> None:
    root = ET.fromstring(lucidify_xml(_N2G_STYLE_LINK_XML))
    for cell_id in ("0", "1"):
        cell = root.find(f".//mxCell[@id='{cell_id}']")
        assert cell is not None
        assert cell.find("./mxGeometry") is None


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
