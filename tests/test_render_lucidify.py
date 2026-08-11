"""Tests for the draw.io link-label post-process (PROJECT_SPEC.md section 8).

Fixture XML mirrors exactly what N2G's `drawio_diagram.add_link(src_label=...,
trgt_label=...)` emits: two `<mxCell>` label vertices parented to the link's `<object>` id,
with relative geometry (`x="-0.5"` near the source, `x="0.5"` near the target), emitted
ahead of the link they belong to, and a doubled `;;` in their style from N2G's XML
template.

Unlike `test_render_drawio.py`, these tests may assert positions: they run the transform
against fixed fixture coordinates, not against igraph's layout output.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from nettopo.render.lucidify import lucidify_xml

_NODE_WIDTH = 120.0
_NODE_HEIGHT = 60.0

_NODE_XML = """<object id="{id}" label="{id}">
      <mxCell style="shape=mxgraph.cisco.switches.workgroup_switch;" vertex="1" parent="1">
          <mxGeometry x="{x}" y="{y}" width="120" height="60" as="geometry" />
      </mxCell>
    </object>"""

_LABEL_XML = """<mxCell id="{id}-{end}" value="{value}" style="labelBackgroundColor=#ffffff;;" \
vertex="1" connectable="0" parent="{id}">
      <mxGeometry x="{position}" relative="1" as="geometry">
        <mxPoint as="offset" />
      </mxGeometry>
    </mxCell>"""

_LINK_XML = """<object id="{id}" label="" src_label="{src_label}" trgt_label="{trgt_label}" \
source="{source}" target="{target}">
      <mxCell style="endArrow=none;" edge="1" parent="1" source="{source}" target="{target}">
          <mxGeometry relative="1" as="geometry" />
      </mxCell>
    </object>"""

_DOCUMENT_XML = """<mxfile type="device" compressed="false">
    <diagram id="diagram_1" name="diagram_1">
      <mxGraphModel dx="1360" dy="864" grid="1">
        <root>
          <mxCell id="0" />
          <mxCell id="1" parent="0" />
        {body}</root>
      </mxGraphModel>
    </diagram></mxfile>"""


def _document(
    nodes: dict[str, tuple[float, float]],
    links: list[tuple[str, str, str, str, str]],
) -> str:
    """Build an N2G-shaped document from `{node id: top-left}` and `(id, source, target,
    src_label, trgt_label)` links. A blank label still gets a cell, so the empty-value path
    can be exercised."""
    body = [_NODE_XML.format(id=node_id, x=x, y=y) for node_id, (x, y) in nodes.items()]
    for link_id, source, target, src_label, trgt_label in links:
        body.append(_LABEL_XML.format(id=link_id, end="src", value=src_label, position="-0.5"))
        body.append(_LABEL_XML.format(id=link_id, end="trgt", value=trgt_label, position="0.5"))
        body.append(
            _LINK_XML.format(
                id=link_id,
                source=source,
                target=target,
                src_label=src_label,
                trgt_label=trgt_label,
            )
        )
    return _DOCUMENT_XML.format(body="".join(body))


_STRAIGHT_LINK = _document(
    nodes={"sw1": (100.0, 400.0), "sw2": (700.0, 400.0)},
    links=[("link1", "sw1", "sw2", "Gi1/0/1", "Gi1/0/24")],
)
# Node boxes nearly touching, so both labels hit the "never past the midpoint" clamp.
_SHORT_LINK = _document(
    nodes={"sw1": (100.0, 400.0), "sw2": (250.0, 400.0)},
    links=[("link1", "sw1", "sw2", "Gi1/0/1", "Gi1/0/24")],
)
_COINCIDENT_NODES = _document(
    nodes={"sw1": (200.0, 150.0), "sw2": (200.0, 150.0)},
    links=[("link1", "sw1", "sw2", "Gi1/0/1", "Gi1/0/24")],
)


def _cells_by_id(xml_text: str) -> dict[str, ET.Element]:
    root = ET.fromstring(lucidify_xml(xml_text))
    return {
        cell_id: cell
        for cell in root.findall(".//root/mxCell")
        if (cell_id := cell.get("id")) is not None
    }


def _box(cell: ET.Element) -> tuple[float, float, float, float]:
    """The cell's absolute geometry as `(left, top, width, height)`."""
    geometry = cell.find("./mxGeometry")
    assert geometry is not None
    return (
        float(geometry.get("x", "")),
        float(geometry.get("y", "")),
        float(geometry.get("width", "")),
        float(geometry.get("height", "")),
    )


def _center(cell: ET.Element) -> tuple[float, float]:
    left, top, width, height = _box(cell)
    return left + width / 2, top + height / 2


