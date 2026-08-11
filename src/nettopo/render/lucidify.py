"""Post-process draw.io XML so each link's per-end labels stay readable (PROJECT_SPEC.md section 8).

N2G emits each link's per-end interface label (`src_label`/`trgt_label`) as a separate
`<mxCell>` vertex with geometry relative to the link's own `<object>` cell (`x="-0.5"`
near the source, `x="0.5"` near the target). That shape causes two problems: Lucid's
draw.io importer does not handle the relative-geometry child-of-an-edge pattern and
mangles or drops these labels, and folding both ends into one centered label would run
them together into a single string -- unreadable in the STP view, where each end carries
its own role/state and the two must stay told apart.

This detaches each end label into a free-standing top-level vertex with absolute geometry,
placed just outside its own node along the link, on the opposite side of the line from the
other end's label, and stepped further aside where a busy node would otherwise pile its
links' labels on top of each other. Node coordinates are already absolute by this point
because `render/drawio.py` runs N2G's igraph layout before dumping the XML. It also cleans
up the malformed (doubled) semicolons N2G's XML templates leave behind in style strings,
e.g. `drawio_link_label_xml` always appends `;` after `{style}` even when the style
already ends in one.

Applied by default to every generated diagram; `--no-lucidify` on the CLI skips it.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass

_MALFORMED_STYLE = re.compile(r";{2,}")

# Size and look of a detached label, in draw.io canvas units.
_LABEL_HEIGHT = 20.0  # one 12px line plus draw.io's default vertical padding
_LABEL_MIN_WIDTH = 40.0
_LABEL_CHAR_WIDTH = 7.0
_LABEL_PADDING = 8.0
# `text;html=1` is draw.io's own free-text vertex, which foreign importers understand. The
# white fill replaces N2G's `labelBackgroundColor`, a draw.io-specific attribute of exactly
# the kind this module exists to route around, and keeps the text legible over the link.
_LABEL_STYLE = (
    "text;html=1;strokeColor=none;fillColor=#FFFFFF;"
    "align=center;verticalAlign=middle;whiteSpace=nowrap;"
)

# Placement of a detached label relative to its own node and to the link line.
_NODE_CLEARANCE = 12.0  # one draw.io grid step plus 2, so the label reads as detached from the icon
_LINE_CLEARANCE = 2.0
_STACK_GAP = 4.0
# How far a crowded label may step away from its link before it is left where it started.
_MAX_STACK_RANK = 6
# A label's center never passes this far toward the far node, so which end it describes
# stays unambiguous even where the two nodes sit close enough to crowd both labels.
_MAX_END_FRACTION = 0.45
# Below this much separation there is no link direction to follow.
_COINCIDENT_EPSILON = 1.0


@dataclass(frozen=True)
class _Box:
    """An absolutely positioned draw.io cell, in center-plus-extent form."""

    center: tuple[float, float]
    width: float
    height: float


@dataclass(frozen=True)
class _EndLabel:
    """One end label of one link, resolved onto the two nodes that link runs between."""

    cell: ET.Element
    value: str
    own: _Box  # the node this end sits at
    other: _Box  # the node at the far end
    at_source: bool


def lucidify_xml(xml_text: str) -> str:
    """Return `xml_text` (a full N2G draw.io document) made Lucid-import-friendly."""
    root = ET.fromstring(xml_text)
    for diagram_root in root.iterfind("./diagram/mxGraphModel/root"):
        _float_link_end_labels(diagram_root)
    _clean_styles(root)
    return ET.tostring(root, encoding="unicode")


def _float_link_end_labels(diagram_root: ET.Element) -> None:
    """Detach every link's end labels into free-standing vertices beside their own node."""
    node_boxes = _node_boxes(diagram_root)
    endpoints = _edge_endpoints(diagram_root)

    end_labels: list[_EndLabel] = []
    for cell, (source_id, target_id) in _end_label_cells(diagram_root, endpoints):
        value = (cell.get("value") or "").strip()
        if not value:
            # A blank label would leave nothing but a white rectangle on the canvas.
            diagram_root.remove(cell)
            continue

        # The relative x N2G gave the cell is the only record of which end it describes.
        at_source = _geometry_x(cell) < 0.0
        own_id, other_id = (source_id, target_id) if at_source else (target_id, source_id)
        own, other = node_boxes.get(own_id), node_boxes.get(other_id)
        if own is None or other is None:
            # With no box to anchor to there is nowhere to put the label. Leaving N2G's
            # cell as it stands keeps the port name, which beats dropping it outright.
            continue

        end_labels.append(
            _EndLabel(cell=cell, value=value, own=own, other=other, at_source=at_source)
        )

    # Placement order decides which label of a crowded pair keeps the closer spot, so it has
    # to be stable: the views sort their links before rendering, and N2G emits them in that
    # order, which is the order these cells come back in.
    obstacles = list(node_boxes.values())
    for end_label in end_labels:
        box = _placed_box(end_label, obstacles)
        obstacles.append(box)
        _detach(diagram_root, end_label.cell, box)


