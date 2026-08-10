"""Tests for the STP view (PROJECT_SPEC.md sections 6, 7): per-VLAN diagram content,
root highlighting, port-state link coloring, and `--group-mode`/`--vlan` selection.
"""

from __future__ import annotations

import logging

import pytest

from nettopo.model.entities import (
    Device,
    Interface,
    Link,
    NetworkModel,
    StpBridge,
    StpPort,
    StpRole,
    StpState,
    StpVlan,
)
from nettopo.model.grouping import GroupMode
from nettopo.views import stp


def _bridge(device: str, vlan: int, base_priority: int, is_root: bool = False) -> StpBridge:
    return StpBridge(
        device=device,
        vlan=vlan,
        base_priority=base_priority,
        sys_id_ext=vlan,
        mac=f"aaaa.bbbb.{vlan:04d}",
        is_root=is_root,
    )


def _port(
    device: str,
    vlan: int,
    interface: str,
    role: StpRole,
    state: StpState,
    link_type: str = "P2p",
) -> StpPort:
    return StpPort(
        device=device,
        vlan=vlan,
        interface=interface,
        role=role,
        state=state,
        cost=4,
        link_type=link_type,
    )


def _two_switch_model(vlan: int = 10) -> NetworkModel:
    model = NetworkModel()
    model.devices["sw1"] = Device(hostname="sw1", is_source=True)
    model.devices["sw2"] = Device(hostname="sw2", is_source=True)
    model.links = [
        Link(
            local_device="sw1",
            local_interface="Gi1/0/1",
            remote_device="sw2",
            remote_interface="Gi1/0/2",
        ),
    ]
    model.stp[vlan] = StpVlan(
        vlan=vlan,
        root_device="sw1",
        bridges={
            "sw1": _bridge("sw1", vlan, base_priority=24576, is_root=True),
            "sw2": _bridge("sw2", vlan, base_priority=32768),
        },
        ports={
            ("sw1", "Gi1/0/1"): _port("sw1", vlan, "Gi1/0/1", StpRole.DESIGNATED, StpState.FWD),
            ("sw2", "Gi1/0/2"): _port("sw2", vlan, "Gi1/0/2", StpRole.ROOT, StpState.FWD),
        },
    )
    return model


def test_build_groups_for_a_single_vlan_returns_one_group() -> None:
    groups = stp.build_groups(_two_switch_model(), vlan=10)
    assert len(groups) == 1
    assert groups[0].vlan_ids == (10,)


def test_build_groups_for_a_missing_vlan_returns_nothing() -> None:
    assert stp.build_groups(_two_switch_model(), vlan=999) == []


def test_diagram_has_a_node_per_bridge() -> None:
    (group,) = stp.build_groups(_two_switch_model(), vlan=10)
    assert {node.id for node in group.diagram.nodes} == {"sw1", "sw2"}


def test_root_bridge_node_is_highlighted() -> None:
    (group,) = stp.build_groups(_two_switch_model(), vlan=10)
    sw1 = next(node for node in group.diagram.nodes if node.id == "sw1")
    sw2 = next(node for node in group.diagram.nodes if node.id == "sw2")
    assert sw1.highlight is True
    assert sw2.highlight is False


def test_node_label_includes_mac_and_effective_priority() -> None:
    (group,) = stp.build_groups(_two_switch_model(), vlan=10)
    sw2 = next(node for node in group.diagram.nodes if node.id == "sw2")
    assert "aaaa.bbbb.0010" in sw2.label
    assert "32778" in sw2.label  # base 32768 + sys_id_ext 10


def test_forwarding_link_is_colored_green() -> None:
    (group,) = stp.build_groups(_two_switch_model(), vlan=10)
    (link,) = group.diagram.links
    assert link.color == "#2E7D32"


def test_blocking_link_is_colored_red() -> None:
    model = _two_switch_model()
    model.stp[10].ports[("sw2", "Gi1/0/2")] = _port(
        "sw2", 10, "Gi1/0/2", StpRole.ALTERNATE, StpState.BLK
    )
    (group,) = stp.build_groups(model, vlan=10)
    (link,) = group.diagram.links
    assert link.color == "#C62828"


def test_link_labels_carry_role_and_state_per_end() -> None:
    (group,) = stp.build_groups(_two_switch_model(), vlan=10)
    (link,) = group.diagram.links
    assert link.src_label == "Gi1/0/1 designated/forwarding"
    assert link.trgt_label == "Gi1/0/2 root/forwarding"