def _overlaps(
    first: tuple[float, float, float, float], second: tuple[float, float, float, float]
) -> bool:
    left, top, width, height = first
    other_left, other_top, other_width, other_height = second
    return (
        left < other_left + other_width
        and other_left < left + width
        and top < other_top + other_height
        and other_top < top + height
    )


def test_result_is_well_formed_xml() -> None:
    ET.fromstring(lucidify_xml(_STRAIGHT_LINK))


def test_the_links_own_label_attribute_is_left_alone() -> None:
    root = ET.fromstring(lucidify_xml(_STRAIGHT_LINK))
    link_object = root.find(".//object[@id='link1']")
    assert link_object is not None
    assert link_object.get("label") == ""


def test_end_label_cells_are_reparented_onto_the_canvas_root() -> None:
    cells = _cells_by_id(_STRAIGHT_LINK)
    for cell_id in ("link1-src", "link1-trgt"):
        assert cells[cell_id].get("parent") == "1"
        assert cells[cell_id].get("vertex") == "1"


def test_end_label_geometry_becomes_absolute() -> None:
    cells = _cells_by_id(_STRAIGHT_LINK)
    for cell_id in ("link1-src", "link1-trgt"):
        geometry = cells[cell_id].find("./mxGeometry")
        assert geometry is not None
        assert geometry.get("relative") is None
        assert geometry.find("./mxPoint") is None
        _, _, width, height = _box(cells[cell_id])
        assert width > 0
        assert height > 0


def test_each_end_label_sits_on_its_own_half_of_the_link() -> None:
    cells = _cells_by_id(_STRAIGHT_LINK)
    midpoint_x = (160.0 + 760.0) / 2

    assert 160.0 < _center(cells["link1-src"])[0] < midpoint_x
    assert midpoint_x < _center(cells["link1-trgt"])[0] < 760.0


def test_label_boxes_stay_clear_of_the_node_boxes() -> None:
    cells = _cells_by_id(_STRAIGHT_LINK)
    node_boxes = [
        (100.0, 400.0, _NODE_WIDTH, _NODE_HEIGHT),
        (700.0, 400.0, _NODE_WIDTH, _NODE_HEIGHT),
    ]

    for cell_id in ("link1-src", "link1-trgt"):
        for node_box in node_boxes:
            assert not _overlaps(_box(cells[cell_id]), node_box)


def test_the_two_end_labels_land_on_opposite_sides_of_the_link_line() -> None:
    cells = _cells_by_id(_STRAIGHT_LINK)
    link_y = 430.0

    source_offset = _center(cells["link1-src"])[1] - link_y
    target_offset = _center(cells["link1-trgt"])[1] - link_y
    assert source_offset * target_offset < 0


def test_a_short_link_still_keeps_each_label_on_its_own_side() -> None:
    cells = _cells_by_id(_SHORT_LINK)
    midpoint_x = (160.0 + 310.0) / 2

    assert _center(cells["link1-src"])[0] < midpoint_x
    assert _center(cells["link1-trgt"])[0] > midpoint_x


def test_a_vertical_link_clears_the_shorter_side_of_the_node_box() -> None:
    # A node is 120 wide but only 60 tall, so a vertical link has to clear far less than a
    # horizontal one -- the clearance follows the box, it is not one flat number.
    cells = _cells_by_id(
        _document(
            nodes={"sw1": (100.0, 100.0), "sw2": (100.0, 700.0)},
            links=[("link1", "sw1", "sw2", "Gi1/0/1", "Gi1/0/24")],
        )
    )

    assert not _overlaps(_box(cells["link1-src"]), (100.0, 100.0, _NODE_WIDTH, _NODE_HEIGHT))
    assert _center(cells["link1-src"])[1] < _center(cells["link1-trgt"])[1]


def test_coincident_nodes_separate_the_labels_instead_of_stacking_them() -> None:
    cells = _cells_by_id(_COINCIDENT_NODES)

    assert _center(cells["link1-src"])[0] != _center(cells["link1-trgt"])[0]


def test_a_self_loop_is_placed_without_crashing() -> None:
    cells = _cells_by_id(
        _document(
            nodes={"sw1": (100.0, 400.0)}, links=[("link1", "sw1", "sw1", "Gi1/0/1", "Gi1/0/2")]
        )
    )

    assert _center(cells["link1-src"]) != _center(cells["link1-trgt"])


