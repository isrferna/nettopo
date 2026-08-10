"""Tests for DeviceRole -> Cisco draw.io shape mapping (PROJECT_SPEC.md section 8)."""

from __future__ import annotations

import pytest

from nettopo.model.entities import DeviceRole
from nettopo.render.icons import style_for_role

_ROLES_WITH_CISCO_SHAPES = (
    DeviceRole.ROUTER,
    DeviceRole.L3_SWITCH,
    DeviceRole.SWITCH,
    DeviceRole.FIREWALL,
    DeviceRole.AP,
    DeviceRole.PHONE,
    DeviceRole.SERVER,
    DeviceRole.HOST,
)


@pytest.mark.parametrize("role", _ROLES_WITH_CISCO_SHAPES)
def test_every_classified_role_gets_a_cisco_stencil_shape(role: DeviceRole) -> None:
    style = style_for_role(role)
    assert "shape=mxgraph.cisco." in style


def test_unknown_role_falls_back_to_a_plain_box_not_a_cisco_shape() -> None:
    style = style_for_role(DeviceRole.UNKNOWN)
    assert "shape=" not in style


def test_roles_map_to_distinct_shapes() -> None:
    shapes = {role: style_for_role(role) for role in _ROLES_WITH_CISCO_SHAPES}
    assert len(set(shapes.values())) == len(shapes)


def test_highlight_overrides_the_stroke_color() -> None:
    style = style_for_role(DeviceRole.SWITCH, highlight=True)
    assert style.rstrip(";").split(";")[-1] == "strokeWidth=4"


def test_no_highlight_keeps_the_default_stroke_color() -> None:
    style = style_for_role(DeviceRole.SWITCH, highlight=False)
    assert "#FFD700" not in style


def test_inferred_nodes_are_dashed() -> None:
    style = style_for_role(DeviceRole.SWITCH, inferred=True)
    assert style.rstrip(";").split(";")[-1] == "dashPattern=8 8"
    assert "dashed=1" in style


def test_a_device_can_be_both_the_root_and_only_inferred() -> None:
    style = style_for_role(DeviceRole.SWITCH, highlight=True, inferred=True)
    assert "strokeWidth=4" in style
    assert "dashed=1" in style


def test_captured_nodes_keep_a_solid_border() -> None:
    assert "dashed=1" not in style_for_role(DeviceRole.SWITCH)