def test_physical_links_outside_the_vlans_stp_data_are_excluded() -> None:
    model = _two_switch_model()
    model.devices["sw3"] = Device(hostname="sw3", is_source=True)
    model.links.append(
        Link(
            local_device="sw1",
            local_interface="Gi1/0/9",
            remote_device="sw3",
            remote_interface="Gi1/0/9",
        )
    )
    (group,) = stp.build_groups(model, vlan=10)
    assert {(link.source, link.target) for link in group.diagram.links} == {("sw1", "sw2")}


def test_broken_port_is_colored_as_blocking() -> None:
    model = _two_switch_model()
    model.stp[10].ports[("sw2", "Gi1/0/2")] = _port(
        "sw2", 10, "Gi1/0/2", StpRole.DESIGNATED, StpState.BKN
    )
    (group,) = stp.build_groups(model, vlan=10)
    (link,) = group.diagram.links
    assert link.color == "#C62828"


def _port_channel_model(vlan: int = 10) -> NetworkModel:
    """Two switches joined by a two-member Po1, named as real captures name it.

    `show spanning-tree` reports only the bundle, CDP/LLDP report only its members, so the
    two sources share no interface name at all -- the mismatch the view has to bridge.
    """
    model = NetworkModel()
    for hostname in ("sw1", "sw2"):
        device = Device(hostname=hostname, is_source=True)
        device.interfaces["Po1"] = Interface(name="Po1", po_members=["Gi1/0/1", "Gi1/0/2"])
        for member in ("Gi1/0/1", "Gi1/0/2"):
            device.interfaces[member] = Interface(name=member, po_id=1)
        model.devices[hostname] = device

    model.links = [
        Link(
            local_device="sw1",
            local_interface=member,
            remote_device="sw2",
            remote_interface=member,
        )
        for member in ("Gi1/0/1", "Gi1/0/2")
    ]
    model.stp[vlan] = StpVlan(
        vlan=vlan,
        root_device="sw1",
        bridges={
            "sw1": _bridge("sw1", vlan, base_priority=24576, is_root=True),
            "sw2": _bridge("sw2", vlan, base_priority=32768),
        },
        ports={
            ("sw1", "Po1"): _port("sw1", vlan, "Po1", StpRole.DESIGNATED, StpState.FWD),
            ("sw2", "Po1"): _port("sw2", vlan, "Po1", StpRole.ROOT, StpState.FWD),
        },
    )
    return model


def test_port_channel_members_collapse_into_one_link() -> None:
    (group,) = stp.build_groups(_port_channel_model(), vlan=10)
    assert len(group.diagram.links) == 1


def test_port_channel_link_is_labeled_with_the_bundle_and_its_stp_state() -> None:
    (group,) = stp.build_groups(_port_channel_model(), vlan=10)
    (link,) = group.diagram.links
    assert link.src_label == "Po1 designated/forwarding"
    assert link.trgt_label == "Po1 root/forwarding"
    assert link.color == "#2E7D32"


def test_port_channel_link_tooltip_lists_the_member_interfaces() -> None:
    (group,) = stp.build_groups(_port_channel_model(), vlan=10)
    (link,) = group.diagram.links
    assert link.tooltip == "Members:<br>Gi1/0/1 — Gi1/0/1<br>Gi1/0/2 — Gi1/0/2"


def test_bundled_links_are_dropped_without_port_channel_data() -> None:
    # `Interface.po_id` comes only from `show etherchannel summary`. Without that command
    # in the capture there is nothing to tie Gi1/0/1 to Po1, and the links cannot be drawn
    # -- the failure this whole code path exists to make visible.
    model = _port_channel_model()
    for device in model.devices.values():
        device.interfaces.clear()
    (group,) = stp.build_groups(model, vlan=10)
    assert group.diagram.links == []
    assert len(group.diagram.nodes) == 2


def test_one_sided_bundle_stays_one_link_per_member() -> None:
    # sw2 has no bundle of its own, so its two ports really are distinct to STP.
    model = _port_channel_model()
    model.devices["sw2"].interfaces.clear()
    for member in ("Gi1/0/1", "Gi1/0/2"):
        model.stp[10].ports[("sw2", member)] = _port("sw2", 10, member, StpRole.ROOT, StpState.FWD)
    (group,) = stp.build_groups(model, vlan=10)
    assert len(group.diagram.links) == 2