def test_labels_whose_endpoints_have_no_geometry_are_left_untouched() -> None:
    # "ghost" is named by the link but never drawn, so neither end has a box to anchor to.
    cells = _cells_by_id(
        _document(
            nodes={"sw1": (100.0, 400.0)},
            links=[("link1", "sw1", "ghost", "Gi1/0/1", "Gi1/0/24")],
        )
    )

    for cell_id in ("link1-src", "link1-trgt"):
        assert cells[cell_id].get("parent") == "link1"
        geometry = cells[cell_id].find("./mxGeometry")
        assert geometry is not None
        assert geometry.get("relative") == "1"


def test_a_blank_label_leaves_no_floating_vertex_behind() -> None:
    cells = _cells_by_id(
        _document(
            nodes={"sw1": (100.0, 400.0), "sw2": (700.0, 400.0)},
            links=[("link1", "sw1", "sw2", "Gi1/0/1", "")],
        )
    )

    assert "link1-trgt" not in cells
    assert "link1-src" in cells


def test_parallel_links_between_one_pair_do_not_stack_their_labels() -> None:
    # The second link is discovered from the other device, so its *target* end is the one
    # at sw1 -- placement has to see past that to keep the two labels there apart.
    cells = _cells_by_id(
        _document(
            nodes={"sw1": (100.0, 400.0), "sw2": (700.0, 400.0)},
            links=[
                ("link1", "sw1", "sw2", "Gi1/0/1", "Gi1/0/24"),
                ("link2", "sw2", "sw1", "Gi1/0/25", "Gi1/0/2"),
            ],
        )
    )

    assert not _overlaps(_box(cells["link1-src"]), _box(cells["link2-trgt"]))
    assert not _overlaps(_box(cells["link1-trgt"]), _box(cells["link2-src"]))


def test_two_links_leaving_one_node_do_not_crowd_their_labels_together() -> None:
    # Both links leave sw1 rightward within a few degrees of each other, so their labels
    # start out on top of one another and only a step aside separates them.
    cells = _cells_by_id(
        _document(
            nodes={"sw1": (100.0, 400.0), "sw2": (900.0, 380.0), "sw3": (900.0, 480.0)},
            links=[
                ("link1", "sw1", "sw2", "Gi1/0/1 designated/forwarding", "Gi0/1 root/forwarding"),
                ("link2", "sw1", "sw3", "Gi1/0/2 designated/forwarding", "Gi0/1 root/forwarding"),
            ],
        )
    )

    assert not _overlaps(_box(cells["link1-src"]), _box(cells["link2-src"]))


def test_a_label_stepped_aside_does_not_land_on_a_node() -> None:
    # Two port-channel members between one pair of switches, at the coordinates igraph laid
    # them out at in tests/fixtures/stp_portchannel: the second link's labels have to step
    # aside to miss the first's, and a step that only dodged other labels landed on a node.
    node_positions = {"po-sw1": (532.0, 400.0), "po-sw2": (737.0, 0.0)}
    cells = _cells_by_id(
        _document(
            nodes=node_positions,
            links=[
                ("link1", "po-sw1", "po-sw2", "Gi1/0/1", "Gi1/0/1"),
                ("link2", "po-sw1", "po-sw2", "Gi1/0/2", "Gi1/0/2"),
            ],
        )
    )

    for cell_id in ("link1-src", "link1-trgt", "link2-src", "link2-trgt"):
        for x, y in node_positions.values():
            assert not _overlaps(_box(cells[cell_id]), (x, y, _NODE_WIDTH, _NODE_HEIGHT))


def test_end_labels_are_emitted_after_the_links_they_belong_to() -> None:
    root = ET.fromstring(lucidify_xml(_STRAIGHT_LINK))
    diagram_root = root.find(".//root")
    assert diagram_root is not None

    children = list(diagram_root)
    link_index = next(i for i, child in enumerate(children) if child.get("id") == "link1")
    label_indexes = [
        i for i, child in enumerate(children) if (child.get("id") or "").startswith("link1-")
    ]
    assert all(index > link_index for index in label_indexes)


def test_doubled_semicolons_in_style_strings_are_cleaned() -> None:
    root = ET.fromstring(lucidify_xml(_STRAIGHT_LINK))
    for element in root.iter():
        style = element.get("style")
        if style is not None:
            assert ";;" not in style


def test_nodes_and_the_link_object_itself_survive_unchanged_otherwise() -> None:
    root = ET.fromstring(lucidify_xml(_STRAIGHT_LINK))
    assert root.find(".//object[@id='sw1']") is not None
    assert root.find(".//object[@id='sw2']") is not None

    link_cell = root.find(".//object[@id='link1']/mxCell")
    assert link_cell is not None
    assert link_cell.get("source") == "sw1"
    assert link_cell.get("target") == "sw2"