def _node_boxes(diagram_root: ET.Element) -> dict[str, _Box]:
    """Map every node's id to its absolute box.

    The id lives on the wrapping `<object>` -- N2G leaves the inner `<mxCell>` without one.
    """
    boxes: dict[str, _Box] = {}
    for node_object in diagram_root.findall("./object"):
        node_id = node_object.get("id")
        geometry = node_object.find("./mxCell[@vertex='1']/mxGeometry")
        if node_id is None or geometry is None:
            continue
        box = _box(geometry)
        if box is not None:
            boxes[node_id] = box
    return boxes


def _box(geometry: ET.Element) -> _Box | None:
    """Read an absolute `<mxGeometry>`, or None when it is relative or malformed."""
    try:
        x = float(geometry.get("x", ""))
        y = float(geometry.get("y", ""))
        width = float(geometry.get("width", ""))
        height = float(geometry.get("height", ""))
    except ValueError:
        return None
    # draw.io anchors geometry at the top-left; every placement below reasons about centers.
    return _Box(center=(x + width / 2, y + height / 2), width=width, height=height)


def _edge_endpoints(diagram_root: ET.Element) -> dict[str, tuple[str, str]]:
    """Map every link's id to the pair of node ids it connects.

    Read from the edge `<mxCell>` rather than the `<object>`'s mirrored attributes: the
    cell is what draw.io itself wires the link up from.
    """
    endpoints: dict[str, tuple[str, str]] = {}
    for link_object in diagram_root.findall("./object"):
        link_id = link_object.get("id")
        edge_cell = link_object.find("./mxCell[@edge='1']")
        if link_id is None or edge_cell is None:
            continue
        source_id, target_id = edge_cell.get("source"), edge_cell.get("target")
        if source_id is not None and target_id is not None:
            endpoints[link_id] = (source_id, target_id)
    return endpoints


def _end_label_cells(
    diagram_root: ET.Element, endpoints: dict[str, tuple[str, str]]
) -> list[tuple[ET.Element, tuple[str, str]]]:
    """The label cells N2G parented to a link, each paired with that link's endpoints."""
    return [
        (cell, endpoints[parent_id])
        for cell in diagram_root.findall("./mxCell")
        if (parent_id := cell.get("parent")) is not None and parent_id in endpoints
    ]


def _placed_box(end_label: _EndLabel, obstacles: Iterable[_Box]) -> _Box:
    """Position a label beside its own node, stepping it aside to miss `obstacles`.

    A node with several links crowds all of their labels into the same corner: parallel
    links land theirs on identical points, and links merely leaving at similar angles land
    them close enough to overlap. Each step out along the link's normal buys one label
    height, and stepping is bounded -- past that the diagram is dense enough that staying
    near the right node matters more than not touching anything.
    """
    width, height = _label_size(end_label.value)
    for rank in range(_MAX_STACK_RANK + 1):
        box = _label_box(end_label, width, height, rank)
        if not any(_overlap(box, obstacle) for obstacle in obstacles):
            return box
    return _label_box(end_label, width, height, rank=0)


def _overlap(box: _Box, other: _Box) -> bool:
    (x, y), (other_x, other_y) = box.center, other.center
    return (
        abs(x - other_x) < (box.width + other.width) / 2
        and abs(y - other_y) < (box.height + other.height) / 2
    )