def test_link_orientation_ignores_the_direction_it_was_discovered_from() -> None:
    model = _port_channel_model()
    model.links = [
        Link(
            local_device="sw2",
            local_interface=member,
            remote_device="sw1",
            remote_interface=member,
        )
        for member in ("Gi1/0/1", "Gi1/0/2")
    ]
    (group,) = stp.build_groups(model, vlan=10)
    (link,) = group.diagram.links
    assert (link.source, link.target) == ("sw1", "sw2")
    assert link.src_label == "Po1 designated/forwarding"


def _neighbor_model(link_type: str = "P2p", vlan: int = 10) -> NetworkModel:
    """One captured switch facing a device we hold no capture for."""
    model = NetworkModel()
    model.devices["sw1"] = Device(hostname="sw1", is_source=True)
    model.devices["sw9"] = Device(hostname="sw9")
    model.links = [
        Link(
            local_device="sw1",
            local_interface="Gi1/0/24",
            remote_device="sw9",
            remote_interface="Gi0/1",
        )
    ]
    model.stp[vlan] = StpVlan(
        vlan=vlan,
        root_device="sw1",
        bridges={"sw1": _bridge("sw1", vlan, base_priority=24576, is_root=True)},
        ports={
            ("sw1", "Gi1/0/24"): _port(
                "sw1", vlan, "Gi1/0/24", StpRole.DESIGNATED, StpState.FWD, link_type=link_type
            )
        },
    )
    return model


def test_uncaptured_neighbor_on_a_non_edge_port_is_drawn_as_inferred() -> None:
    (group,) = stp.build_groups(_neighbor_model(), vlan=10)
    sw9 = next(node for node in group.diagram.nodes if node.id == "sw9")
    assert sw9.inferred is True
    assert sw9.label == "sw9"  # no MAC or priority: we have neither
    assert len(group.diagram.links) == 1


def test_uncaptured_neighbor_behind_an_edge_port_is_excluded() -> None:
    (group,) = stp.build_groups(_neighbor_model(link_type="P2p Edge"), vlan=10)
    assert {node.id for node in group.diagram.nodes} == {"sw1"}
    assert group.diagram.links == []


def test_edge_is_read_as_a_token_not_a_substring() -> None:
    # NX-OS orders the column the other way round, and "Peer" must not read as "Edge".
    assert stp.build_groups(_neighbor_model(link_type="Edge P2p"), vlan=10)[0].diagram.links == []
    assert stp.build_groups(_neighbor_model(link_type="P2p Peer(STP)"), vlan=10)[0].diagram.links


def test_uncaptured_neighbor_facing_a_bundle_gets_a_single_link() -> None:
    # An EtherChannel cannot exist on one side only, so the members collapse even though
    # the neighbor never told us it bundles them.
    model = _port_channel_model()
    del model.devices["sw2"]
    model.devices["sw9"] = Device(hostname="sw9")
    model.links = [
        Link(
            local_device="sw1",
            local_interface=member,
            remote_device="sw9",
            remote_interface=member,
        )
        for member in ("Gi1/0/1", "Gi1/0/2")
    ]
    del model.stp[10].bridges["sw2"]
    del model.stp[10].ports[("sw2", "Po1")]

    (group,) = stp.build_groups(model, vlan=10)
    (link,) = group.diagram.links
    assert link.src_label == "Po1 designated/forwarding"
    assert link.trgt_label == "Gi1/0/1, Gi1/0/2"


def _external_root_model(chassis_id: str | None) -> NetworkModel:
    model = _neighbor_model()
    model.devices["sw9"].chassis_id = chassis_id
    model.stp[10].root_device = None
    model.stp[10].root_mac = "aaaa.bbbb.9999"
    model.stp[10].bridges["sw1"].is_root = False
    model.stp[10].bridges["sw1"].root_mac = "aaaa.bbbb.9999"
    model.stp[10].ports[("sw1", "Gi1/0/24")] = _port(
        "sw1", 10, "Gi1/0/24", StpRole.ROOT, StpState.FWD
    )
    return model


def test_external_root_is_highlighted_when_the_lldp_chassis_id_matches() -> None:
    (group,) = stp.build_groups(_external_root_model("AAAA.BBBB.9999"), vlan=10)
    sw9 = next(node for node in group.diagram.nodes if node.id == "sw9")
    assert sw9.highlight is True
    assert sw9.inferred is True


def test_external_root_without_a_matching_chassis_id_warns_and_highlights_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="nettopo"):
        (group,) = stp.build_groups(_external_root_model(chassis_id=None), vlan=10)

    assert all(node.highlight is False for node in group.diagram.nodes)
    assert "aaaa.bbbb.9999" in caplog.text


