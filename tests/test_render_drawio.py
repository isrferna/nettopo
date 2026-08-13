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
from nettopo.render.icons import LINK_LABEL_STYLE, node_style
from nettopo.views.diagram import Diagram, DiagramLink, DiagramNode, LegendEntry


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
    assert "mxgraph.cisco19.rect;prIcon=router" in router_cell.get("style", "")


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


def test_highlighted_node_style_carries_the_highlight_fill(tmp_path: Path) -> None:
    output_path = tmp_path / "stp.drawio"
    diagram = Diagram(
        nodes=[DiagramNode(id="root", label="root", role=DeviceRole.SWITCH, highlight=True)]
    )
    render_diagram(diagram, output_path)

    root = ET.fromstring(output_path.read_text(encoding="utf-8"))
    node_cell = root.find(".//object[@id='root']/mxCell")
    assert node_cell is not None
    assert "fillColor=#FFF3C4;" in node_cell.get("style", "")


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
    # The gap has to hold a full-width node icon (120px) plus that end label, which renders
    # about 136px wide at the size `icons.LINK_LABEL_STYLE` sets.
    output_path = tmp_path / "stp.drawio"
    render_diagram(_ring_diagram("Gi1/0/3 designated/forwarding"), output_path)

    assert _closest_node_pair_distance(output_path) > 120 + 136


def test_long_labels_push_the_nodes_further_apart_than_short_ones(tmp_path: Path) -> None:
    """Spacing follows the labels a view actually writes, so the L2 view stays compact."""
    long_labels = tmp_path / "stp.drawio"
    short_labels = tmp_path / "l2.drawio"
    render_diagram(_ring_diagram("Gi1/0/3 designated/forwarding"), long_labels)
    render_diagram(_ring_diagram("Gi1/0/3"), short_labels)

    assert _closest_node_pair_distance(long_labels) > _closest_node_pair_distance(short_labels)


def test_a_multi_line_node_label_is_broken_where_the_view_broke_it(tmp_path: Path) -> None:
    """Views separate a label's lines with `\\n`, which draw.io would render as a space.

    The label is an XML attribute (newline normalized to a space by the parser) drawn as
    HTML (newline is plain whitespace), so the break has to be an HTML one to survive.
    """
    output_path = tmp_path / "labels.drawio"
    render_diagram(
        Diagram(nodes=[DiagramNode(id="sw1", label="sw1\n10.0.0.1", role=DeviceRole.SWITCH)]),
        output_path,
    )

    (node,) = ET.fromstring(output_path.read_text(encoding="utf-8")).findall(".//object")
    assert node.get("label") == "sw1<br>10.0.0.1"


def test_a_multi_line_label_is_measured_by_its_widest_line(tmp_path: Path) -> None:
    """Its lines are drawn one under another, so stacking more of them is not wider."""
    stacked = tmp_path / "stacked.drawio"
    one_line = tmp_path / "one-line.drawio"
    render_diagram(_ring_diagram("Gi1/0/3\ndesignated\nforwarding"), stacked)
    render_diagram(_ring_diagram("Gi1/0/3 designated forwarding"), one_line)

    assert _closest_node_pair_distance(stacked) < _closest_node_pair_distance(one_line)


def test_a_single_node_diagram_needs_no_spacing_and_still_renders(tmp_path: Path) -> None:
    """There is no pair to measure, so the spacing pass has to leave the node alone."""
    output_path = tmp_path / "stp.drawio"
    diagram = Diagram(nodes=[DiagramNode(id="sw1", label="sw1", role=DeviceRole.SWITCH)])
    render_diagram(diagram, output_path)

    root = ET.fromstring(output_path.read_text(encoding="utf-8"))
    assert root.find(".//object[@id='sw1']") is not None


def test_nodes_are_sized_to_their_icon_rather_than_n2gs_default(tmp_path: Path) -> None:
    """cisco19 styles carry `aspect=fixed`, so a mismatched geometry stretches the icon."""
    output_path = tmp_path / "l2.drawio"
    render_diagram(_diagram(), output_path)

    root = ET.fromstring(output_path.read_text(encoding="utf-8"))
    geometry = root.find(".//object[@id='rtr1']/mxCell/mxGeometry")
    assert geometry is not None
    expected = node_style(DeviceRole.ROUTER)
    assert geometry.get("width") == str(expected.width)
    assert geometry.get("height") == str(expected.height)


def test_link_end_labels_are_set_smaller_than_the_body_text(tmp_path: Path) -> None:
    """Interface labels sit where links cross, so they get their own compact style."""
    output_path = tmp_path / "l2.drawio"
    render_diagram(_diagram(), output_path)

    root = ET.fromstring(output_path.read_text(encoding="utf-8"))
    end_labels = [
        cell for cell in root.iter("mxCell") if cell.get("value") in {"Gi1/0/1", "Gi0/0/0"}
    ]
    assert len(end_labels) == 2
    assert all(LINK_LABEL_STYLE in cell.get("style", "") for cell in end_labels)


def _legend_diagram() -> Diagram:
    diagram = _ring_diagram("Gi1/0/3")
    diagram.legend = [
        LegendEntry(label="Root bridge", role=DeviceRole.SWITCH, highlight=True),
        LegendEntry(label="Blocked at one end", color="#C62828"),
    ]
    return diagram


def test_the_legend_is_drawn_when_a_view_asks_for_one(tmp_path: Path) -> None:
    output_path = tmp_path / "stp.drawio"
    render_diagram(_legend_diagram(), output_path)

    root = ET.fromstring(output_path.read_text(encoding="utf-8"))
    labels = {cell.get("value") for cell in root.iter("mxCell")}
    assert {"Legend", "Root bridge", "Blocked at one end"} <= labels
    # The blocking swatch has to carry the color the links themselves were drawn in.
    assert any("#C62828" in cell.get("style", "") for cell in root.iter("mxCell"))


def test_a_diagram_with_no_legend_entries_gets_no_legend_box(tmp_path: Path) -> None:
    output_path = tmp_path / "stp.drawio"
    render_diagram(_ring_diagram("Gi1/0/3"), output_path)

    root = ET.fromstring(output_path.read_text(encoding="utf-8"))
    assert "Legend" not in {cell.get("value") for cell in root.iter("mxCell")}


def test_the_legend_is_not_counted_as_a_link(tmp_path: Path) -> None:
    """A swatch is drawn as a filled bar, so anything counting edges still sees five."""
    output_path = tmp_path / "stp.drawio"
    render_diagram(_legend_diagram(), output_path)

    root = ET.fromstring(output_path.read_text(encoding="utf-8"))
    assert len(root.findall(".//mxCell[@edge='1']")) == 5


def test_the_legend_sits_clear_of_every_node(tmp_path: Path) -> None:
    """It is added after the spread, so the scaling must not have dragged it into them."""
    output_path = tmp_path / "stp.drawio"
    render_diagram(_legend_diagram(), output_path)

    root = ET.fromstring(output_path.read_text(encoding="utf-8"))
    box = root.find(".//mxCell[@id='legend']/mxGeometry")
    assert box is not None
    legend_bottom = float(box.get("y", 0)) + float(box.get("height", 0))

    node_tops = []
    for node_object in root.findall(".//object"):
        cell = node_object.find("./mxCell")
        if cell is None or cell.get("edge") == "1":
            continue
        geometry = cell.find("./mxGeometry")
        if geometry is not None and geometry.get("x") is not None:
            node_tops.append(float(geometry.get("y", 0)))
    assert legend_bottom < min(node_tops)
