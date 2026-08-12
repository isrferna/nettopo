"""Per-VLAN HSRP view (PROJECT_SPEC.md section 7).

The STP view's sibling in shape -- same `--vlan`/`--all` selection, same
`VlanDiagramGroup` result -- but it draws a different kind of graph, because HSRP is not a
topology. `show standby brief` says which routers share a virtual IP and who is currently
active; it says nothing about which cable joins them, and the segment they share is a
broadcast domain rather than a set of point-to-point links. So this view does not go to
`model.links` at all (the STP view's whole difficulty). Each HSRP group is drawn as a
**virtual gateway node** -- the address hosts actually point at -- with one link to each
router that offers it, labeled with that router's SVI, role and priority. Every router
also carries its own SVI address under its name, so the diagram shows both halves of the
first hop: the address hosts are configured with, and the real addresses behind it. What
the reader needs from an HSRP diagram is which box answers for the gateway and which one
takes over, and that is exactly what a star around the virtual IP shows.

A diagram covers one VLAN and every HSRP group configured on it, since one SVI can carry
several groups (load-sharing across two gateways).

Unlike STP, this view offers no `--group-mode`: it always writes one diagram per VLAN.
Grouping means renders-identically, and two VLANs' HSRP never does -- each has its own
virtual IP and its own SVI address on every router, and the virtual IP is the headline
fact of the whole picture. Collapsing them would either drop every VLAN but one, or repeat
a stack of addresses per node until the star is unreadable. Whichever addresses are wanted
side by side, `hsrp.csv` lists them all.
"""

from __future__ import annotations

from collections import defaultdict

from nettopo.model.entities import DeviceRole, HsrpGroup, HsrpMember, HsrpRole, NetworkModel
from nettopo.views.diagram import (
    Diagram,
    DiagramLink,
    DiagramNode,
    LegendEntry,
    VlanDiagramGroup,
    vlan_diagram_filename,
)

_ACTIVE_COLOR = "#2E7D32"
_STANDBY_COLOR = "#EF6C00"

# The virtual gateway is not a device, so it deliberately takes no Cisco icon: `UNKNOWN`
# is what `render/icons.py` draws as a plain box, which is exactly the distinction the
# diagram needs to make between an address and the routers that answer for it.
_GATEWAY_ROLE = DeviceRole.UNKNOWN


def build_groups(model: NetworkModel, *, vlan: int | None = None) -> list[VlanDiagramGroup]:
    """Build one `Diagram` per VLAN, or just `vlan`'s when one is named.

    Every group covers exactly one VLAN: this view never collapses VLANs into a shared
    diagram (see the module docstring). The `VlanDiagramGroup` shape is kept all the same,
    so `cli.py` drives this view and the STP view through one code path.
    """
    groups_by_vlan = _groups_by_vlan(model)

    if vlan is not None:
        hsrp_groups = groups_by_vlan.get(vlan)
        if hsrp_groups is None:
            return []
        return [VlanDiagramGroup(vlan_ids=(vlan,), diagram=_build_diagram(model, hsrp_groups))]

    return [
        VlanDiagramGroup(vlan_ids=(vlan_id,), diagram=_build_diagram(model, hsrp_groups))
        for vlan_id, hsrp_groups in sorted(groups_by_vlan.items())
    ]


def hsrp_output_filename(vlan_ids: tuple[int, ...]) -> str:
    """Derive the `output/hsrp/` filename for a diagram covering `vlan_ids`."""
    return vlan_diagram_filename("hsrp", vlan_ids)


def _groups_by_vlan(model: NetworkModel) -> dict[int, list[HsrpGroup]]:
    """Every HSRP group in the model, collected under the VLAN whose SVI carries it."""
    by_vlan: dict[int, list[HsrpGroup]] = defaultdict(list)
    for (vlan_id, _group_id), hsrp_group in model.hsrp.items():
        by_vlan[vlan_id].append(hsrp_group)
    for hsrp_groups in by_vlan.values():
        hsrp_groups.sort(key=lambda hsrp_group: hsrp_group.group)
    return by_vlan


def _build_diagram(model: NetworkModel, hsrp_groups: list[HsrpGroup]) -> Diagram:
    diagram = Diagram()
    diagram.nodes = _build_nodes(model, hsrp_groups)
    diagram.links = _build_links(hsrp_groups)
    diagram.legend = _legend(diagram, hsrp_groups)
    return diagram


