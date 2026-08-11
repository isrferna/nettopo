"""Tests for the HSRP view (PROJECT_SPEC.md sections 6, 7): the virtual-gateway star, the
active router's highlight, role-colored links, and `--group-mode`/`--vlan` selection.
"""

from __future__ import annotations

from nettopo.model.entities import (
    Device,
    DeviceRole,
    HsrpGroup,
    HsrpMember,
    HsrpRole,
    Interface,
    InterfaceType,
    NetworkModel,
)
from nettopo.model.grouping import GroupMode
from nettopo.views import hsrp

_ACTIVE_COLOR = "#2E7D32"
_STANDBY_COLOR = "#EF6C00"


def _router(hostname: str, vlan: int, address: str | None) -> Device:
    """A source device whose SVI for `vlan` holds `address`, as `show ip int brief` reports."""
    device = Device(hostname=hostname, is_source=True, role=DeviceRole.L3_SWITCH)
    device.interfaces[f"Vl{vlan}"] = Interface(
        name=f"Vl{vlan}", type=InterfaceType.SVI, ip_address=address
    )
    return device


def _member(device: str, vlan: int, group: int, priority: int, role: HsrpRole) -> HsrpMember:
    return HsrpMember(
        device=device,
        interface=f"Vl{vlan}",
        group=group,
        priority=priority,
        role=role,
        preempt=True,
    )


def _group(
    vlan: int, group: int, virtual_ip: str | None, *members: HsrpMember
) -> tuple[tuple[int, int], HsrpGroup]:
    return (vlan, group), HsrpGroup(
        vlan=vlan,
        group=group,
        virtual_ip=virtual_ip,
        members={member.device: member for member in members},
    )


def _pair_model() -> NetworkModel:
    """Two gateways, active/standby on VLAN 10 and swapped on VLAN 30."""
    model = NetworkModel(
        devices={
            "gw-a": _router("gw-a", 10, "10.0.10.2"),
            "gw-b": _router("gw-b", 10, "10.0.10.3"),
        }
    )
    model.hsrp = dict(
        [
            _group(
                10,
                10,
                "10.0.10.1",
                _member("gw-a", 10, 10, 150, HsrpRole.ACTIVE),
                _member("gw-b", 10, 10, 100, HsrpRole.STANDBY),
            ),
            _group(
                30,
                30,
                "10.0.30.1",
                _member("gw-a", 30, 30, 100, HsrpRole.STANDBY),
                _member("gw-b", 30, 30, 150, HsrpRole.ACTIVE),
            ),
        ]
    )
    return model


def test_a_group_is_drawn_as_its_members_around_a_virtual_gateway() -> None:
    (diagram_group,) = hsrp.build_groups(_pair_model(), vlan=10)
    diagram = diagram_group.diagram

    assert [node.id for node in diagram.nodes] == ["hsrp:vlan10:group10", "gw-a", "gw-b"]
    assert [(link.source, link.target) for link in diagram.links] == [
        ("gw-a", "hsrp:vlan10:group10"),
        ("gw-b", "hsrp:vlan10:group10"),
    ]


def test_the_gateway_node_names_its_vlan_group_and_virtual_ip() -> None:
    """Under `--group-mode` the diagram stands for several VLANs, so it says which one
    the address it shows belongs to."""
    (diagram_group,) = hsrp.build_groups(_pair_model(), vlan=10)
    (gateway, *_routers) = diagram_group.diagram.nodes

    assert gateway.label == "VLAN 10 group 10\n10.0.10.1"
    assert gateway.role is DeviceRole.UNKNOWN  # not a device, so no Cisco icon


def test_a_group_with_no_learned_virtual_ip_is_labeled_without_one() -> None:
    model = NetworkModel(devices={"gw-a": Device(hostname="gw-a", is_source=True)})
    model.hsrp = dict([_group(10, 10, None, _member("gw-a", 10, 10, 100, HsrpRole.INIT))])

    (diagram_group,) = hsrp.build_groups(model, vlan=10)
    (gateway, _router) = diagram_group.diagram.nodes
    assert gateway.label == "VLAN 10 group 10"


def test_links_carry_the_svi_role_and_priority_and_are_colored_by_role() -> None:
    (diagram_group,) = hsrp.build_groups(_pair_model(), vlan=10)
    active, standby = diagram_group.diagram.links

    assert (active.src_label, active.color) == ("Vl10 active/150", _ACTIVE_COLOR)
    assert (standby.src_label, standby.color) == ("Vl10 standby/100", _STANDBY_COLOR)


