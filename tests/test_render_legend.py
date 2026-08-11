"""Tests for the diagram legend (PROJECT_SPEC.md section 8)."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from nettopo.model.entities import DeviceRole
from nettopo.render.icons import node_style
from nettopo.render.legend import add_legend
from nettopo.views.diagram import LegendEntry


def _root(entries: list[LegendEntry]) -> ET.Element:
    root = ET.Element("root")
    add_legend(root, entries, (0.0, 0.0))
    return root


def _cell(root: ET.Element, cell_id: str) -> ET.Element:
    cell = root.find(f"./mxCell[@id='{cell_id}']")
    assert cell is not None
    return cell


def test_no_entries_draws_nothing_at_all() -> None:
    assert len(_root([])) == 0


def test_each_entry_gets_a_sample_and_its_label() -> None:
    root = _root(
        [
            LegendEntry(label="Router", role=DeviceRole.ROUTER),
            LegendEntry(label="Blocked at one end", color="#C62828"),
        ]
    )

    assert _cell(root, "legend_label_0").get("value") == "Router"
    assert _cell(root, "legend_label_1").get("value") == "Blocked at one end"
    assert _cell(root, "legend_sample_0") is not None
    assert _cell(root, "legend_sample_1") is not None


def test_a_device_sample_reuses_the_style_the_diagram_drew_that_role_with() -> None:
    """The key is generated from the same function as the picture, so it cannot drift."""
    root = _root([LegendEntry(label="Layer 3 switch", role=DeviceRole.L3_SWITCH)])

    style = _cell(root, "legend_sample_0").get("style", "")
    assert node_style(DeviceRole.L3_SWITCH).style in style


def test_a_device_sample_keeps_its_icons_aspect_ratio() -> None:
    """Every cisco19 style carries `aspect=fixed`; a square geometry would distort them."""
    root = _root([LegendEntry(label="Server", role=DeviceRole.SERVER)])

    geometry = _cell(root, "legend_sample_0").find("./mxGeometry")
    assert geometry is not None
    icon = node_style(DeviceRole.SERVER)
    drawn_ratio = float(geometry.get("width", 0)) / float(geometry.get("height", 1))
    assert abs(drawn_ratio - icon.width / icon.height) < 0.05


def test_a_root_bridge_sample_carries_the_highlight() -> None:
    root = _root([LegendEntry(label="Root bridge", role=DeviceRole.SWITCH, highlight=True)])
    assert "fillColor=#FFF3C4;" in _cell(root, "legend_sample_0").get("style", "")


def test_an_inferred_sample_carries_the_fade() -> None:
    root = _root([LegendEntry(label="No capture held", role=DeviceRole.SWITCH, inferred=True)])
    assert "opacity=40;" in _cell(root, "legend_sample_0").get("style", "")


def test_a_link_sample_is_filled_with_the_links_own_color() -> None:
    root = _root([LegendEntry(label="Forwarding at both ends", color="#2E7D32")])
    assert "fillColor=#2E7D32;" in _cell(root, "legend_sample_0").get("style", "")


def test_a_link_sample_is_not_an_edge() -> None:
    """Drawn as a bar, so anything counting the diagram's links does not count the key."""
    root = _root([LegendEntry(label="Forwarding at both ends", color="#2E7D32")])
    assert root.find(".//mxCell[@edge='1']") is None


def test_the_box_is_tall_enough_for_every_row() -> None:
    entries = [LegendEntry(label=f"Row {index}", color="#2E7D32") for index in range(4)]
    root = _root(entries)

    box = _cell(root, "legend").find("./mxGeometry")
    assert box is not None
    last_row = _cell(root, "legend_label_3").find("./mxGeometry")
    assert last_row is not None
    box_bottom = float(box.get("y", 0)) + float(box.get("height", 0))
    row_bottom = float(last_row.get("y", 0)) + float(last_row.get("height", 0))
    assert row_bottom <= box_bottom


def test_the_box_sits_above_the_diagram_it_explains() -> None:
    root = ET.Element("root")
    add_legend(root, [LegendEntry(label="Router", role=DeviceRole.ROUTER)], (400.0, 900.0))

    box = _cell(root, "legend").find("./mxGeometry")
    assert box is not None
    assert float(box.get("y", 0)) + float(box.get("height", 0)) < 900.0
