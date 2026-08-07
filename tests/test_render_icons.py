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
