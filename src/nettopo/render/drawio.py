"""Thin wrapper over N2G `drawio_diagram` (PROJECT_SPEC.md section 8).

The only module that imports N2G. If N2G is ever replaced, only this module changes --
`views/` and `model/` know nothing about N2G or draw.io concepts.
"""

from __future__ import annotations

import math
from itertools import combinations
from pathlib import Path
from xml.etree.ElementTree import Element

from N2G import drawio_diagram

from nettopo.render.icons import LINK_LABEL_STYLE, MAX_NODE_WIDTH_PX, link_style, node_style
from nettopo.render.legend import add_legend
from nettopo.render.lucidify import lucidify_xml
from nettopo.views.diagram import Diagram, DiagramLink

_DIAGRAM_ID = "diagram_1"

# Width of one character in draw.io's default label font, measured off an export.
_LABEL_CHARACTER_WIDTH_PX = 6

# How many label widths of clear space to leave between the two closest nodes, on top of
# the icons themselves. More than one is needed because draw.io centers a node's label
# under its icon *and* pins each link end label near that same end, so the gap between two
# neighbors has to hold both nodes' labels and the link end label sitting between them.
# Tuned down from 1.5 against the campus example's exported PNGs: link end labels are now
# set several points smaller than node labels (`icons.LINK_LABEL_STYLE`), so the same gap
# holds more, and the diagram no longer needs to be as sparse to stay readable.
_LABEL_CLEARANCE = 1.3

# Views write a node label's lines separated by `\n` (`core-sw1\n10.10.10.2`), which is not
# a line break by the time draw.io reads it: the label is an XML attribute, where any
# conforming parser normalizes a newline to a space, and it is then rendered as HTML, where
# a newline is whitespace like any other. An HTML `<br>` survives both -- the same break
# `views/diagram.py` already uses inside a link tooltip, for the same reason. It is spelled
# escaped here because N2G formats the label into an XML template before parsing it, so a
# bare `<br>` would be markup rather than the text the attribute has to carry.
_LABEL_LINE_BREAK = "&lt;br&gt;"


def render_diagram(diagram: Diagram, output_path: Path, *, apply_lucidify: bool = True) -> None:
    """Render `diagram` to a draw.io file at `output_path`.

    Applies the Lucidchart-friendliness post-process by default; pass
    `apply_lucidify=False` for the CLI's `--no-lucidify`.
    """
    drawing = drawio_diagram()
    drawing.add_diagram(_DIAGRAM_ID)

    for node in diagram.nodes:
        style = node_style(node.role, highlight=node.highlight, inferred=node.inferred)
        drawing.add_node(
            id=node.id,
            label=node.label.replace("\n", _LABEL_LINE_BREAK),
            style=style.style,
            width=style.width,
            height=style.height,
        )

    for link in diagram.links:
        drawing.add_link(
            source=link.source,
            target=link.target,
            label=link.label,
            src_label=link.src_label,
            trgt_label=link.trgt_label,
            style=link_style(link.color),
            src_label_style=LINK_LABEL_STYLE,
            trgt_label_style=LINK_LABEL_STYLE,
            data=_link_data(link),
        )

    # igraph-backed layout (PROJECT_SPEC.md section 8); without it nodes overlap.
    # igraph's "kk" layout raises on a graph with zero vertices, so skip it for an
    # empty diagram rather than letting that raise out of a routine "no data" case.
    if diagram.nodes:
        drawing.layout(algo="kk")
        _spread_nodes(drawing, _minimum_node_separation(diagram))
        # After the spread, so the legend is placed against the final node positions and
        # is not itself scaled by it.
        add_legend(drawing.current_root, diagram.legend, _top_left(drawing))

    xml_text = drawing.dump_xml()
    if apply_lucidify:
        xml_text = lucidify_xml(xml_text)

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(xml_text, encoding="utf-8")
    except OSError as exc:
        raise OSError(f"failed to write draw.io diagram '{output_path}': {exc}") from exc