def test_each_router_carries_its_own_svi_address_under_its_name() -> None:
    """The real addresses, beside the virtual one, say which box a given hop actually is."""
    (diagram_group,) = hsrp.build_groups(_pair_model(), vlan=10)
    (_gateway, gw_a, gw_b) = diagram_group.diagram.nodes

    assert gw_a.label == "gw-a\n10.0.10.2"
    assert gw_b.label == "gw-b\n10.0.10.3"


def test_a_router_whose_svi_address_is_unknown_is_labeled_with_its_name_alone() -> None:
    """`show standby brief` carries no addresses of its own, so a capture without
    `show ip interface brief` leaves nothing to show rather than an invented address."""
    model = NetworkModel(devices={"gw-a": Device(hostname="gw-a", is_source=True)})
    model.hsrp = dict([_group(10, 10, "10.0.10.1", _member("gw-a", 10, 10, 100, HsrpRole.ACTIVE))])

    (diagram_group,) = hsrp.build_groups(model, vlan=10)
    (_gateway, router) = diagram_group.diagram.nodes
    assert router.label == "gw-a"


def test_every_member_shows_its_address_including_the_listening_ones() -> None:
    """Four routers, one active, one standby, two listening.

    The two listeners are the case that needs `show ip interface brief`: `show standby
    brief` names the active and standby routers by address and no one else, so nothing
    else in the captures could place them.
    """
    model = NetworkModel(
        devices={
            hostname: _router(hostname, 10, address)
            for hostname, address in (
                ("gw-a", "10.0.10.2"),
                ("gw-b", "10.0.10.3"),
                ("gw-c", "10.0.10.4"),
                ("gw-d", "10.0.10.5"),
            )
        }
    )
    model.hsrp = dict(
        [
            _group(
                10,
                10,
                "10.0.10.1",
                _member("gw-a", 10, 10, 150, HsrpRole.ACTIVE),
                _member("gw-b", 10, 10, 140, HsrpRole.STANDBY),
                _member("gw-c", 10, 10, 100, HsrpRole.LISTEN),
                _member("gw-d", 10, 10, 90, HsrpRole.LISTEN),
            )
        ]
    )

    (diagram_group,) = hsrp.build_groups(model, vlan=10)
    diagram = diagram_group.diagram

    assert [node.label for node in diagram.nodes] == [
        "VLAN 10 group 10\n10.0.10.1",
        "gw-a\n10.0.10.2",
        "gw-b\n10.0.10.3",
        "gw-c\n10.0.10.4",
        "gw-d\n10.0.10.5",
    ]
    assert [(link.source, link.src_label, link.color) for link in diagram.links] == [
        ("gw-a", "Vl10 active/150", _ACTIVE_COLOR),
        ("gw-b", "Vl10 standby/140", _STANDBY_COLOR),
        ("gw-c", "Vl10 listen/100", None),
        ("gw-d", "Vl10 listen/90", None),
    ]
    assert [node.id for node in diagram.nodes if node.highlight] == ["gw-a"]


def test_only_the_active_router_is_highlighted() -> None:
    (vlan10,) = hsrp.build_groups(_pair_model(), vlan=10)
    (vlan30,) = hsrp.build_groups(_pair_model(), vlan=30)

    assert [node.id for node in vlan10.diagram.nodes if node.highlight] == ["gw-a"]
    assert [node.id for node in vlan30.diagram.nodes if node.highlight] == ["gw-b"]


def test_a_role_with_no_color_leaves_the_link_and_the_legend_neutral() -> None:
    """A listening member is neither answering for the gateway nor next in line for it."""
    model = NetworkModel(devices={"gw-c": Device(hostname="gw-c", is_source=True)})
    model.hsrp = dict([_group(10, 10, "10.0.10.1", _member("gw-c", 10, 10, 80, HsrpRole.LISTEN))])

    (diagram_group,) = hsrp.build_groups(model, vlan=10)
    (link,) = diagram_group.diagram.links
    assert link.color is None
    assert [entry.label for entry in diagram_group.diagram.legend] == ["Virtual gateway"]


def test_the_legend_explains_every_marking_the_diagram_uses() -> None:
    (diagram_group,) = hsrp.build_groups(_pair_model(), vlan=10)
    assert [entry.label for entry in diagram_group.diagram.legend] == [
        "Virtual gateway",
        "Active router",
        "Active for this group",
        "Standby for this group",
    ]


