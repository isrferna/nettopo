"""Draws a diagram's key into the finished draw.io XML (PROJECT_SPEC.md section 8).

Device samples are produced by calling `render/icons.py`'s `node_style` -- the same
function that styled the diagram itself -- and link samples are filled with the very color
the view handed its links, so the key cannot claim something the picture does not do. A
view says *what* deserves explaining (`Diagram.legend`); this module only decides where the
box goes and how big it is.

Legend cells are appended after the layout has been computed and scaled, and are written
as bare `<mxCell>` elements rather than N2G's `<object>` wrappers. Both facts keep them out
of `render/drawio.py`'s `_node_geometries()`, which selects `./object` elements and would
otherwise drag the legend around with the nodes.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element, SubElement

from nettopo.render.icons import node_style
from nettopo.views.diagram import LegendEntry

_TITLE = "Legend"

_PADDING = 14
_TITLE_HEIGHT = 22
_ROW_HEIGHT = 38
_SAMPLE_WIDTH = 52
_LABEL_WIDTH = 230
_SAMPLE_HEIGHT = 26

# Clear space between the legend's bottom edge and the topmost node.
_DIAGRAM_GAP = 60

_BOX_STYLE = (
    "rounded=1;arcSize=4;html=1;fillColor=#FFFFFF;strokeColor=#D5DAE0;"
    "verticalAlign=top;align=left;spacingLeft=8;"
)
_TITLE_STYLE = (
    "text;html=1;align=left;verticalAlign=middle;fontSize=13;fontStyle=1;fontColor=#2B3440;"
)
_LABEL_STYLE = "text;html=1;align=left;verticalAlign=middle;fontSize=11;fontColor=#5A6673;"
_LINE_SAMPLE_STYLE = "rounded=1;arcSize=50;html=1;"
_LINE_SAMPLE_WIDTH = 36
_LINE_SAMPLE_HEIGHT = 4


def add_legend(root: Element, entries: list[LegendEntry], bounds: tuple[float, float]) -> None:
    """Append a legend box to `root`, sitting above the laid-out diagram.

    `bounds` is the top-left corner of the nodes' bounding box; the legend is placed
    directly above it so it never lands on top of the topology, whatever shape the layout
    came out as.
    """
    if not entries:
        return

    width = _PADDING * 2 + _SAMPLE_WIDTH + _LABEL_WIDTH
    height = _PADDING * 2 + _TITLE_HEIGHT + _ROW_HEIGHT * len(entries)
    left, top = bounds[0], bounds[1] - height - _DIAGRAM_GAP

    _add_cell(root, "legend", "", _BOX_STYLE, left, top, width, height)
    _add_cell(
        root,
        "legend_title",
        _TITLE,
        _TITLE_STYLE,
        left + _PADDING,
        top + _PADDING,
        width - _PADDING * 2,
        _TITLE_HEIGHT,
    )

    row_top = top + _PADDING + _TITLE_HEIGHT
    for index, entry in enumerate(entries):
        _add_entry(root, index, entry, left + _PADDING, row_top + _ROW_HEIGHT * index)


def _add_entry(root: Element, index: int, entry: LegendEntry, left: float, top: float) -> None:
    _add_sample(root, index, entry, left, top)
    _add_cell(
        root,
        f"legend_label_{index}",
        entry.label,
        _LABEL_STYLE,
        left + _SAMPLE_WIDTH,
        top,
        _LABEL_WIDTH,
        _ROW_HEIGHT,
    )


def _add_sample(root: Element, index: int, entry: LegendEntry, left: float, top: float) -> None:
    """Draw the visual being explained, at a size that fits one legend row."""
    cell_id = f"legend_sample_{index}"
    if entry.role is not None:
        style = node_style(entry.role, highlight=entry.highlight, inferred=entry.inferred)
        # The icon keeps its own aspect ratio (`aspect=fixed` in the style would distort
        # it otherwise) and the label goes in the row's own text cell, not under the icon.
        scale = _SAMPLE_HEIGHT / style.height
        width = style.width * scale
        _add_cell(
            root,
            cell_id,
            "",
            f"{style.style}verticalLabelPosition=middle;",
            left + (_SAMPLE_WIDTH - width) / 2,
            top + (_ROW_HEIGHT - _SAMPLE_HEIGHT) / 2,
            width,
            _SAMPLE_HEIGHT,
        )
        return

    # A filled bar rather than an actual edge: a legend swatch is not a link, and drawing
    # it as one would make every consumer that counts the diagram's edges -- including our
    # own tests -- count the legend too.
    _add_cell(
        root,
        cell_id,
        "",
        f"{_LINE_SAMPLE_STYLE}fillColor={entry.color};strokeColor={entry.color};",
        left + (_SAMPLE_WIDTH - _LINE_SAMPLE_WIDTH) / 2,
        top + (_ROW_HEIGHT - _LINE_SAMPLE_HEIGHT) / 2,
        _LINE_SAMPLE_WIDTH,
        _LINE_SAMPLE_HEIGHT,
    )


def _add_cell(
    root: Element,
    cell_id: str,
    value: str,
    style: str,
    x_coord: float,
    y_coord: float,
    width: float,
    height: float,
) -> None:
    cell = SubElement(
        root,
        "mxCell",
        {"id": cell_id, "value": value, "style": style, "vertex": "1", "parent": "1"},
    )
    SubElement(
        cell,
        "mxGeometry",
        {
            "x": str(round(x_coord)),
            "y": str(round(y_coord)),
            "width": str(round(width)),
            "height": str(round(height)),
            "as": "geometry",
        },
    )
