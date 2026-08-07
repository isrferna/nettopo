"""DeviceRole -> Cisco draw.io shape mapping (PROJECT_SPEC.md section 8).

Shape paths are draw.io's classic Cisco stencil set (`mxgraph.cisco.*`), verified
against jgraph/drawio's `Sidebar-Cisco.js` rather than guessed: a wrong stencil path
renders as an invisible/blank shape instead of falling back to a box, so accuracy here
matters more than it would for a typo elsewhere.
"""

from __future__ import annotations

from nettopo.model.entities import DeviceRole

_STYLE_SUFFIX = (
    "sketch=0;html=1;pointerEvents=1;dashed=0;fillColor=#036897;strokeColor=#ffffff;"
    "strokeWidth=2;verticalLabelPosition=bottom;verticalAlign=top;align=center;"
    "outlineConnect=0;"
)

_SHAPE_BY_ROLE: dict[DeviceRole, str] = {
    DeviceRole.ROUTER: "mxgraph.cisco.routers.router",
    DeviceRole.L3_SWITCH: "mxgraph.cisco.switches.layer_3_switch",
    DeviceRole.SWITCH: "mxgraph.cisco.switches.workgroup_switch",
    DeviceRole.FIREWALL: "mxgraph.cisco.security.firewall",
    DeviceRole.AP: "mxgraph.cisco.misc.access_point",
    DeviceRole.PHONE: "mxgraph.cisco.modems_and_phones.ip_phone",
    DeviceRole.SERVER: "mxgraph.cisco.servers.standard_host",
    DeviceRole.HOST: "mxgraph.cisco.computers_and_peripherals.pc",
}

# DeviceRole.UNKNOWN (and any future role without a mapping) falls back to a plain box
# rather than a Cisco stencil -- there is no meaningful "unknown device" Cisco icon.
_DEFAULT_STYLE = "rounded=1;whiteSpace=wrap;html=1;"


def style_for_role(role: DeviceRole) -> str:
    """Return the draw.io node style string for `role`."""
    shape = _SHAPE_BY_ROLE.get(role)
    if shape is None:
        return _DEFAULT_STYLE
    return f"shape={shape};{_STYLE_SUFFIX}"
