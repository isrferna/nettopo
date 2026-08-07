"""Tests for the L2 view (PROJECT_SPEC.md section 7): endpoint filtering and the
port-channel (MLAG) grouping of physical links sharing a local port-channel membership.
"""

from __future__ import annotations

from nettopo.model.entities import Device, DeviceRole, Interface, Link, NetworkModel
from nettopo.views import l2


def _model() -> NetworkModel:
    model = NetworkModel()
    model.devices["sw1"] = Device(hostname="sw1", is_source=True)
    model.devices["sw2"] = Device(hostname="sw2", is_source=False, role=DeviceRole.SWITCH)
    model.devices["pc1"] = Device(hostname="pc1", is_source=False, role=DeviceRole.HOST)
    model.links = [
        Link(
            local_device="sw1",
            local_interface="Gi1/0/1",
            remote_device="sw2",
            remote_interface="Gi1/0/24",
            remote_capabilities=["Switch"],
        ),
        Link(
            local_device="sw1",
            local_interface="Gi1/0/2",
            remote_device="pc1",
            remote_interface="Eth0",
            remote_capabilities=["Host"],
        ),
    ]
    return model


def test_endpoints_all_keeps_every_device() -> None:
    diagram = l2.build(_model(), endpoints="all")
    assert {node.id for node in diagram.nodes} == {"sw1", "sw2", "pc1"}
    assert len(diagram.links) == 2


def test_endpoints_network_only_drops_hosts_but_keeps_sources_and_network_neighbors() -> None:
    diagram = l2.build(_model(), endpoints="network-only")
    assert {node.id for node in diagram.nodes} == {"sw1", "sw2"}
    assert [(link.source, link.target) for link in diagram.links] == [("sw1", "sw2")]


def test_network_only_keeps_a_source_device_even_with_no_reported_capabilities() -> None:
    # A source device's own capture never lists its own CDP/LLDP capabilities, so it
    # must be kept by is_source alone, not by capability matching.
    model = _model()
    diagram = l2.build(model, endpoints="network-only")
    assert "sw1" in {node.id for node in diagram.nodes}


def test_interface_labels_are_attached_to_both_link_ends() -> None:
    diagram = l2.build(_model(), endpoints="all")
    sw1_to_sw2 = next(link for link in diagram.links if link.target == "sw2")
    assert sw1_to_sw2.src_label == "Gi1/0/1"
    assert sw1_to_sw2.trgt_label == "Gi1/0/24"


def test_links_whose_local_interface_is_a_port_channel_member_are_grouped() -> None:
    model = NetworkModel()
    model.devices["sw1"] = Device(
        hostname="sw1",
        is_source=True,
        interfaces={
            "Gi1/0/1": Interface(name="Gi1/0/1", po_id=1),
            "Gi1/0/2": Interface(name="Gi1/0/2", po_id=1),
        },
    )
    model.devices["sw2"] = Device(hostname="sw2", role=DeviceRole.SWITCH)
    model.links = [
        Link(
            local_device="sw1",
            local_interface="Gi1/0/1",
            remote_device="sw2",
            remote_interface="Gi2/0/1",
        ),
        Link(
            local_device="sw1",
            local_interface="Gi1/0/2",
            remote_device="sw2",
            remote_interface="Gi2/0/2",
        ),
    ]

    diagram = l2.build(model, endpoints="all")

    assert len(diagram.links) == 1
    grouped = diagram.links[0]
    assert grouped.src_label == "Po1"
    assert grouped.trgt_label == "Gi2/0/1, Gi2/0/2"


def test_links_without_a_port_channel_membership_are_not_grouped() -> None:
    diagram = l2.build(_model(), endpoints="all")
    assert len(diagram.links) == 2
