"""Per-VLAN STP view (PROJECT_SPEC.md section 7).

Switches only. Links come from `model.links`, the only place that records *which* devices
are neighbors -- `StpPort` records a device's own port role/state, never who is on the
other end. Two things follow from having to join those two sources:

- **A bundle has one logical port.** `show spanning-tree` reports a port-channel as `Po1`
  while CDP/LLDP report its physical members, so a member interface finds its `StpPort`
  only under the bundle's name, and the members collapse into a single drawn link.
- **Nodes are of two kinds.** A device we hold a capture for is drawn from its own
  `StpBridge` (MAC and priority, highlighted when it is the root). A device seen only in a
  neighbor's CDP/LLDP output is drawn faded and unlabeled beyond its name, because
  everything else about it would be inference. Such a device is included only through a
  non-Edge STP port: PortFast marks the ports facing hosts, and without that filter every
  phone and access point in the network would land in a spanning-tree diagram.

Honors `--group-mode`/`--vlan` (PROJECT_SPEC.md sections 6 and 9): grouping itself is
`model/grouping.py`'s concern (a property of the model), not this view's -- this module
only partitions VLANs by the fingerprints that module computes and picks one VLAN per
group to render, since grouped VLANs are guaranteed to produce the same diagram.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from nettopo.model.entities import (
    DeviceRole,
    Link,
    NetworkModel,
    StpPort,
    StpState,
    StpVlan,
)
from nettopo.model.grouping import GroupMode, stp_fingerprint
from nettopo.views.diagram import (
    Diagram,
    DiagramLink,
    DiagramNode,
    LegendEntry,
    join_interfaces,
    members_tooltip,
)

logger = logging.getLogger("nettopo")

_FORWARDING_COLOR = "#2E7D32"
_BLOCKING_COLOR = "#C62828"

# A broken port (PVID or type inconsistency) passes no traffic, so it reads as a blocked
# link rather than a forwarding one.
_BLOCKING_STATES = frozenset({StpState.BLK, StpState.BKN})


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


@dataclass(frozen=True)
class _LinkEnd:
    """One end of a discovered link, resolved onto the port STP knows it by."""

    device: str
    interface: str  # the physical interface CDP/LLDP reported
    stp_name: str  # the bundle this end belongs to, or `interface` when it has none
    port: StpPort | None
    is_bridge: bool  # this device has an `StpBridge` in the VLAN being drawn
    is_source: bool  # we hold this device's own capture, so its interfaces are known

    @property
    def is_bundled(self) -> bool:
        return self.stp_name != self.interface


@dataclass
class _StpEdge:
    """One drawn link, and every physical adjacency it stands for."""

    source: _LinkEnd
    target: _LinkEnd
    members: list[tuple[str, str]] = field(default_factory=list)

    def to_diagram_link(self) -> DiagramLink:
        member_pairs = sorted(self.members)
        # The tooltip earns its place only when the end labels no longer name the physical
        # ports themselves -- a plain one-interface link already shows them.
        collapsed = len(member_pairs) > 1 or self.source.is_bundled or self.target.is_bundled
        return DiagramLink(
            source=self.source.device,
            target=self.target.device,
            src_label=_end_label(self.source, (pair[0] for pair in member_pairs)),
            trgt_label=_end_label(self.target, (pair[1] for pair in member_pairs)),
            color=_link_color(self.source.port, self.target.port),
            tooltip=members_tooltip(member_pairs) if collapsed else "",
        )


def _build_diagram(model: NetworkModel, stp_vlan: StpVlan) -> Diagram:
    edges = _build_edges(model, stp_vlan)
    diagram = Diagram()
    diagram.nodes = _build_nodes(model, stp_vlan, edges)
    diagram.links = [edge.to_diagram_link() for edge in edges]
    diagram.links.sort(key=lambda link: (link.source, link.target, link.src_label))
    diagram.legend = _legend(diagram)
    return diagram


def _legend(diagram: Diagram) -> list[LegendEntry]:
    """Explain the four markings this view adds on top of the plain topology.

    Each is listed only when the diagram uses it, so a converged tree with nothing blocked
    does not advertise a red that never appears. The root bridge entry borrows whichever
    role the root itself was drawn with, so the sample is the icon the reader is looking
    for rather than a generic one.
    """
    entries: list[LegendEntry] = []
    root = next((node for node in diagram.nodes if node.highlight), None)
    if root is not None:
        entries.append(LegendEntry(label="Root bridge", role=root.role, highlight=True))

    inferred = next((node for node in diagram.nodes if node.inferred), None)
    if inferred is not None:
        entries.append(LegendEntry(label="No capture held", role=inferred.role, inferred=True))

    colors = {link.color for link in diagram.links}
    if _FORWARDING_COLOR in colors:
        entries.append(LegendEntry(label="Forwarding at both ends", color=_FORWARDING_COLOR))
    if _BLOCKING_COLOR in colors:
        entries.append(LegendEntry(label="Blocked at one end", color=_BLOCKING_COLOR))
    return entries


def _build_edges(model: NetworkModel, stp_vlan: StpVlan) -> list[_StpEdge]:
    """Collapse the discovered links into the ones this VLAN's spanning tree runs over."""
    edges: dict[frozenset[tuple[str, str]], _StpEdge] = {}
    for link in model.links:
        ends = _link_ends(model, stp_vlan, link)
        if ends is None:
            continue

        local, remote = ends
        key = frozenset(
            {
                (local.device, _grouping_name(local, remote)),
                (remote.device, _grouping_name(remote, local)),
            }
        )
        source, target = sorted(ends, key=lambda end: end.device)
        edge = edges.setdefault(key, _StpEdge(source=source, target=target))
        edge.members.append(link.oriented(source.device))
    return list(edges.values())


