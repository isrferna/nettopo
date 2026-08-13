"""BGP neighbor session graph (PROJECT_SPEC.md section 7).

One diagram for the whole network, not one per anything: BGP sessions do not partition
into VLANs the way STP and HSRP do. Nodes are routers labeled with their AS number, links
are sessions labeled with their state, and iBGP and eBGP are drawn in different colors --
which AS boundary a session crosses is the first thing a reader looks for, and the state
is what they check next.

**Peers are matched by address at drawing time.** `show ip bgp summary` names the far end
of a session by IP only, and `BgpPeer.peer_device` stays `None` in v1 (section 2). Drawn
literally, two captured routers peering with each other would become four nodes -- each
one plus a nameless box for the other -- which is not a picture of the network. So this
view looks each peer IP up in the interface addresses the model already holds, and when it
belongs to a device we captured, the two reports collapse into one link between the two
routers. The match lives here rather than in the model: it decides how a session is
*drawn*, it never fills in `peer_device`, and `bgp.csv` still reports exactly what the
device said. A peer that matches nothing keeps a node of its own, labeled with the address
and AS the session named it by and faded like any other device we hold no capture for.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping

from nettopo.model.entities import BgpPeer, BgpType, DeviceRole, NetworkModel
from nettopo.views.diagram import Diagram, DiagramLink, DiagramNode, LegendEntry

_IBGP_COLOR = "#1565C0"
_EBGP_COLOR = "#6A1B9A"

_COLOR_BY_TYPE: dict[BgpType, str] = {
    BgpType.IBGP: _IBGP_COLOR,
    BgpType.EBGP: _EBGP_COLOR,
}

# A peer we hold no capture for is not a device we know anything about, so it takes no
# Cisco icon: `UNKNOWN` is what `render/icons.py` draws as a plain box.
_PEER_ROLE = DeviceRole.UNKNOWN

_STATE_SEPARATOR = " / "

# One session, keyed so that both ends report it under the same key: the VRF, then the two
# endpoint ids in name order.
_SessionKey = tuple[str, str, str]


def build(model: NetworkModel) -> Diagram:
    """Build the BGP session graph for every peering in the model."""
    hostname_by_ip = _hostname_by_ip(model)

    sessions: dict[_SessionKey, list[BgpPeer]] = defaultdict(list)
    unresolved_peers: dict[str, BgpPeer] = {}
    for peer in model.bgp:
        endpoint = _endpoint_id(peer, hostname_by_ip)
        if endpoint not in model.devices:
            unresolved_peers.setdefault(endpoint, peer)
        source, target = _session_ends(peer.local_device, endpoint, model)
        sessions[(peer.vrf, source, target)].append(peer)

    diagram = Diagram()
    diagram.links = _build_links(sessions)
    diagram.nodes = _build_nodes(model, sessions, unresolved_peers)
    diagram.legend = _legend(diagram)
    return diagram


def _hostname_by_ip(model: NetworkModel) -> dict[str, str]:
    """Index every interface address in the model by the device that holds it.

    Built in hostname order so that two devices reporting the same address -- a capture
    set with a duplicate, or a shared virtual address -- always resolve the same way
    rather than by dictionary insertion accident.
    """
    hostname_by_ip: dict[str, str] = {}
    for hostname, device in sorted(model.devices.items()):
        for interface in device.interfaces.values():
            if interface.ip_address:
                hostname_by_ip.setdefault(interface.ip_address, hostname)
    return hostname_by_ip


def _endpoint_id(peer: BgpPeer, hostname_by_ip: Mapping[str, str]) -> str:
    """Node id for the far end of `peer`: its hostname if we captured it, else its address.

    The colons keep a peer node clear of the hostnames devices are keyed by, the same way
    the HSRP view namespaces its virtual gateways.
    """
    hostname = hostname_by_ip.get(peer.peer_ip)
    # An address that resolves back to the router reporting it is not a session with
    # itself, so it stays an unresolved peer rather than becoming a self-loop.
    if hostname is not None and hostname != peer.local_device:
        return hostname
    return f"bgp:peer:{peer.peer_ip}"


def _session_ends(local_device: str, endpoint: str, model: NetworkModel) -> tuple[str, str]:
    """Order a session's two ends: captured routers first, then by name.

    Links are undirected, so this is about how the session reads rather than which way it
    points -- a session with an uncaptured peer reads outward from the router that
    reported it, instead of being led by a `bgp:peer:` id that only sorts first by
    accident. Both ends of a session between two captured routers still order identically
    whichever of them reported it, which is what lets the two reports collapse into one.
    """
    ends = sorted((local_device, endpoint), key=lambda end: (end not in model.devices, end))
    return ends[0], ends[1]


def _build_links(sessions: Mapping[_SessionKey, list[BgpPeer]]) -> list[DiagramLink]:
    links = [
        DiagramLink(
            source=source,
            target=target,
            label=_state_label(peers),
            color=_COLOR_BY_TYPE[peers[0].type],
        )
        for (_vrf, source, target), peers in sessions.items()
    ]
    links.sort(key=lambda link: (link.source, link.target))
    return links


def _state_label(peers: list[BgpPeer]) -> str:
    """Name the session's state, reporting both when its two ends disagree.

    When we hold captures for both routers, each reports the session from its own side,
    and the two need not match -- one end can still be `Active` while the other has moved
    on. Showing both, in device-name order, is the honest reading; picking one would hide
    exactly the case a reader is looking for.
    """
    states = {peer.local_device: peer.state for peer in peers}
    ordered = list(dict.fromkeys(states[device] for device in sorted(states)))
    return _STATE_SEPARATOR.join(ordered)


def _build_nodes(
    model: NetworkModel,
    sessions: Mapping[_SessionKey, list[BgpPeer]],
    unresolved_peers: Mapping[str, BgpPeer],
) -> list[DiagramNode]:
    """One node per router in a session, plus one per peer we hold no capture for."""
    endpoints = {endpoint for (_vrf, source, target) in sessions for endpoint in (source, target)}

    nodes = [
        DiagramNode(
            id=hostname,
            label=_device_label(model, hostname),
            role=_node_role(model, hostname),
        )
        for hostname in sorted(endpoints & set(model.devices))
    ]
    nodes.extend(
        DiagramNode(
            id=peer_id,
            label=f"{peer.peer_ip}\nAS {peer.peer_asn}",
            role=_PEER_ROLE,
            inferred=True,
        )
        for peer_id, peer in sorted(unresolved_peers.items())
    )
    return nodes


def _device_label(model: NetworkModel, hostname: str) -> str:
    """Name the router, over the AS it speaks BGP from."""
    device = model.devices[hostname]
    return f"{hostname}\nAS {device.asn}" if device.asn is not None else hostname


def _node_role(model: NetworkModel, hostname: str) -> DeviceRole:
    """A BGP speaker routes, so it is a router unless we know something better."""
    device = model.devices[hostname]
    if device.role is DeviceRole.UNKNOWN:
        return DeviceRole.ROUTER
    return device.role


def _legend(diagram: Diagram) -> list[LegendEntry]:
    """Explain the two session colors and the faded peers, when the diagram uses them."""
    entries: list[LegendEntry] = []

    colors = {link.color for link in diagram.links}
    if _IBGP_COLOR in colors:
        entries.append(LegendEntry(label="iBGP session", color=_IBGP_COLOR))
    if _EBGP_COLOR in colors:
        entries.append(LegendEntry(label="eBGP session", color=_EBGP_COLOR))

    if any(node.inferred for node in diagram.nodes):
        entries.append(
            LegendEntry(label="Peer known only by its address", role=_PEER_ROLE, inferred=True)
        )
    return entries
