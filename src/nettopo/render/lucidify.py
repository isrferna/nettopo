"""Post-process draw.io XML for Lucidchart import fidelity (PROJECT_SPEC.md section 8).

N2G emits each link's per-end interface label (`src_label`/`trgt_label`) as a separate
`<mxCell>` vertex with geometry relative to the link's own `<object>` cell (`x="-0.5"`
near the source, `x="0.5"` near the target). Lucid's draw.io importer does not handle
that relative-geometry child-of-an-edge pattern and mangles or drops these labels.

This collapses each link's src/trgt label cells into a single label on the link's own
`<object label="...">` attribute -- an attribute Lucid imports correctly -- and removes
the now-redundant child cells. It also cleans up the malformed (doubled) semicolons
N2G's XML templates leave behind in style strings, e.g. `drawio_link_label_xml` always
appends `;` after `{style}` even when the style already ends in one.

Applied by default to every generated diagram; `--no-lucidify` on the CLI skips it.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import defaultdict

_MALFORMED_STYLE = re.compile(r";{2,}")


def lucidify_xml(xml_text: str) -> str:
    """Return `xml_text` (a full N2G draw.io document) made Lucid-import-friendly."""
    root = ET.fromstring(xml_text)
    for diagram_root in root.iterfind("./diagram/mxGraphModel/root"):
        _collapse_link_labels(diagram_root)
    _clean_styles(root)
    return ET.tostring(root, encoding="unicode")


def _collapse_link_labels(diagram_root: ET.Element) -> None:
    link_objects: dict[str, ET.Element] = {
        link_id: link_object
        for link_object in diagram_root.findall("./object")
        if link_object.find("./mxCell[@edge='1']") is not None
        and (link_id := link_object.get("id")) is not None
    }

    label_cells_by_link: dict[str, list[ET.Element]] = defaultdict(list)
    for cell in diagram_root.findall("./mxCell"):
        parent_id = cell.get("parent")
        if parent_id is not None and parent_id in link_objects:
            label_cells_by_link[parent_id].append(cell)

    for link_id, label_cells in label_cells_by_link.items():
        # N2G places the source-end label at x=-0.5 and the target-end label at
        # x=0.5 along the edge; sorting on that puts the combined label in
        # source -> target order regardless of which one N2G added first.
        label_cells.sort(key=lambda cell: _geometry_x(cell))
        combined = " — ".join(cell.get("value", "") for cell in label_cells if cell.get("value"))
        if combined:
            link_object = link_objects[link_id]
            existing = link_object.get("label", "")
            link_object.set("label", f"{existing} {combined}".strip() if existing else combined)
        for cell in label_cells:
            diagram_root.remove(cell)


def _geometry_x(cell: ET.Element) -> float:
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
