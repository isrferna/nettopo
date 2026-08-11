"""Tests for DeviceRole -> Cisco draw.io icon mapping (PROJECT_SPEC.md section 8)."""

from __future__ import annotations

import pytest

from nettopo.model.entities import DeviceRole
from nettopo.render.icons import MAX_NODE_WIDTH_PX, link_style, node_style

_ROLES_WITH_CISCO_ICONS = (
    DeviceRole.ROUTER,
    DeviceRole.L3_SWITCH,
    DeviceRole.SWITCH,
    DeviceRole.FIREWALL,
    DeviceRole.AP,
    DeviceRole.PHONE,
    DeviceRole.SERVER,
    DeviceRole.HOST,
)


@pytest.mark.parametrize("role", _ROLES_WITH_CISCO_ICONS)
def test_every_classified_role_gets_a_cisco_icon(role: DeviceRole) -> None:
    assert "shape=mxgraph.cisco19." in node_style(role).style


def test_unknown_role_falls_back_to_a_plain_box_not_a_cisco_icon() -> None:
    assert "shape=" not in node_style(DeviceRole.UNKNOWN).style


def test_roles_map_to_distinct_icons() -> None:
    styles = {role: node_style(role).style for role in _ROLES_WITH_CISCO_ICONS}
    assert len(set(styles.values())) == len(styles)


@pytest.mark.parametrize("role", _ROLES_WITH_CISCO_ICONS)
def test_every_icon_is_given_a_size(role: DeviceRole) -> None:
    """`aspect=fixed` distorts the drawing unless the geometry matches the icon's ratio."""
    style = node_style(role)
    assert style.width > 0
    assert style.height > 0
    assert "aspect=fixed" in style.style


def test_no_node_is_wider_than_the_advertised_maximum() -> None:
    """`render/drawio.py` spaces nodes by this, so an icon exceeding it would overlap."""
    widest = max(node_style(role).width for role in (*_ROLES_WITH_CISCO_ICONS, DeviceRole.UNKNOWN))
    assert widest == MAX_NODE_WIDTH_PX


def test_highlight_repaints_the_card_not_the_glyph() -> None:
    """On cisco19 shapes `strokeColor` draws the icon itself, so it must survive."""
    plain = node_style(DeviceRole.SWITCH)
    highlighted = node_style(DeviceRole.SWITCH, highlight=True)
    assert "fillColor=#FFF3C4;" in highlighted.style
    assert highlighted.style.startswith(plain.style)


def test_no_highlight_leaves_the_card_unpainted() -> None:
    assert "#FFF3C4" not in node_style(DeviceRole.SWITCH, highlight=False).style


def test_inferred_nodes_are_faded_rather_than_dashed() -> None:
    """A dashed border was invisible on these shapes; fading the node is what reads."""
    style = node_style(DeviceRole.SWITCH, inferred=True).style
    assert "opacity=40;" in style
    assert "dashed=1" not in style


def test_a_device_can_be_both_the_root_and_only_inferred() -> None:
    style = node_style(DeviceRole.SWITCH, highlight=True, inferred=True).style
    assert "fillColor=#FFF3C4;" in style
    assert "opacity=40;" in style
    # Bold from the base style, italic from the fade: draw.io's combined fontStyle.
    assert style.rstrip(";").endswith("fontStyle=3")


def test_captured_nodes_are_drawn_at_full_strength() -> None:
    assert "opacity=" not in node_style(DeviceRole.SWITCH).style


def test_an_uncolored_link_is_gray_rather_than_black() -> None:
    style = link_style(None)
    assert "strokeColor=#98A2B3;" in style
    assert "endArrow=none;" in style


def test_a_colored_link_keeps_its_color_and_loses_the_arrowhead() -> None:
    style = link_style("#C62828")
    assert "strokeColor=#C62828;" in style
    assert "endArrow=none;" in style