def _gateway_id(hsrp_group: HsrpGroup) -> str:
    """Node id for a group's virtual gateway.

    The colons keep it clear of the hostnames the member nodes are keyed by: a device name
    cannot contain one, so no capture can collide with a gateway node however it is named.
    """
    return f"hsrp:vlan{hsrp_group.vlan}:group{hsrp_group.group}"


def _build_nodes(model: NetworkModel, hsrp_groups: list[HsrpGroup]) -> list[DiagramNode]:
    """One node per virtual gateway, plus one per router that offers any of them."""
    nodes = [
        DiagramNode(
            id=_gateway_id(hsrp_group), label=_gateway_label(hsrp_group), role=_GATEWAY_ROLE
        )
        for hsrp_group in hsrp_groups
    ]

    members_by_device: dict[str, list[HsrpMember]] = defaultdict(list)
    for hsrp_group in hsrp_groups:
        for member in hsrp_group.members.values():
            members_by_device[member.device].append(member)

    nodes.extend(
        DiagramNode(
            id=hostname,
            label=_member_label(model, hostname, members[0].interface),
            role=_node_role(model, hostname),
            highlight=any(member.role is HsrpRole.ACTIVE for member in members),
        )
        for hostname, members in sorted(members_by_device.items())
    )
    return nodes


def _gateway_label(hsrp_group: HsrpGroup) -> str:
    """Name the gateway by the VLAN and group it serves, over its virtual address."""
    heading = f"VLAN {hsrp_group.vlan} group {hsrp_group.group}"
    if hsrp_group.virtual_ip is None:
        return heading
    return f"{heading}\n{hsrp_group.virtual_ip}"


def _member_label(model: NetworkModel, hostname: str, interface: str) -> str:
    """Name the router, over the address its own SVI holds in this VLAN.

    The real address beside the virtual one is what tells a reader which box a given
    traceroute hop or ping reply came from -- and it is the only address at all for a
    member that is neither active nor standby, since `show standby brief` names those two
    routers by address and no one else. It is read off `Device.interfaces`, populated by
    `show ip interface brief`/`show interfaces`, so a capture carrying neither leaves the
    node labeled with its name alone rather than inventing one.

    Any of the router's members will do for `interface`: a diagram covers one VLAN, so
    every group in it sits on that VLAN's single SVI.
    """
    device = model.devices.get(hostname)
    svi = device.interfaces.get(interface) if device is not None else None
    address = svi.ip_address if svi is not None else None
    return f"{hostname}\n{address}" if address else hostname


def _node_role(model: NetworkModel, hostname: str) -> DeviceRole:
    """An HSRP speaker routes, so it is a layer-3 switch unless we know something better."""
    device = model.devices.get(hostname)
    if device is None or device.role is DeviceRole.UNKNOWN:
        return DeviceRole.L3_SWITCH
    return device.role


def _build_links(hsrp_groups: list[HsrpGroup]) -> list[DiagramLink]:
    links = [
        DiagramLink(
            source=member.device,
            target=_gateway_id(hsrp_group),
            src_label=f"{member.interface} {member.role.value}/{member.priority}",
            color=_link_color(member.role),
        )
        for hsrp_group in hsrp_groups
        for member in sorted(hsrp_group.members.values(), key=lambda member: member.device)
    ]
    links.sort(key=lambda link: (link.target, link.source))
    return links


def _link_color(role: HsrpRole) -> str | None:
    if role is HsrpRole.ACTIVE:
        return _ACTIVE_COLOR
    if role is HsrpRole.STANDBY:
        return _STANDBY_COLOR
    return None


def _legend(diagram: Diagram, hsrp_groups: list[HsrpGroup]) -> list[LegendEntry]:
    """Explain the gateway node and the two roles the links are colored for.

    Each entry is listed only when the diagram uses it, so a group with no standby router
    -- or none currently active -- does not advertise a color that never appears.
    """
    entries: list[LegendEntry] = []
    if hsrp_groups:
        entries.append(LegendEntry(label="Virtual gateway", role=_GATEWAY_ROLE))

    active = next((node for node in diagram.nodes if node.highlight), None)
    if active is not None:
        entries.append(LegendEntry(label="Active router", role=active.role, highlight=True))

    colors = {link.color for link in diagram.links}
    if _ACTIVE_COLOR in colors:
        entries.append(LegendEntry(label="Active for this group", color=_ACTIVE_COLOR))
    if _STANDBY_COLOR in colors:
        entries.append(LegendEntry(label="Standby for this group", color=_STANDBY_COLOR))
    return entries