def _label_size(value: str) -> tuple[float, float]:
    """Estimate a box big enough to hold `value`.

    draw.io stores geometry, not measured text, so the width has to come from the character
    count: Helvetica 12px averages a little under 7px per character, rounded up here so a
    label is never clipped by its own background.
    """
    width = max(_LABEL_MIN_WIDTH, len(value) * _LABEL_CHAR_WIDTH + _LABEL_PADDING)
    return width, _LABEL_HEIGHT


def _label_box(end_label: _EndLabel, width: float, height: float, rank: int) -> _Box:
    """Place a label just clear of its own node, `rank` steps aside from the link line."""
    (own_x, own_y) = end_label.own.center
    (other_x, other_y) = end_label.other.center
    span = math.hypot(other_x - own_x, other_y - own_y)
    if span > _COINCIDENT_EPSILON:
        unit_x, unit_y = (other_x - own_x) / span, (other_y - own_y) / span
    else:
        # Nodes drawn on top of each other leave no direction to follow. Sending the source
        # end left and the target end right still tells the two labels apart, in reading order.
        unit_x, unit_y = (-1.0, 0.0) if end_label.at_source else (1.0, 0.0)

    # Adding the label's own half-extent puts its near edge a fixed clearance past the node
    # boundary however long the text is, instead of burying half of it under the icon.
    along = (
        _ray_exit_distance(end_label.own, unit_x, unit_y)
        + _NODE_CLEARANCE
        + _projected_half_extent(width, height, unit_x, unit_y)
    )
    if span > _COINCIDENT_EPSILON:
        along = min(along, span * _MAX_END_FRACTION)

    # The far end's direction is this one's negation, so its normal is negated too and a
    # link's two labels always come to rest on opposite sides of the line.
    aside = height / 2 + _LINE_CLEARANCE + rank * (height + _STACK_GAP)
    return _Box(
        center=(own_x + unit_x * along - unit_y * aside, own_y + unit_y * along + unit_x * aside),
        width=width,
        height=height,
    )


def _ray_exit_distance(box: _Box, unit_x: float, unit_y: float) -> float:
    """Distance from `box`'s center to where the ray `(unit_x, unit_y)` leaves it."""
    # A unit vector always has a non-zero component, so this never ends up empty.
    candidates: list[float] = []
    if unit_x != 0.0:
        candidates.append((box.width / 2) / abs(unit_x))
    if unit_y != 0.0:
        candidates.append((box.height / 2) / abs(unit_y))
    return min(candidates)


def _projected_half_extent(width: float, height: float, unit_x: float, unit_y: float) -> float:
    """Half the length of a box's shadow on the direction `(unit_x, unit_y)`."""
    return (width / 2) * abs(unit_x) + (height / 2) * abs(unit_y)


def _detach(diagram_root: ET.Element, cell: ET.Element, box: _Box) -> None:
    """Re-home `cell` on the canvas itself, occupying `box` in absolute geometry."""
    cell.set("parent", "1")
    cell.set("style", _LABEL_STYLE)
    for child in list(cell):  # drops the relative <mxGeometry> and its <mxPoint as="offset"/>
        cell.remove(child)
    ET.SubElement(
        cell,
        "mxGeometry",
        {
            "x": _coordinate(box.center[0] - box.width / 2),
            "y": _coordinate(box.center[1] - box.height / 2),
            "width": _coordinate(box.width),
            "height": _coordinate(box.height),
            "as": "geometry",
        },
    )
    # ElementTree has no move operation, and N2G emits these cells ahead of the links they
    # belong to; re-appending puts each label last, so it paints over the line, not under it.
    diagram_root.remove(cell)
    diagram_root.append(cell)


def _coordinate(value: float) -> str:
    """Round to whole canvas units: draw.io snaps to a 10px grid, and integers keep the
    generated XML diffable."""
    return str(round(value))


def _geometry_x(cell: ET.Element) -> float:
    """The cell's relative position along its link: negative at the source end, positive at
    the target end."""
    geometry = cell.find("./mxGeometry")
    if geometry is None:
        return 0.0
    try:
        return float(geometry.get("x", "0"))
    except ValueError:
        return 0.0


def _clean_styles(root: ET.Element) -> None:
    for element in root.iter():
        style = element.get("style")
        if style is None:
            continue
        cleaned = _MALFORMED_STYLE.sub(";", style).strip(";")
        if cleaned:
            cleaned += ";"
        if cleaned != style:
            element.set("style", cleaned)
