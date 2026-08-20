"""Tests for the L2 view (PROJECT_SPEC.md section 7): endpoint filtering and the two
link modes -- one link per physical interface, or one link per port-channel (MLAG).
"""

from __future__ import annotations

from nettopo.model.entities import Device, DeviceRole, Interface, Link, NetworkModel
from nettopo.views import l2
from nettopo.views.l2 import LinkMode


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


def test_network_only_keeps_a_neighbor_reported_with_lldp_letter_capabilities() -> None:
    # An LLDP-only neighbor advertises `B`/`R`, not CDP's "Switch"/"Router" words.
    model = _model()
    model.devices["ar1"] = Device(hostname="ar1", is_source=False, role=DeviceRole.L3_SWITCH)
    model.links.append(
        Link(
            local_device="sw1",
            local_interface="Te1/0/1",
            remote_device="ar1",
            remote_interface="Eth3/11/1",
            discovery="lldp",
            remote_capabilities=["B", "R"],
        )
    )
    diagram = l2.build(model, endpoints="network-only")
    assert "ar1" in {node.id for node in diagram.nodes}


def test_interface_labels_are_attached_to_both_link_ends() -> None:
    diagram = l2.build(_model(), endpoints="all")
    sw1_to_sw2 = next(link for link in diagram.links if link.target == "sw2")
    assert sw1_to_sw2.src_label == "Gi1/0/1"
    assert sw1_to_sw2.trgt_label == "Gi1/0/24"


def _bundled_model(
    *, remote_is_source: bool = False, swap_second_member: bool = False
) -> NetworkModel:
    """sw1 and sw2 joined by a two-member bundle, sw1 always knowing it as Po1."""
    model = NetworkModel()
    model.devices["sw1"] = Device(
        hostname="sw1",
        is_source=True,
        interfaces={
            "Po1": Interface(name="Po1", po_members=["Gi1/0/1", "Gi1/0/2"]),
            "Gi1/0/1": Interface(name="Gi1/0/1", po_id=1),
            "Gi1/0/2": Interface(name="Gi1/0/2", po_id=1),
        },
    )
    model.devices["sw2"] = Device(
        hostname="sw2",
        is_source=remote_is_source,
        role=DeviceRole.SWITCH,
        interfaces={
            "Po2": Interface(name="Po2", po_members=["Gi2/0/1", "Gi2/0/2"]),
            "Gi2/0/1": Interface(name="Gi2/0/1", po_id=2),
            "Gi2/0/2": Interface(name="Gi2/0/2", po_id=2),
        }
        if remote_is_source
        else {},
    )
    second_member = Link(
        local_device="sw1",
        local_interface="Gi1/0/2",
        remote_device="sw2",
        remote_interface="Gi2/0/2",
        remote_capabilities=["Switch"],
    )
    if swap_second_member:
        second_member = Link(
            local_device="sw2",
            local_interface="Gi2/0/2",
            remote_device="sw1",
            remote_interface="Gi1/0/2",
        )
    model.links = [
        Link(
            local_device="sw1",
            local_interface="Gi1/0/1",
            remote_device="sw2",
            remote_interface="Gi2/0/1",
            remote_capabilities=["Switch"],
        ),
        second_member,
    ]
    return model


def test_physical_mode_draws_one_link_per_member_interface() -> None:
    diagram = l2.build(_bundled_model(), link_mode=LinkMode.PHYSICAL)

    assert [(link.src_label, link.trgt_label) for link in diagram.links] == [
        ("Gi1/0/1", "Gi2/0/1"),
        ("Gi1/0/2", "Gi2/0/2"),
    ]
    assert all(link.tooltip == "" for link in diagram.links)


def test_physical_mode_is_the_default() -> None:
    assert (
        l2.build(_bundled_model()).links
        == l2.build(_bundled_model(), link_mode=LinkMode.PHYSICAL).links
    )


def test_port_channel_mode_draws_one_link_labeled_with_the_port_channel() -> None:
    diagram = l2.build(_bundled_model(), link_mode=LinkMode.PORT_CHANNEL)

    assert len(diagram.links) == 1
    bundle = diagram.links[0]
    assert bundle.src_label == "Po1"
    # sw2 is not a source device, so its interfaces are unknown and its end can only be
    # labeled with the member ports the neighbor reported.
    assert bundle.trgt_label == "Gi2/0/1, Gi2/0/2"


def test_port_channel_mode_labels_both_ends_when_both_devices_are_source_captures() -> None:
    diagram = l2.build(_bundled_model(remote_is_source=True), link_mode=LinkMode.PORT_CHANNEL)

    assert len(diagram.links) == 1
    assert (diagram.links[0].src_label, diagram.links[0].trgt_label) == ("Po1", "Po2")


def test_port_channel_mode_carries_the_member_interfaces_in_the_tooltip() -> None:
    diagram = l2.build(_bundled_model(), link_mode=LinkMode.PORT_CHANNEL)

    assert diagram.links[0].tooltip == "Members:<br>Gi1/0/1 — Gi2/0/1<br>Gi1/0/2 — Gi2/0/2"


def test_port_channel_mode_bundles_members_reported_from_opposite_ends() -> None:
    # Which end of a link the model stored depends on whose capture reported it first;
    # a bundle must not split in two because of that.
    diagram = l2.build(
        _bundled_model(remote_is_source=True, swap_second_member=True),
        link_mode=LinkMode.PORT_CHANNEL,
    )

    assert len(diagram.links) == 1
    assert diagram.links[0].tooltip == "Members:<br>Gi1/0/1 — Gi2/0/1<br>Gi1/0/2 — Gi2/0/2"


def test_port_channel_mode_leaves_links_with_no_port_channel_untouched() -> None:
    physical = l2.build(_model(), link_mode=LinkMode.PHYSICAL)
    bundled = l2.build(_model(), link_mode=LinkMode.PORT_CHANNEL)

    assert bundled.links == physical.links


def test_port_channel_mode_folds_an_adjacency_reported_on_the_bundle_itself() -> None:
    # NX-OS can report a vPC/port-channel adjacency on `Po1` rather than on a member
    # port; that link belongs to the same bundle as the member links.
    model = _bundled_model()
    model.links.append(
        Link(
            local_device="sw1",
            local_interface="Po1",
            remote_device="sw2",
            remote_interface="Po2",
            remote_capabilities=["Switch"],
        )
    )

    diagram = l2.build(model, link_mode=LinkMode.PORT_CHANNEL)

    assert len(diagram.links) == 1
    assert diagram.links[0].src_label == "Po1"
