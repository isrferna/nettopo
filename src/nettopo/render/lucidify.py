"""Post-process draw.io XML so each link's per-end labels survive (PROJECT_SPEC.md section 8).

N2G emits each link's per-end interface label (`src_label`/`trgt_label`) as an `<mxCell>`
parented to the link's own edge `<object>`, positioned along it by a relative geometry
(`x="-0.5"` near the source, `x="0.5"` near the target). That is the right construct, and
it is left in place: draw.io treats a vertex parented to an edge as *that edge's label*, so
it travels with the link when the link moves, and the Arrange layouts skip it instead of
scattering it across the canvas as a node in its own right. It also keeps the two ends
apart, which the STP view depends on -- each end carries its own role/state, and running
them together into one centered string says nothing about which switch is which.

What N2G gets wrong is the flag that declares the geometry relative. It writes
`relative="-1"` on the target-end label where the source-end label correctly gets
`relative="1"` (`N2G_DrawIO.py`, `drawio_link_label_xml`). draw.io reads that leniently --
it parses the attribute as a number, and any non-zero value is truthy -- but an importer
that tests for the literal `"1"` sees a label with no relative positioning at all and drops
it at the edge's origin. Normalizing the flag is what makes these labels portable, and is
the likeliest explanation for the mangling on Lucid import this module was written for.

It also cleans up the malformed (doubled) semicolons N2G's XML templates leave behind in
style strings, e.g. `drawio_link_label_xml` always appends `;` after `{style}` even when
the style already ends in one.

Applied by default to every generated diagram; `--no-lucidify` on the CLI skips it.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

_MALFORMED_STYLE = re.compile(r";{2,}")


def lucidify_xml(xml_text: str) -> str:
    """Return `xml_text` (a full N2G draw.io document) made Lucid-import-friendly."""
    root = ET.fromstring(xml_text)
    for diagram_root in root.iterfind("./diagram/mxGraphModel/root"):
        _normalize_end_labels(diagram_root)
    _clean_styles(root)
    return ET.tostring(root, encoding="unicode")


def _normalize_end_labels(diagram_root: ET.Element) -> None:
    """Declare every link end label's geometry relative in the way importers recognize."""
    link_ids = {
        link_id
        for link_object in diagram_root.findall("./object")
        if link_object.find("./mxCell[@edge='1']") is not None
        and (link_id := link_object.get("id")) is not None
    }

    for cell in diagram_root.findall("./mxCell"):
        if cell.get("parent") not in link_ids:
            continue
        geometry = cell.find("./mxGeometry")
        if geometry is not None:
            geometry.set("relative", "1")


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
