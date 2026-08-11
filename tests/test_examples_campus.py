"""Guards the `examples/campus/` capture set against drift from what the README claims.

The README's "Example diagrams" section embeds diagrams generated from this directory and
describes them in prose. Both the images and that prose are committed artifacts: nothing
else would fail if an example capture were edited or a view's output changed shape, so
the section would quietly become fiction. These tests assert the handful of facts the
README states outright: the two node/link counts, the STP root and blocked ports of the
two distinct trees, the dashed uncaptured switch, the HSRP gateway pair and the roles and
priorities on its links, and what each `--group-mode` writes for either view.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nettopo.ingest.files import FileDataSource
from nettopo.ingest.model_builder import build_network_model
from nettopo.model.entities import NetworkModel
from nettopo.model.grouping import GroupMode
from nettopo.views import hsrp as hsrp_view
from nettopo.views import l2 as l2_view
from nettopo.views import stp as stp_view
from nettopo.views.diagram import Diagram
from nettopo.views.l2 import LinkMode

CAMPUS = Path(__file__).parent.parent / "examples" / "campus"

_BLOCKING_COLOR = "#C62828"
_FORWARDING_COLOR = "#2E7D32"
_HSRP_ACTIVE_COLOR = "#2E7D32"
_HSRP_STANDBY_COLOR = "#EF6C00"


@pytest.fixture(scope="module")
def campus() -> NetworkModel:
    return build_network_model(FileDataSource(CAMPUS))


def _blocked_ends(diagram: Diagram) -> set[tuple[str, str]]:
    """The (device, end label) pairs on every red link, from whichever end blocks."""
    blocked = set()
    for link in diagram.links:
        if link.color != _BLOCKING_COLOR:
            continue
        for device, label in ((link.source, link.src_label), (link.target, link.trgt_label)):
            if "blocking" in label:
                blocked.add((device, label.split()[0]))
    return blocked


def test_six_source_devices_and_four_neighbor_only_ones(campus: NetworkModel) -> None:
    sources = {hostname for hostname, device in campus.devices.items() if device.is_source}
    assert sources == {"core-sw1", "core-sw2", "dist-sw1", "dist-sw2", "acc-sw1", "acc-sw2"}
    assert set(campus.devices) - sources == {
        "acc-sw3",
        "edge-rtr",
        "esxi-host01",
        "esxi-host02",
    }


def test_l2_diagram_matches_the_readme(campus: NetworkModel) -> None:
    diagram = l2_view.build(campus)
    assert len(diagram.nodes) == 10
    assert len(diagram.links) == 13


def test_network_only_port_channel_diagram_matches_the_readme(campus: NetworkModel) -> None:
    """Drops both hosts, and collapses the two core links into the bundle both ends call Po1."""
    diagram = l2_view.build(campus, endpoints="network-only", link_mode=LinkMode.PORT_CHANNEL)
    assert len(diagram.nodes) == 8
    assert len(diagram.links) == 10

    bundle = next(
        link for link in diagram.links if {link.source, link.target} == {"core-sw1", "core-sw2"}
    )
    assert (bundle.src_label, bundle.trgt_label) == ("Po1", "Po1")
    assert "Gi1/0/1 — Gi1/0/1" in bundle.tooltip
    assert "Gi1/0/2 — Gi1/0/2" in bundle.tooltip


@pytest.mark.parametrize(
    ("vlan", "root", "blocked"),
    [
        (
            10,
            "core-sw1",
            {("dist-sw1", "Gi1/0/2"), ("dist-sw2", "Gi1/0/2"), ("acc-sw2", "Gi1/0/23")},
        ),
        (
            30,
            "core-sw2",
            {("dist-sw1", "Gi1/0/1"), ("dist-sw2", "Gi1/0/1"), ("acc-sw2", "Gi1/0/23")},
        ),
    ],
)
def test_stp_diagram_matches_the_readme(
    campus: NetworkModel, vlan: int, root: str, blocked: set[tuple[str, str]]
) -> None:
    """VLANs 10 and 30 are rooted on different core switches, so their trees differ."""
    (group,) = stp_view.build_groups(campus, vlan=vlan)
    diagram = group.diagram

    assert len(diagram.nodes) == 7
    assert len(diagram.links) == 9
    assert [node.id for node in diagram.nodes if node.highlight] == [root]
    assert _blocked_ends(diagram) == blocked


def test_uncaptured_switch_is_drawn_dashed_and_reached_over_a_forwarding_link(
    campus: NetworkModel,
) -> None:
    """acc-sw3 is only ever a CDP neighbor of dist-sw2, on a port that is not Edge."""
    (group,) = stp_view.build_groups(campus, vlan=10)

    (acc_sw3,) = [node for node in group.diagram.nodes if node.id == "acc-sw3"]
    assert acc_sw3.inferred
    assert acc_sw3.label == "acc-sw3"

    (link,) = [link for link in group.diagram.links if "acc-sw3" in (link.source, link.target)]
    assert (link.source, link.src_label) == ("acc-sw3", "Gi1/0/24")
    assert (link.target, link.trgt_label) == ("dist-sw2", "Gi1/0/22 designated/forwarding")
    assert link.color == _FORWARDING_COLOR


def test_edge_ports_keep_the_hosts_out_of_the_stp_view(campus: NetworkModel) -> None:
    (group,) = stp_view.build_groups(campus, vlan=10)
    assert {"esxi-host01", "esxi-host02", "edge-rtr"}.isdisjoint(
        node.id for node in group.diagram.nodes
    )


@pytest.mark.parametrize(
    ("group_mode", "expected"),
    [
        (GroupMode.PER_VLAN, [(10,), (20,), (30,), (99,)]),
        (GroupMode.STRICT, [(10, 20), (30,), (99,)]),
        (GroupMode.TOPOLOGY, [(10, 20, 99), (30,)]),
    ],
)
def test_group_modes_match_the_readme_table(
    campus: NetworkModel, group_mode: GroupMode, expected: list[tuple[int, ...]]
) -> None:
    """VLAN 99 shares 10/20's tree but not core-sw2's priority, which is what splits the modes."""
    groups = stp_view.build_groups(campus, group_mode=group_mode)
    assert [group.vlan_ids for group in groups] == expected


def test_hsrp_diagram_matches_the_readme(campus: NetworkModel) -> None:
    """VLAN 10's gateway is core-sw1, active at priority 150, standing in for 10.10.10.1."""
    (diagram_group,) = hsrp_view.build_groups(campus, vlan=10)
    diagram = diagram_group.diagram

    assert [node.label for node in diagram.nodes] == [
        "VLAN 10 group 10\n10.10.10.1",
        "core-sw1\n10.10.10.2",  # each router's own SVI address, beside the virtual one
        "core-sw2\n10.10.10.3",
    ]
    assert [node.id for node in diagram.nodes if node.highlight] == ["core-sw1"]
    assert [(link.source, link.src_label, link.color) for link in diagram.links] == [
        ("core-sw1", "Vl10 active/150", _HSRP_ACTIVE_COLOR),
        ("core-sw2", "Vl10 standby/100", _HSRP_STANDBY_COLOR),
    ]


def test_hsrp_active_gateway_follows_the_spanning_tree_root(campus: NetworkModel) -> None:
    """VLAN 30 is rooted on core-sw2, and its gateway is active there too."""
    (diagram_group,) = hsrp_view.build_groups(campus, vlan=30)
    assert [node.id for node in diagram_group.diagram.nodes if node.highlight] == ["core-sw2"]


@pytest.mark.parametrize(
    ("group_mode", "expected"),
    [
        (GroupMode.PER_VLAN, [(10,), (20,), (30,)]),
        (GroupMode.STRICT, [(10,), (20,), (30,)]),
        (GroupMode.TOPOLOGY, [(10, 20), (30,)]),
    ],
)
def test_hsrp_group_modes_match_the_readme_table(
    campus: NetworkModel, group_mode: GroupMode, expected: list[tuple[int, ...]]
) -> None:
    """VLANs 10 and 20 share their active/standby split and differ only in priority."""
    groups = hsrp_view.build_groups(campus, group_mode=group_mode)
    assert [group.vlan_ids for group in groups] == expected