def _link_ends(
    model: NetworkModel, stp_vlan: StpVlan, link: Link
) -> tuple[_LinkEnd, _LinkEnd] | None:
    """Resolve both ends of `link`, or None if it does not belong in this VLAN's diagram."""
    local = _resolve_end(model, stp_vlan, link.local_device, link.local_interface)
    remote = _resolve_end(model, stp_vlan, link.remote_device, link.remote_interface)

    if local.is_bridge and remote.is_bridge:
        if local.port is None and remote.port is None:
            logger.debug(
                "VLAN %d: no STP port for %s or %s, dropping link %s %s -- %s %s",
                stp_vlan.vlan,
                (local.device, local.stp_name),
                (remote.device, remote.stp_name),
                local.device,
                local.interface,
                remote.device,
                remote.interface,
            )
            return None
        return local, remote

    if not local.is_bridge and not remote.is_bridge:
        return None

    # Only one end is in this VLAN's spanning tree, so the other is a device we hold no
    # capture for. Its near-end port is the only evidence it takes part at all, which is
    # why an unresolved port disqualifies it here but not between two known bridges.
    known, unknown = (local, remote) if local.is_bridge else (remote, local)
    if known.port is None:
        logger.debug(
            "VLAN %d: no STP port for %s, dropping link to uncaptured %s %s",
            stp_vlan.vlan,
            (known.device, known.stp_name),
            unknown.device,
            unknown.interface,
        )
        return None
    if known.port.is_edge:
        logger.debug(
            "VLAN %d: %s %s is an edge port (%s), excluding uncaptured %s",
            stp_vlan.vlan,
            known.device,
            known.stp_name,
            known.port.link_type,
            unknown.device,
        )
        return None
    return local, remote