def test_a_mismatched_chassis_id_never_highlights_the_wrong_switch() -> None:
    (group,) = stp.build_groups(_external_root_model("dead.beef.0000"), vlan=10)
    assert all(node.highlight is False for node in group.diagram.nodes)

    assert stp.stp_output_filename((10,)) == "stp_vlan10.drawio"


def test_stp_output_filename_for_a_group_is_sorted_and_joined() -> None:
    assert stp.stp_output_filename((30, 10, 20)) == "stp_vlans-30_10_20.drawio"


def _grouping_model() -> NetworkModel:
    # vlan10 and vlan20 share topology (sw2 blocks Gi1/0/2) but differ in sw2's
    # priority; vlan30 blocks a different port entirely -- mirrors the boundary cases
    # in tests/test_grouping.py, now exercised through the view.
    model = NetworkModel()
    model.devices["sw1"] = Device(hostname="sw1", is_source=True)
    model.devices["sw2"] = Device(hostname="sw2", is_source=True)
    model.links = [
        Link(
            local_device="sw1",
            local_interface="Gi1/0/1",
            remote_device="sw2",
            remote_interface="Gi1/0/1",
        ),
        Link(
            local_device="sw1",
            local_interface="Gi1/0/2",
            remote_device="sw2",
            remote_interface="Gi1/0/2",
        ),
    ]
    for vlan, sw2_priority, blocked_interface in (
        (10, 32768, "Gi1/0/2"),
        (20, 30000, "Gi1/0/2"),
        (30, 32768, "Gi1/0/1"),
    ):
        forwarding_interface = "Gi1/0/1" if blocked_interface == "Gi1/0/2" else "Gi1/0/2"
        model.stp[vlan] = StpVlan(
            vlan=vlan,
            root_device="sw1",
            bridges={
                "sw1": _bridge("sw1", vlan, base_priority=24576, is_root=True),
                "sw2": _bridge("sw2", vlan, base_priority=sw2_priority),
            },
            ports={
                ("sw1", "Gi1/0/1"): _port("sw1", vlan, "Gi1/0/1", StpRole.DESIGNATED, StpState.FWD),
                ("sw1", "Gi1/0/2"): _port("sw1", vlan, "Gi1/0/2", StpRole.DESIGNATED, StpState.FWD),
                ("sw2", forwarding_interface): _port(
                    "sw2", vlan, forwarding_interface, StpRole.ROOT, StpState.FWD
                ),
                ("sw2", blocked_interface): _port(
                    "sw2", vlan, blocked_interface, StpRole.ALTERNATE, StpState.BLK
                ),
            },
        )
    return model


def test_per_vlan_mode_never_groups() -> None:
    groups = stp.build_groups(_grouping_model(), group_mode=GroupMode.PER_VLAN)
    assert sorted(group.vlan_ids for group in groups) == [(10,), (20,), (30,)]


def test_topology_mode_groups_same_topology_ignoring_priority() -> None:
    groups = stp.build_groups(_grouping_model(), group_mode=GroupMode.TOPOLOGY)
    assert sorted(group.vlan_ids for group in groups) == [(10, 20), (30,)]


def test_strict_mode_does_not_group_differing_priority() -> None:
    groups = stp.build_groups(_grouping_model(), group_mode=GroupMode.STRICT)
    assert sorted(group.vlan_ids for group in groups) == [(10,), (20,), (30,)]


def test_a_link_between_two_switches_outside_this_vlan_is_ignored() -> None:
    # Neither end runs this VLAN's spanning tree, so the link belongs to another diagram.
    model = _two_switch_model()
    for hostname in ("sw7", "sw8"):
        model.devices[hostname] = Device(hostname=hostname, is_source=True)
    model.links.append(
        Link(
            local_device="sw7",
            local_interface="Gi1/0/1",
            remote_device="sw8",
            remote_interface="Gi1/0/1",
        )
    )
    (group,) = stp.build_groups(model, vlan=10)
    assert {node.id for node in group.diagram.nodes} == {"sw1", "sw2"}
    assert len(group.diagram.links) == 1


def test_a_transitioning_link_gets_no_color() -> None:
    # Listening and learning are neither forwarding nor blocked; coloring them either way
    # would assert something about the topology that has not settled yet.
    model = _two_switch_model()
    model.stp[10].ports[("sw1", "Gi1/0/1")] = _port(
        "sw1", 10, "Gi1/0/1", StpRole.DESIGNATED, StpState.LIS
    )
    del model.stp[10].ports[("sw2", "Gi1/0/2")]
    (group,) = stp.build_groups(model, vlan=10)
    (link,) = group.diagram.links
    assert link.color is None
