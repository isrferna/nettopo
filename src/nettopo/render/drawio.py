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

from nettopo.render.icons import style_for_role
from nettopo.render.lucidify import lucidify_xml
from nettopo.views.diagram import Diagram, DiagramLink

_DIAGRAM_ID = "diagram_1"

# Every node N2G draws is this wide; two nodes any closer have overlapping icons.
_NODE_WIDTH_PX = 120

# Width of one character in draw.io's default label font, measured off an export.
_LABEL_CHARACTER_WIDTH_PX = 6

# How many label widths of clear space to leave between the two closest nodes, on top of
# the icons themselves. More than one is needed because draw.io centers a node's label
# under its icon *and* pins each link end label near that same end, so the gap between two
# neighbors has to hold both nodes' labels and the link end label sitting between them.
_LABEL_CLEARANCE = 1.5


def render_diagram(diagram: Diagram, output_path: Path, *, apply_lucidify: bool = True) -> None:
    """Render `diagram` to a draw.io file at `output_path`.

    Applies the Lucidchart-friendliness post-process by default; pass
    `apply_lucidify=False` for the CLI's `--no-lucidify`.
    """
    drawing = drawio_diagram()
    drawing.add_diagram(_DIAGRAM_ID)

    for node in diagram.nodes:
        style = style_for_role(node.role, highlight=node.highlight, inferred=node.inferred)
        drawing.add_node(id=node.id, label=node.label, style=style)

    for link in diagram.links:
        drawing.add_link(
            source=link.source,
            target=link.target,
            label=link.label,
            src_label=link.src_label,
            trgt_label=link.trgt_label,
            style=_link_style(link.color),
            data=_link_data(link),
        )

    # igraph-backed layout (PROJECT_SPEC.md section 8); without it nodes overlap.
    # igraph's "kk" layout raises on a graph with zero vertices, so skip it for an
    # empty diagram rather than letting that raise out of a routine "no data" case.
    if diagram.nodes:
        drawing.layout(algo="kk")
        _spread_nodes(drawing, _minimum_node_separation(diagram))

    xml_text = drawing.dump_xml()
    if apply_lucidify:
        xml_text = lucidify_xml(xml_text)

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(xml_text, encoding="utf-8")
    except OSError as exc:
        raise OSError(f"failed to write draw.io diagram '{output_path}': {exc}") from exc


def _minimum_node_separation(diagram: Diagram) -> float:
    """Pixels the two closest nodes need between them for the diagram's labels to fit.

    Derived from the longest label the diagram actually carries, because that is what
    varies between views: the STP view labels a link end "Gi1/0/23 designated/forwarding"
    where the L2 view says "Gi1/0/23", and a spacing that suits the second is unreadable
    for the first. The node icon's own width is the floor, for a diagram whose labels are
    all short.
    """
    longest_label = max(len(text) for text in _label_texts(diagram))
    return _NODE_WIDTH_PX + _LABEL_CLEARANCE * longest_label * _LABEL_CHARACTER_WIDTH_PX


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


def _link_style(color: str | None) -> str:
    """Return the draw.io style for a link, colored by `color` when there is one.

    Spells out `endArrow=none` even though it repeats N2G's own default: N2G *substitutes*
    its default for the style we pass rather than merging the two, so a colored link would
    otherwise lose it and pick up draw.io's built-in arrowhead. Links are undirected in
    every view -- the STP view orders an edge's ends by device name, so an arrow would
    point somewhere that means nothing.
    """
    style = "endArrow=none;"
    if color is not None:
        style += f"strokeColor={color};strokeWidth=2;"
    return style


def _link_data(link: DiagramLink) -> dict[str, str]:
    """Extra `<object>` attributes for the link.

    draw.io shows the `tooltip` attribute on hover instead of its default dump of every
    attribute, which is how a port-channel link reveals its member interfaces.
    """
    return {"tooltip": link.tooltip} if link.tooltip else {}
