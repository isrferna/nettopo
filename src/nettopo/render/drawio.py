"""Thin wrapper over N2G `drawio_diagram` (PROJECT_SPEC.md section 8).

The only module that imports N2G. If N2G is ever replaced, only this module changes --
`views/` and `model/` know nothing about N2G or draw.io concepts.
"""

from __future__ import annotations

from pathlib import Path

from N2G import drawio_diagram

from nettopo.render.icons import style_for_role
from nettopo.render.lucidify import lucidify_xml
from nettopo.views.diagram import Diagram

_DIAGRAM_ID = "diagram_1"


def render_diagram(diagram: Diagram, output_path: Path, *, apply_lucidify: bool = True) -> None:
    """Render `diagram` to a draw.io file at `output_path`.

    Applies the Lucidchart-friendliness post-process by default; pass
    `apply_lucidify=False` for the CLI's `--no-lucidify`.
    """
    drawing = drawio_diagram()
    drawing.add_diagram(_DIAGRAM_ID)

    for node in diagram.nodes:
        style = style_for_role(node.role, highlight=node.highlight)
        drawing.add_node(id=node.id, label=node.label, style=style)

    for link in diagram.links:
        drawing.add_link(
            source=link.source,
            target=link.target,
            label=link.label,
            src_label=link.src_label,
            trgt_label=link.trgt_label,
            style=_link_style(link.color),
        )

    # igraph-backed layout (PROJECT_SPEC.md section 8); without it nodes overlap.
    # igraph's "kk" layout raises on a graph with zero vertices, so skip it for an
    # empty diagram rather than letting that raise out of a routine "no data" case.
    if diagram.nodes:
        drawing.layout(algo="kk")

    xml_text = drawing.dump_xml()
    if apply_lucidify:
        xml_text = lucidify_xml(xml_text)

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(xml_text, encoding="utf-8")
    except OSError as exc:
        raise OSError(f"failed to write draw.io diagram '{output_path}': {exc}") from exc


def _link_style(color: str | None) -> str:
    """Return a draw.io style override for `color`, or "" to use N2G's default."""
    return f"strokeColor={color};strokeWidth=2;" if color is not None else ""