def _resolve_end(model: NetworkModel, stp_vlan: StpVlan, device: str, interface: str) -> _LinkEnd:
    """Find the `StpPort` behind a link end, falling back to the bundle it belongs to.

    A port-channel member never appears in `show spanning-tree` under its own name, so a
    direct miss is retried under the bundle's name before the end is called portless.
    """
    port = stp_vlan.ports.get((device, interface))
    stp_name = interface
    if port is None:
        bundle = model.port_channel_name(device, interface)
        if bundle is not None:
            stp_name = bundle
            port = stp_vlan.ports.get((device, bundle))

    entry = model.devices.get(device)
    return _LinkEnd(
        device=device,
        interface=interface,
        stp_name=stp_name,
        port=port,
        is_bridge=device in stp_vlan.bridges,
        is_source=entry is not None and entry.is_source,
    )


def _grouping_name(end: _LinkEnd, other: _LinkEnd) -> str:
    """The name that decides which drawn link `end` belongs to."""
    if end.is_bundled:
        return end.stp_name
    if not end.is_source and other.is_bundled:
        # An EtherChannel cannot exist on one side only, so an end we hold no capture for
        # follows its bundled neighbor into a single link rather than splitting that
        # bundle into one drawn link per member.
        return ""
    return end.interface


def _end_label(end: _LinkEnd, member_interfaces: Iterable[str]) -> str:
    """Label one end of a drawn link: its port name, plus STP role/state when we know it."""
    name = end.stp_name if end.is_bundled else join_interfaces(member_interfaces)
    if end.port is None:
        return name
    return f"{name} {end.port.role.value}/{end.port.state.value}"


def _link_color(local_port: StpPort | None, remote_port: StpPort | None) -> str | None:
    states = [port.state for port in (local_port, remote_port) if port is not None]
    if any(state in _BLOCKING_STATES for state in states):
        return _BLOCKING_COLOR
    if any(state is StpState.FWD for state in states):
        return _FORWARDING_COLOR
    return None


def _build_nodes(
    model: NetworkModel, stp_vlan: StpVlan, edges: list[_StpEdge]
) -> list[DiagramNode]:
    """Draw every bridge in the VLAN, then every uncaptured device an edge reaches."""
    nodes = [
        DiagramNode(
            id=hostname,
            label=f"{hostname}\n{bridge.mac} / {bridge.effective_priority}",
            role=_node_role(model, hostname),
            highlight=bridge.is_root,
        )
        for hostname, bridge in sorted(stp_vlan.bridges.items())
    ]

    inferred = {
        end.device for edge in edges for end in (edge.source, edge.target) if not end.is_bridge
    }
    external_root = _external_root(model, stp_vlan, inferred)
    nodes.extend(
        DiagramNode(
            id=hostname,
            label=hostname,
            role=_node_role(model, hostname),
            highlight=hostname == external_root,
            inferred=True,
        )
        for hostname in sorted(inferred)
    )
    return nodes


def _node_role(model: NetworkModel, hostname: str) -> DeviceRole:
    """A device in a spanning tree is a switch unless CDP/LLDP said something better."""
    device = model.devices.get(hostname)
    if device is None or device.role is DeviceRole.UNKNOWN:
        return DeviceRole.SWITCH
    return device.role


def _external_root(model: NetworkModel, stp_vlan: StpVlan, inferred: set[str]) -> str | None:
    """Name the root bridge when it sits outside the captures, if LLDP lets us.

    Matching is on the exact chassis address LLDP advertises, so this either identifies the
    root or reports nothing -- it can never point at the wrong switch. CDP advertises no
    chassis address at all, so a neighbor seen only over CDP stays unidentifiable.
    """
    if stp_vlan.root_device is not None or not stp_vlan.root_mac:
        return None

    root_mac = stp_vlan.root_mac.casefold()
    for hostname in sorted(inferred):
        device = model.devices.get(hostname)
        if device is not None and device.chassis_id and device.chassis_id.casefold() == root_mac:
            return hostname

    logger.warning(
        "VLAN %d: the root bridge (%s) is not among the captured devices and no LLDP "
        "neighbor advertises that chassis address, so no node is highlighted as root.",
        stp_vlan.vlan,
        stp_vlan.root_mac,
    )
    return None
