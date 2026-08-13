"""Tests for the BGP session graph view (PROJECT_SPEC.md sections 7, 12).

The view's one real decision is what to do with a peer that is named by address only:
match it against the interface addresses the model already holds, so two captured routers
reporting each other become one link rather than four disconnected boxes, and leave
anything that matches nothing as a faded node of its own.
"""

from __future__ import annotations

from nettopo.model.entities import BgpPeer, BgpType, Device, DeviceRole, Interface, NetworkModel
from nettopo.views import bgp

_IBGP_COLOR = "#1565C0"
_EBGP_COLOR = "#6A1B9A"

_UPSTREAM_IP = "203.0.113.9"
_UPSTREAM_NODE = f"bgp:peer:{_UPSTREAM_IP}"


def _device(
    hostname: str,
    address: str,
    *,
    asn: int | None,
    role: DeviceRole,
    router_id: str | None = None,
) -> Device:
    return Device(
        hostname=hostname,
        is_source=True,
        role=role,
        asn=asn,
        router_id=router_id,
        interfaces={"Gi0/0": Interface(name="Gi0/0", ip_address=address)},
    )


def _peer(
    local_device: str,
    peer_ip: str,
    *,
    peer_asn: int = 65001,
    state: str = "Established",
) -> BgpPeer:
    return BgpPeer(
        local_device=local_device,
        local_asn=65001,
        peer_ip=peer_ip,
        peer_asn=peer_asn,
        state=state,
        type=BgpType.IBGP if peer_asn == 65001 else BgpType.EBGP,
    )


def _pair_model() -> NetworkModel:
    """Two routers in one AS peering with each other, and one uncaptured upstream."""
    model = NetworkModel()
    model.devices = {
        "core-r1": _device(
            "core-r1", "10.0.12.1", asn=65001, role=DeviceRole.ROUTER, router_id="10.255.0.1"
        ),
        "core-r2": _device(
            "core-r2", "10.0.12.2", asn=65001, role=DeviceRole.ROUTER, router_id="10.255.0.2"
        ),
    }
    model.bgp = [
        _peer("core-r1", "10.0.12.2"),
        _peer("core-r1", _UPSTREAM_IP, peer_asn=65200, state="Idle"),
        _peer("core-r2", "10.0.12.1"),
    ]
    return model


def test_two_routers_reporting_each_other_are_drawn_as_one_session() -> None:
    diagram = bgp.build(_pair_model())
    assert [(link.source, link.target) for link in diagram.links] == [
        ("core-r1", _UPSTREAM_NODE),
        ("core-r1", "core-r2"),
    ]


def test_nodes_are_the_captured_routers_plus_any_peer_named_by_address_alone() -> None:
    diagram = bgp.build(_pair_model())
    assert [node.id for node in diagram.nodes] == ["core-r1", "core-r2", _UPSTREAM_NODE]


def test_a_router_is_labeled_with_its_as_number_and_router_id() -> None:
    diagram = bgp.build(_pair_model())
    assert diagram.nodes[0].label == "core-r1\nAS 65001\nRID 10.255.0.1"


def test_an_unresolved_peer_is_labeled_by_address_and_faded() -> None:
    """A peer we hold no capture for is exactly what `inferred` already marks."""
    upstream = bgp.build(_pair_model()).nodes[-1]
    assert upstream.label == f"{_UPSTREAM_IP}\nAS 65200"
    assert upstream.role is DeviceRole.UNKNOWN
    assert upstream.inferred is True


def test_a_peer_named_by_address_alone_is_never_given_a_router_id() -> None:
    """The summary prints a router ID for the reporting device and for nobody else."""
    labels = [node.label for node in bgp.build(_pair_model()).nodes if node.inferred]
    assert all("RID" not in label for label in labels)


def test_sessions_are_colored_by_type_and_labeled_with_their_state() -> None:
    ebgp, ibgp = bgp.build(_pair_model()).links
    assert (ibgp.color, ibgp.label) == (_IBGP_COLOR, "Established")
    assert (ebgp.color, ebgp.label) == (_EBGP_COLOR, "Idle")


def test_ends_that_disagree_about_the_state_report_both() -> None:
    """One end can still be `Active` while the other has moved on; hiding that is worse."""
    model = _pair_model()
    model.bgp = [_peer("core-r1", "10.0.12.2"), _peer("core-r2", "10.0.12.1", state="Active")]
    (session,) = bgp.build(model).links
    assert session.label == "Established / Active"


def test_a_router_with_no_known_role_is_drawn_as_a_router() -> None:
    model = _pair_model()
    model.devices["core-r1"].role = DeviceRole.UNKNOWN
    assert bgp.build(model).nodes[0].role is DeviceRole.ROUTER


def test_a_router_whose_as_number_is_unknown_keeps_the_lines_it_does_have() -> None:
    model = _pair_model()
    model.devices["core-r1"].asn = None
    assert bgp.build(model).nodes[0].label == "core-r1\nRID 10.255.0.1"


def test_a_router_whose_router_id_is_unknown_is_labeled_without_one() -> None:
    """A device reached only as someone else's peer has no summary of its own to read."""
    model = _pair_model()
    model.devices["core-r1"].router_id = None
    assert bgp.build(model).nodes[0].label == "core-r1\nAS 65001"


def test_a_router_we_know_nothing_else_about_is_labeled_with_its_name_alone() -> None:
    model = _pair_model()
    model.devices["core-r1"].asn = None
    model.devices["core-r1"].router_id = None
    assert bgp.build(model).nodes[0].label == "core-r1"


def test_a_peer_address_belonging_to_the_reporting_router_is_not_a_session_with_itself() -> None:
    model = _pair_model()
    model.bgp = [_peer("core-r1", "10.0.12.1")]
    (session,) = bgp.build(model).links
    assert (session.source, session.target) == ("core-r1", "bgp:peer:10.0.12.1")


def test_the_legend_explains_every_marking_the_diagram_uses() -> None:
    diagram = bgp.build(_pair_model())
    assert [entry.label for entry in diagram.legend] == [
        "iBGP session",
        "eBGP session",
        "Peer known only by its address",
    ]


def test_a_diagram_with_no_ebgp_does_not_advertise_an_ebgp_color() -> None:
    model = _pair_model()
    model.bgp = [_peer("core-r1", "10.0.12.2")]
    assert [entry.label for entry in bgp.build(model).legend] == ["iBGP session"]


def test_a_model_with_no_bgp_yields_an_empty_diagram() -> None:
    diagram = bgp.build(NetworkModel())
    assert (diagram.nodes, diagram.links, diagram.legend) == ([], [], [])
