"""Tests for the N2G draw.io wrapper (PROJECT_SPEC.md section 8).

Per PROJECT_SPEC.md section 12: assert the draw.io XML is well-formed and that expected
nodes/links exist; pixel positions (layout output) are not asserted. The node-spacing
tests below stay on the right side of that line -- they assert how far apart the closest
two nodes end up, never where any node is.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from itertools import combinations
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


def test_no_lucidify_leaves_n2gs_raw_label_cells_in_place(tmp_path: Path) -> None:
    output_path = tmp_path / "l2.drawio"
    render_diagram(_diagram(), output_path, apply_lucidify=False)

    xml_text = output_path.read_text(encoding="utf-8")
    assert 'value="Gi1/0/1"' in xml_text
    assert 'value="Gi0/0/0"' in xml_text
    assert 'relative="-1"' in xml_text  # the defect lucidify normalizes


def test_lucidify_applied_by_default_keeps_end_labels_attached_to_their_link(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "l2.drawio"
    render_diagram(_diagram(), output_path)

    root = ET.fromstring(output_path.read_text(encoding="utf-8"))
    link_object = root.find(".//object[@source='sw1'][@target='rtr1']")
    assert link_object is not None
    link_id = link_object.get("id")

    labels = [cell for cell in root.findall(".//root/mxCell") if cell.get("value")]
    assert {cell.get("value") for cell in labels} == {"Gi1/0/1", "Gi0/0/0"}

    for cell in labels:
        assert cell.get("parent") == link_id
        geometry = cell.find("./mxGeometry")
        assert geometry is not None
        assert geometry.get("relative") == "1"

    # The two ends are never merged into one label on the link itself.
    assert link_object.get("label") == ""

    link_object = root.find(".//object[@source='sw1'][@target='rtr1']")
    assert link_object is not None
    assert link_object.get("label") == ""


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


def _colored_link_diagram() -> Diagram:
    return Diagram(
        nodes=[
            DiagramNode(id="sw1", label="sw1", role=DeviceRole.SWITCH),
            DiagramNode(id="sw2", label="sw2", role=DeviceRole.SWITCH),
        ],
        links=[DiagramLink(source="sw1", target="sw2", color="#C62828")],
    )


def _edge_style(output_path: Path) -> str:
    root = ET.fromstring(output_path.read_text(encoding="utf-8"))
    edge_cell = root.find(".//mxCell[@edge='1']")
    assert edge_cell is not None
    return edge_cell.get("style", "")


def test_link_color_is_applied_to_the_edge_style(tmp_path: Path) -> None:
    output_path = tmp_path / "stp.drawio"
    render_diagram(_colored_link_diagram(), output_path, apply_lucidify=False)

    assert "strokeColor=#C62828;" in _edge_style(output_path)


def test_a_colored_link_is_still_drawn_without_an_arrowhead(tmp_path: Path) -> None:
    # N2G substitutes its default style for whatever it is given instead of merging them,
    # so a link that carries a color used to lose the default's `endArrow=none` and come
    # out with draw.io's arrowhead -- pointing whichever way the view happened to order the
    # edge's ends, which in the STP view is alphabetical and therefore meaningless.
    output_path = tmp_path / "stp.drawio"
    render_diagram(_colored_link_diagram(), output_path, apply_lucidify=False)

    style = _edge_style(output_path)
    assert "endArrow=none;" in style
    assert "strokeColor=#C62828;" in style


def test_an_uncolored_link_is_drawn_without_an_arrowhead(tmp_path: Path) -> None:
    output_path = tmp_path / "l2.drawio"
    render_diagram(_diagram(), output_path, apply_lucidify=False)

    assert "endArrow=none;" in _edge_style(output_path)


def test_a_link_tooltip_is_rendered_as_a_drawio_tooltip_attribute(tmp_path: Path) -> None:
    diagram = _diagram()
    diagram.links[0].tooltip = "Members:<br>Gi1/0/1 — Gi2/0/1"
    output_path = tmp_path / "l2_port-channels.drawio"
    render_diagram(diagram, output_path)

    root = ET.fromstring(output_path.read_text(encoding="utf-8"))
    link_object = next(
        obj for obj in root.findall(".//object") if obj.find("./mxCell[@edge='1']") is not None
    )
    assert link_object.get("tooltip") == "Members:<br>Gi1/0/1 — Gi2/0/1"


def test_a_link_without_a_tooltip_gets_no_tooltip_attribute(tmp_path: Path) -> None:
    output_path = tmp_path / "l2.drawio"
    render_diagram(_diagram(), output_path)

    root = ET.fromstring(output_path.read_text(encoding="utf-8"))
    assert all(obj.get("tooltip") is None for obj in root.findall(".//object"))


def _ring_diagram(end_label: str) -> Diagram:
    """Five switches in a ring, every link end carrying `end_label`.

    A ring gives the layout no natural place to put a node far from the others, which is
    what makes the closest pair worth measuring.
    """
    names = [f"sw{index}" for index in range(5)]
    return Diagram(
        nodes=[DiagramNode(id=name, label=name, role=DeviceRole.SWITCH) for name in names],
        links=[
            DiagramLink(
                source=name,
                target=names[(index + 1) % len(names)],
                src_label=end_label,
                trgt_label=end_label,
            )
            for index, name in enumerate(names)
        ],
    )


def _closest_node_pair_distance(output_path: Path) -> float:
    root = ET.fromstring(output_path.read_text(encoding="utf-8"))
    positions = []
    for node_object in root.findall(".//object"):
        cell = node_object.find("./mxCell")
        if cell is None or cell.get("edge") == "1":
            continue
        geometry = cell.find("./mxGeometry")
        if geometry is not None and geometry.get("x") is not None:
            positions.append((float(geometry.get("x", 0)), float(geometry.get("y", 0))))
    return min(math.dist(one, other) for one, other in combinations(positions, 2))


def test_the_closest_two_nodes_leave_room_for_the_labels_between_them(tmp_path: Path) -> None:
    # The regression: N2G fits its layout into one fixed-size canvas, which left the STP
    # view's closest nodes ~157px apart -- less than the width of a single
    # "Gi1/0/3 designated/forwarding" label, so icons and labels piled up unreadably.
    # That label renders about 174px wide, and the gap has to hold two of them: the facing
    # halves of both nodes' own labels, plus the link end label pinned between them.
    output_path = tmp_path / "stp.drawio"
    render_diagram(_ring_diagram("Gi1/0/3 designated/forwarding"), output_path)

    assert _closest_node_pair_distance(output_path) > 2 * 174


def test_long_labels_push_the_nodes_further_apart_than_short_ones(tmp_path: Path) -> None:
    """Spacing follows the labels a view actually writes, so the L2 view stays compact."""
    long_labels = tmp_path / "stp.drawio"
    short_labels = tmp_path / "l2.drawio"
    render_diagram(_ring_diagram("Gi1/0/3 designated/forwarding"), long_labels)
    render_diagram(_ring_diagram("Gi1/0/3"), short_labels)

    assert _closest_node_pair_distance(long_labels) > _closest_node_pair_distance(short_labels)


def test_a_single_node_diagram_needs_no_spacing_and_still_renders(tmp_path: Path) -> None:
    """There is no pair to measure, so the spacing pass has to leave the node alone."""
    output_path = tmp_path / "stp.drawio"
    diagram = Diagram(nodes=[DiagramNode(id="sw1", label="sw1", role=DeviceRole.SWITCH)])
    render_diagram(diagram, output_path)

    root = ET.fromstring(output_path.read_text(encoding="utf-8"))
    assert root.find(".//object[@id='sw1']") is not None