def test_a_member_without_a_known_role_is_drawn_as_a_layer_3_switch() -> None:
    """HSRP runs on a routed interface, so a bare hostname is not just any switch."""
    model = NetworkModel(devices={"gw-a": Device(hostname="gw-a", is_source=True)})
    model.hsrp = dict([_group(10, 10, "10.0.10.1", _member("gw-a", 10, 10, 100, HsrpRole.ACTIVE))])

    (diagram_group,) = hsrp.build_groups(model, vlan=10)
    (_gateway, router) = diagram_group.diagram.nodes
    assert router.role is DeviceRole.L3_SWITCH


def test_several_groups_on_one_svi_share_a_diagram() -> None:
    """Two gateways load-sharing a VLAN is one picture, not two."""
    model = _pair_model()
    model.hsrp.update(
        [
            _group(
                40,
                40,
                "10.0.40.1",
                _member("gw-a", 40, 40, 150, HsrpRole.ACTIVE),
                _member("gw-b", 40, 40, 90, HsrpRole.STANDBY),
            ),
            _group(
                40,
                41,
                "10.0.40.254",
                _member("gw-a", 40, 41, 90, HsrpRole.STANDBY),
                _member("gw-b", 40, 41, 150, HsrpRole.ACTIVE),
            ),
        ]
    )

    (diagram_group,) = hsrp.build_groups(model, vlan=40)
    assert [node.id for node in diagram_group.diagram.nodes] == [
        "hsrp:vlan40:group40",
        "hsrp:vlan40:group41",
        "gw-a",
        "gw-b",
    ]
    assert len(diagram_group.diagram.links) == 4


def test_an_unknown_vlan_yields_no_diagram() -> None:
    assert hsrp.build_groups(_pair_model(), vlan=99) == []


def _grouping_model() -> NetworkModel:
    """VLANs 10 and 20 share roles but not priorities; VLAN 30 swaps the two routers."""
    model = _pair_model()
    model.hsrp.update(
        [
            _group(
                20,
                20,
                "10.0.20.1",
                _member("gw-a", 20, 20, 140, HsrpRole.ACTIVE),
                _member("gw-b", 20, 20, 90, HsrpRole.STANDBY),
            )
        ]
    )
    return model


def test_per_vlan_mode_never_groups() -> None:
    groups = hsrp.build_groups(_grouping_model(), group_mode=GroupMode.PER_VLAN)
    assert [group.vlan_ids for group in groups] == [(10,), (20,), (30,)]


def test_strict_mode_keeps_vlans_whose_priorities_differ_apart() -> None:
    groups = hsrp.build_groups(_grouping_model(), group_mode=GroupMode.STRICT)
    assert [group.vlan_ids for group in groups] == [(10,), (20,), (30,)]


def test_topology_mode_groups_vlans_whose_roles_match() -> None:
    groups = hsrp.build_groups(_grouping_model(), group_mode=GroupMode.TOPOLOGY)
    assert [group.vlan_ids for group in groups] == [(10, 20), (30,)]


def test_a_grouped_diagram_is_rendered_from_its_lowest_vlan() -> None:
    (grouped, _vlan30) = hsrp.build_groups(_grouping_model(), group_mode=GroupMode.TOPOLOGY)
    (gateway, *_routers) = grouped.diagram.nodes

    assert grouped.vlan_ids == (10, 20)
    assert gateway.label == "VLAN 10 group 10\n10.0.10.1"


def test_a_vlan_with_more_groups_never_joins_one_with_fewer() -> None:
    """Fingerprints are compared group-for-group, so a second group is a real difference."""
    model = _grouping_model()
    model.hsrp.update(
        [
            _group(
                50,
                10,
                "10.0.50.1",
                _member("gw-a", 50, 10, 150, HsrpRole.ACTIVE),
                _member("gw-b", 50, 10, 100, HsrpRole.STANDBY),
            ),
            _group(50, 11, "10.0.50.254", _member("gw-a", 50, 11, 90, HsrpRole.ACTIVE)),
        ]
    )

    groups = hsrp.build_groups(model, group_mode=GroupMode.TOPOLOGY)
    assert [group.vlan_ids for group in groups] == [(10, 20), (30,), (50,)]


def test_an_empty_model_yields_no_diagrams() -> None:
    assert hsrp.build_groups(NetworkModel()) == []


def test_hsrp_output_filename_for_one_vlan() -> None:
    assert hsrp.hsrp_output_filename((10,)) == "hsrp_vlan10.drawio"


def test_hsrp_output_filename_for_a_group_is_joined() -> None:
    assert hsrp.hsrp_output_filename((10, 20, 30)) == "hsrp_vlans-10_20_30.drawio"
