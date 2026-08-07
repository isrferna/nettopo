"""Per-VLAN STP view (PROJECT_SPEC.md section 7).

Switches only. Nodes are the devices with a bridge in a given `StpVlan`; the root bridge
is highlighted. Links are the physical connections between two of those devices (from
`model.links`, the only place that records *which* devices are neighbors -- `StpPort`
only records a device's own port role/state, not who is on the other end), labeled with
role/state at each end and colored by whether either end is forwarding or blocking.

Honors `--group-mode`/`--vlan` (PROJECT_SPEC.md sections 6 and 9): grouping itself is
`model/grouping.py`'s concern (a property of the model), not this view's -- this module
only partitions VLANs by the fingerprints that module computes and picks one VLAN per
group to render, since grouped VLANs are guaranteed to produce the same diagram.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from nettopo.model.entities import DeviceRole, NetworkModel, StpPort, StpState, StpVlan
from nettopo.model.grouping import GroupMode, stp_fingerprint
from nettopo.views.diagram import Diagram, DiagramLink, DiagramNode

_FORWARDING_COLOR = "#2E7D32"
_BLOCKING_COLOR = "#C62828"


@dataclass
class StpDiagramGroup:
    vlan_ids: tuple[int, ...]  # sorted ascending; every VLAN this rendered diagram covers
    diagram: Diagram


def build_groups(
    model: NetworkModel, *, group_mode: GroupMode = GroupMode.PER_VLAN, vlan: int | None = None
) -> list[StpDiagramGroup]:
    """Build one `Diagram` per VLAN, or per topology group under `group_mode`.

    `vlan` restricts output to a single VLAN's diagram, ignoring `group_mode` (the CLI
    enforces these as mutually exclusive -- PROJECT_SPEC.md section 9).
    """
    if vlan is not None:
        stp_vlan = model.stp.get(vlan)
        if stp_vlan is None:
            return []
        return [StpDiagramGroup(vlan_ids=(vlan,), diagram=_build_diagram(model, stp_vlan))]

    members_by_fingerprint: dict[tuple[object, ...], list[StpVlan]] = defaultdict(list)
    for stp_vlan in model.stp.values():
        members_by_fingerprint[stp_fingerprint(stp_vlan, group_mode)].append(stp_vlan)

    groups: list[StpDiagramGroup] = []
    for members in members_by_fingerprint.values():
        members.sort(key=lambda stp_vlan: stp_vlan.vlan)
        vlan_ids = tuple(member.vlan for member in members)
        groups.append(StpDiagramGroup(vlan_ids=vlan_ids, diagram=_build_diagram(model, members[0])))
    groups.sort(key=lambda group: group.vlan_ids)
    return groups


def stp_output_filename(vlan_ids: tuple[int, ...]) -> str:
    """Derive the `output/stp/` filename for a diagram covering `vlan_ids`.

    `vlan_ids` are ints from the parsed model, not user/path input, so no additional
    sanitization is needed beyond the deterministic, sorted, filesystem-safe format
    PROJECT_SPEC.md section 6 specifies.
    """
    if len(vlan_ids) == 1:
        return f"stp_vlan{vlan_ids[0]}.drawio"
    return f"stp_vlans-{'_'.join(str(vlan_id) for vlan_id in vlan_ids)}.drawio"


def _build_diagram(model: NetworkModel, stp_vlan: StpVlan) -> Diagram:
    diagram = Diagram()
    for hostname in sorted(stp_vlan.bridges):
        bridge = stp_vlan.bridges[hostname]
        device = model.devices.get(hostname)
        role = (
            device.role
            if device is not None and device.role is not DeviceRole.UNKNOWN
            else DeviceRole.SWITCH
        )
        diagram.nodes.append(
            DiagramNode(
                id=hostname,
                label=f"{hostname}\n{bridge.mac} / {bridge.effective_priority}",
                role=role,
                highlight=bridge.is_root,
            )
        )

    included = set(stp_vlan.bridges)
    for link in model.links:
        if link.local_device not in included or link.remote_device not in included:
            continue

        local_port = stp_vlan.ports.get((link.local_device, link.local_interface))
        remote_port = stp_vlan.ports.get((link.remote_device, link.remote_interface))
        if local_port is None and remote_port is None:
            continue

        diagram.links.append(
            DiagramLink(
                source=link.local_device,
                target=link.remote_device,
                src_label=_port_label(link.local_interface, local_port),
                trgt_label=_port_label(link.remote_interface, remote_port),
                color=_link_color(local_port, remote_port),
            )
        )

    diagram.links.sort(key=lambda diagram_link: (diagram_link.source, diagram_link.target))
    return diagram


def _port_label(interface: str, port: StpPort | None) -> str:
    if port is None:
        return interface
    return f"{interface} {port.role.value}/{port.state.value}"


def _link_color(local_port: StpPort | None, remote_port: StpPort | None) -> str | None:
    states = [port.state for port in (local_port, remote_port) if port is not None]
    if any(state is StpState.BLK for state in states):
        return _BLOCKING_COLOR
    if any(state is StpState.FWD for state in states):
        return _FORWARDING_COLOR
    return None
