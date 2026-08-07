"""Tests for the N2G draw.io wrapper (PROJECT_SPEC.md section 8).

Per PROJECT_SPEC.md section 12: assert the draw.io XML is well-formed and that expected
nodes/links exist; pixel positions (layout output) are not asserted.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from nettopo.model.entities import DeviceRole
from nettopo.render.drawio import render_diagram
from nettopo.views.diagram import Diagram, DiagramLink, DiagramNode


def _diagram() -> Diagram:
    return Diagram(
        nodes=[
            DiagramNode(id="sw1", label="sw1", role=DeviceRole.SWITCH),
            DiagramNode(id="rtr1", label="rtr1", role=DeviceRole.ROUTER),
        ],
        links=[DiagramLink(source="sw1", target="rtr1", src_label="Gi1/0/1", trgt_label="Gi0/0/0")],
    )


def test_renders_well_formed_xml_with_expected_nodes_and_link(tmp_path: Path) -> None:
    output_path = tmp_path / "l2" / "l2_full.drawio"
    render_diagram(_diagram(), output_path)

    root = ET.fromstring(output_path.read_text(encoding="utf-8"))
    node_ids = {obj.get("id") for obj in root.findall(".//object") if obj.get("label")}
    assert {"sw1", "rtr1"} <= node_ids

    link = root.find(".//mxCell[@edge='1']")
    assert link is not None
    assert link.get("source") == "sw1"
    assert link.get("target") == "rtr1"


def test_node_style_reflects_its_role(tmp_path: Path) -> None:
    output_path = tmp_path / "l2.drawio"
    render_diagram(_diagram(), output_path)

    root = ET.fromstring(output_path.read_text(encoding="utf-8"))
    router_cell = root.find(".//object[@id='rtr1']/mxCell")
    assert router_cell is not None
    assert "mxgraph.cisco.routers.router" in router_cell.get("style", "")


def test_no_lucidify_leaves_separate_src_trgt_label_cells_in_place(tmp_path: Path) -> None:
    output_path = tmp_path / "l2.drawio"
    render_diagram(_diagram(), output_path, apply_lucidify=False)

    xml_text = output_path.read_text(encoding="utf-8")
    assert 'value="Gi1/0/1"' in xml_text
    assert 'value="Gi0/0/0"' in xml_text


def test_lucidify_applied_by_default_collapses_labels_onto_the_link_object(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "l2.drawio"
    render_diagram(_diagram(), output_path)

    root = ET.fromstring(output_path.read_text(encoding="utf-8"))
    link_object = root.find(".//object[@source='sw1'][@target='rtr1']")
    assert link_object is not None
    assert link_object.get("label") == "Gi1/0/1 — Gi0/0/0"


def test_an_empty_diagram_still_renders_valid_xml_without_crashing(tmp_path: Path) -> None:
    output_path = tmp_path / "empty.drawio"
    render_diagram(Diagram(), output_path)

    ET.fromstring(output_path.read_text(encoding="utf-8"))


def test_creates_parent_directories(tmp_path: Path) -> None:
    output_path = tmp_path / "nested" / "l2" / "l2_full.drawio"
    render_diagram(_diagram(), output_path)
    assert output_path.exists()


def test_highlighted_node_style_carries_the_highlight_color(tmp_path: Path) -> None:
    output_path = tmp_path / "stp.drawio"
    diagram = Diagram(
        nodes=[DiagramNode(id="root", label="root", role=DeviceRole.SWITCH, highlight=True)]
    )
    render_diagram(diagram, output_path)

    root = ET.fromstring(output_path.read_text(encoding="utf-8"))
    node_cell = root.find(".//object[@id='root']/mxCell")
    assert node_cell is not None
    assert "#FFD700" in node_cell.get("style", "")


def test_link_color_is_applied_to_the_edge_style(tmp_path: Path) -> None:
    output_path = tmp_path / "stp.drawio"
    diagram = Diagram(
        nodes=[
            DiagramNode(id="sw1", label="sw1", role=DeviceRole.SWITCH),
            DiagramNode(id="sw2", label="sw2", role=DeviceRole.SWITCH),
        ],
        links=[DiagramLink(source="sw1", target="sw2", color="#C62828")],
    )
    render_diagram(diagram, output_path, apply_lucidify=False)

    xml_text = output_path.read_text(encoding="utf-8")
    assert "#C62828" in xml_text
