"""L2 physical/link-layer topology view (PROJECT_SPEC.md section 7).

Nodes are devices, links are `Link`s. `--endpoints network-only` drops any non-source
device unless a neighbor's CDP/LLDP reported it with Router or Switch capabilities --
a source device's own capture never lists its own capabilities, so source devices are
kept unconditionally rather than relying on capability data that will never exist for
them (see `ingest/model_builder.py`, which infers `Device.role` the same way).

Interface labels are attached to both ends of every link. Physical links whose local
interface is a port-channel member (`Interface.po_id` is set) are grouped into a single
rendered link per port-channel, imitating current N2G behavior for MLAG. No shipped
parser populates `po_id` yet (no phase parses `show etherchannel summary`), so this
grouping is data-ready but a no-op against today's real captures -- see
`docs/architecture.md`.
"""

from __future__ import annotations

from collections import defaultdict

from nettopo.model.entities import Link, NetworkModel
from nettopo.views.diagram import Diagram, DiagramLink, DiagramNode

_NETWORK_CAPABILITIES = {"Router", "Switch"}


def build(model: NetworkModel, *, endpoints: str = "all") -> Diagram:
    """Build the L2 topology diagram.

    `endpoints` is `"all"` (every device, full diagram) or `"network-only"`
    (routers/switches only).
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
    diagram.links = _group_links(model, links)
    return diagram


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


def _group_links(model: NetworkModel, links: list[Link]) -> list[DiagramLink]:
    singles: list[Link] = []
    port_channels: dict[tuple[str, str, int], list[Link]] = defaultdict(list)

    for link in links:
        po_id = _local_po_id(model, link)
        if po_id is None:
            singles.append(link)
        else:
            port_channels[(link.local_device, link.remote_device, po_id)].append(link)

    diagram_links = [
        DiagramLink(
            source=link.local_device,
            target=link.remote_device,
            src_label=link.local_interface,
            trgt_label=link.remote_interface,
        )
        for link in singles
    ]
    for (local_device, remote_device, po_id), members in port_channels.items():
        diagram_links.append(
            DiagramLink(
                source=local_device,
                target=remote_device,
                src_label=f"Po{po_id}",
                trgt_label=", ".join(sorted(member.remote_interface for member in members)),
            )
        )

    diagram_links.sort(key=lambda link: (link.source, link.target, link.src_label))
    return diagram_links


def _local_po_id(model: NetworkModel, link: Link) -> int | None:
    device = model.devices.get(link.local_device)
    if device is None:
        return None
    interface = device.interfaces.get(link.local_interface)
    if interface is None:
        return None
    return interface.po_id
