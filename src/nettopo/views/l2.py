"""L2 physical/link-layer topology view (PROJECT_SPEC.md section 7).

Nodes are devices, links are `Link`s. `--endpoints network-only` drops any non-source
device unless a neighbor's CDP/LLDP reported it with Router or Switch capabilities --
a source device's own capture never lists its own capabilities, so source devices are
kept unconditionally rather than relying on capability data that will never exist for
them (see `ingest/model_builder.py`, which infers `Device.role` the same way).

Interface labels are attached to both ends of every link. `LinkMode` chooses what a
drawn link represents:

- `PHYSICAL` -- one link per discovered adjacency, labeled with the physical interface
  at each end.
- `PORT_CHANNEL` -- adjacencies whose interface is a port-channel member (or the
  port-channel itself) collapse into one link per bundle, labeled `Po150` at the ends
  that have a bundle, with the member interfaces carried in the link's tooltip. Links
  with no port-channel on either end are drawn exactly as in `PHYSICAL` mode, so a
  network with no bundles renders identically under both modes.

A bundle is keyed on the *device pair*, not on the direction the adjacency happens to be
stored in: `ingest/model_builder.py` keeps one direction per physical link, and which
direction that is depends on which device's capture reported it. Two members of one
bundle reported from opposite ends would otherwise become two separate bundles. The
drawn link's source/target therefore follow device-name order rather than the members'
own direction.
"""

from __future__ import annotations

from collections import defaultdict
from enum import Enum

from nettopo.model.entities import DeviceRole, Link, NetworkModel
from nettopo.views.diagram import (
    Diagram,
    DiagramLink,
    DiagramNode,
    LegendEntry,
    join_interfaces,
    members_tooltip,
)

# CDP word forms and the IEEE 802.1AB letter codes; `_ROLE_BY_CAPABILITY` in
# `ingest/model_builder.py` is the shared vocabulary.
_NETWORK_CAPABILITIES = {"Router", "Switch", "R", "B"}

# Insertion order is the order the legend lists them: network gear from the core outward,
# then the endpoints.
_ROLE_LABELS: dict[DeviceRole, str] = {
    DeviceRole.ROUTER: "Router",
    DeviceRole.L3_SWITCH: "Layer 3 switch",
    DeviceRole.SWITCH: "Switch",
    DeviceRole.FIREWALL: "Firewall",
    DeviceRole.AP: "Access point",
    DeviceRole.SERVER: "Server",
    DeviceRole.HOST: "Host",
    DeviceRole.PHONE: "IP phone",
    DeviceRole.UNKNOWN: "Unidentified device",
}


class LinkMode(Enum):
    PHYSICAL = "physical"
    PORT_CHANNEL = "port-channel"


# One end of a bundled link: the device, and its port-channel name ("" when that end has
# no bundle, which keeps every member of a one-sided bundle under the same key).
_BundleEnd = tuple[str, str]


def build(
    model: NetworkModel,
    *,
    endpoints: str = "all",
    link_mode: LinkMode = LinkMode.PHYSICAL,
) -> Diagram:
    """Build the L2 topology diagram.

    `endpoints` is `"all"` (every device, full diagram) or `"network-only"`
    (routers/switches only). `link_mode` selects physical links or port-channel bundles.
    """
    included = _included_devices(model, endpoints=endpoints)
    links = [
        link
        for link in model.links
        if link.local_device in included and link.remote_device in included
    ]

    diagram = Diagram()
    for hostname in sorted(included):
        device = model.devices[hostname]
        diagram.nodes.append(DiagramNode(id=hostname, label=hostname, role=device.role))
    diagram.links = _diagram_links(model, links, link_mode)
    diagram.legend = _legend(diagram)
    return diagram


def _legend(diagram: Diagram) -> list[LegendEntry]:
    """Name every device role the diagram actually drew, in a stable order.

    Only roles present are listed: a key that explains icons the reader cannot see is
    noise, and the L2 view's whole point is which kinds of device are out there.
    """
    present = {node.role for node in diagram.nodes}
    return [
        LegendEntry(label=_ROLE_LABELS[role], role=role) for role in _ROLE_LABELS if role in present
    ]


def _included_devices(model: NetworkModel, *, endpoints: str) -> set[str]:
    if endpoints == "all":
        return set(model.devices)

    network_remotes = {
        link.remote_device
        for link in model.links
        if _NETWORK_CAPABILITIES & set(link.remote_capabilities)
    }
    return {
        hostname
        for hostname, device in model.devices.items()
        if device.is_source or hostname in network_remotes
    }


def _diagram_links(
    model: NetworkModel, links: list[Link], link_mode: LinkMode
) -> list[DiagramLink]:
    singles: list[Link] = []
    bundles: dict[tuple[_BundleEnd, _BundleEnd], list[Link]] = defaultdict(list)

    for link in links:
        ends = _bundle_ends(model, link) if link_mode is LinkMode.PORT_CHANNEL else None
        if ends is None:
            singles.append(link)
        else:
            bundles[ends].append(link)

    diagram_links = [_physical_link(link) for link in singles]
    diagram_links.extend(_bundle_link(ends, members) for ends, members in bundles.items())
    diagram_links.sort(key=lambda link: (link.source, link.target, link.src_label))
    return diagram_links


def _physical_link(link: Link) -> DiagramLink:
    return DiagramLink(
        source=link.local_device,
        target=link.remote_device,
        src_label=link.local_interface,
        trgt_label=link.remote_interface,
    )


def _bundle_ends(model: NetworkModel, link: Link) -> tuple[_BundleEnd, _BundleEnd] | None:
    """Return the link's two ends in device-name order, or None if no end is bundled."""
    local = model.port_channel_name(link.local_device, link.local_interface)
    remote = model.port_channel_name(link.remote_device, link.remote_interface)
    if local is None and remote is None:
        return None

    ends = ((link.local_device, local or ""), (link.remote_device, remote or ""))
    return min(ends), max(ends)


def _bundle_link(ends: tuple[_BundleEnd, _BundleEnd], members: list[Link]) -> DiagramLink:
    (source, source_po), (target, target_po) = ends
    member_pairs = sorted(member.oriented(source) for member in members)

    return DiagramLink(
        source=source,
        target=target,
        src_label=source_po or join_interfaces(pair[0] for pair in member_pairs),
        trgt_label=target_po or join_interfaces(pair[1] for pair in member_pairs),
        tooltip=members_tooltip(member_pairs),
    )
