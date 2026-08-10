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
from collections.abc import Iterable
from enum import Enum

from nettopo.model.entities import Link, NetworkModel
from nettopo.views.diagram import Diagram, DiagramLink, DiagramNode

_NETWORK_CAPABILITIES = {"Router", "Switch"}

_INTERFACE_SEPARATOR = ", "
_TOOLTIP_LINE_BREAK = "<br>"  # draw.io renders a link tooltip as (sanitized) HTML


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
    local = _port_channel_name(model, link.local_device, link.local_interface)
    remote = _port_channel_name(model, link.remote_device, link.remote_interface)
    if local is None and remote is None:
        return None

    ends = ((link.local_device, local or ""), (link.remote_device, remote or ""))
    return min(ends), max(ends)


def _bundle_link(ends: tuple[_BundleEnd, _BundleEnd], members: list[Link]) -> DiagramLink:
    (source, source_po), (target, target_po) = ends
    member_pairs = sorted(_oriented_interfaces(member, source) for member in members)

    return DiagramLink(
        source=source,
        target=target,
        src_label=source_po or _joined(pair[0] for pair in member_pairs),
        trgt_label=target_po or _joined(pair[1] for pair in member_pairs),
        tooltip=_TOOLTIP_LINE_BREAK.join(
            ["Members:", *(f"{local} — {remote}" for local, remote in member_pairs)]
        ),
    )


def _oriented_interfaces(link: Link, source: str) -> tuple[str, str]:
    """Return the link's (source-end, target-end) interfaces for a bundle drawn from `source`."""
    if link.local_device == source:
        return link.local_interface, link.remote_interface
    return link.remote_interface, link.local_interface


def _port_channel_name(model: NetworkModel, hostname: str, interface_name: str) -> str | None:
    """Return the port-channel `interface_name` belongs to (or is), if any.

    Only source devices have interfaces populated, so an adjacency to a device we hold no
    capture for is bundled by its near end alone.
    """
    interface = model.devices[hostname].interfaces.get(interface_name)
    if interface is None:
        return None
    if interface.po_id is not None:
        return f"Po{interface.po_id}"
    return interface.name if interface.po_members else None


def _joined(interface_names: Iterable[str]) -> str:
    """Join member interfaces for the end of a bundle that has no port-channel name."""
    return _INTERFACE_SEPARATOR.join(dict.fromkeys(interface_names))