def _minimum_node_separation(diagram: Diagram) -> float:
    """Pixels two neighboring nodes need between them for the diagram's labels to fit.

    Derived from the longest label the diagram actually carries, because that is what
    varies between views: the STP view labels a link end "Gi1/0/23 designated/forwarding"
    where the L2 view says "Gi1/0/23", and a spacing that suits the second is unreadable
    for the first. The widest node icon is the floor, for a diagram whose labels are all
    short.

    A multi-line label is measured line by line: what has to fit between two nodes is how
    wide the label is drawn, and `_LABEL_LINE_BREAK` makes each of its lines its own.
    """
    longest_line = max(len(line) for text in _label_texts(diagram) for line in text.split("\n"))
    return MAX_NODE_WIDTH_PX + _LABEL_CLEARANCE * longest_line * _LABEL_CHARACTER_WIDTH_PX


def _label_texts(diagram: Diagram) -> list[str]:
    """Every piece of text the diagram will draw: node labels and all three link labels."""
    return [node.label for node in diagram.nodes] + [
        text for link in diagram.links for text in (link.src_label, link.trgt_label, link.label)
    ]


def _spread_nodes(drawing: drawio_diagram, minimum_separation: float) -> None:
    """Scale the laid-out node positions apart until they are `minimum_separation` apart.

    N2G's `layout()` fits igraph's coordinates into the diagram's fixed canvas, so the
    algorithm choice decides only the *shape* of the layout -- the absolute spacing is
    whatever that one canvas size happens to give, and igraph's own spacing arguments are
    normalized away by the fit. Scaling the result afterwards is therefore the only lever
    on spacing in pixels, and being uniform it preserves the layout igraph computed.

    The measurement is the *closest* pair in the graph, not a typical gap. Scaling to the
    typical gap is tempting, since a force-directed layout routinely leaves one pair much
    tighter than the rest and the whole canvas grows to serve it -- but in this project's
    own STP example that leaves three of seven nodes at roughly half the separation their
    labels need, overlapping. A diagram that is larger than it strictly has to be is a
    smaller problem than one whose labels sit on top of each other, so every pair is made
    to fit.

    Kamada-Kawai ("kk") is kept as the algorithm: of the alternatives N2G offers, "fr"
    packs the closest pair tighter, "drl" collapses this size of graph almost to a point,
    and "rt" flattens it into rows of touching nodes.
    """
    geometries = _node_geometries(drawing)
    positions = [
        (float(geometry.get("x", 0)), float(geometry.get("y", 0))) for geometry in geometries
    ]
    closest = min((math.dist(a, b) for a, b in combinations(positions, 2)), default=0.0)
    if closest <= 0 or closest >= minimum_separation:
        return

    scale = minimum_separation / closest
    for geometry, (x_coord, y_coord) in zip(geometries, positions, strict=True):
        geometry.set("x", str(round(x_coord * scale)))
        geometry.set("y", str(round(y_coord * scale)))


def _top_left(drawing: drawio_diagram) -> tuple[float, float]:
    """Top-left corner of the bounding box the laid-out nodes occupy."""
    geometries = _node_geometries(drawing)
    if not geometries:
        return (0.0, 0.0)
    return (
        min(float(geometry.get("x", 0)) for geometry in geometries),
        min(float(geometry.get("y", 0)) for geometry in geometries),
    )


def _node_geometries(drawing: drawio_diagram) -> list[Element]:
    """The `mxGeometry` of every node in the current diagram, in document order.

    Mirrors how N2G's own `layout()` tells nodes from links: an `<object>` whose `mxCell`
    names both a source and a target is a link, and everything else is a node.
    """
    geometries = []
    for diagram_object in drawing.current_root.iterfind("./object"):
        cell = diagram_object.find("./mxCell")
        if cell is None or (cell.get("source") and cell.get("target")):
            continue
        geometry = cell.find("./mxGeometry")
        if geometry is not None:
            geometries.append(geometry)
    return geometries


def _link_data(link: DiagramLink) -> dict[str, str]:
    """Extra `<object>` attributes for the link.

    draw.io shows the `tooltip` attribute on hover instead of its default dump of every
    attribute, which is how a port-channel link reveals its member interfaces.
    """
    return {"tooltip": link.tooltip} if link.tooltip else {}
