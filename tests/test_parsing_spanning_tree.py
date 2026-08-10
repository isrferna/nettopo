"""Tests for `show spanning-tree` parsing (PROJECT_SPEC.md sections 4, 6, 12).

Covers both IOS and IOS-XE fixture variants (identical command format -- see
`parsing/spanning_tree.py`), multi-VLAN parsing, root vs non-root bridges, and a
blocked port.
"""

from __future__ import annotations

from pathlib import Path

from nettopo.model.entities import StpRole, StpState
from nettopo.parsing.spanning_tree import parse_spanning_tree

FIXTURES = Path(__file__).parent / "fixtures" / "spanning_tree"


def _capture(filename: str) -> str:
    return f"sw1#show spanning-tree\n{(FIXTURES / filename).read_text()}"


def test_parses_every_vlan_block() -> None:
    captures = parse_spanning_tree("sw1", _capture("ios_show_spanning-tree.txt"))
    assert [capture.vlan for capture in captures] == [10, 99]


def test_non_root_bridge_captures_priority_and_mac() -> None:
    (vlan10, _vlan99) = parse_spanning_tree("sw1", _capture("ios_show_spanning-tree.txt"))
    assert vlan10.bridge.is_root is False
    assert vlan10.bridge.base_priority == 32768
    assert vlan10.bridge.sys_id_ext == 10
    assert vlan10.bridge.mac == "aaaa.bbbb.0002"
    assert vlan10.bridge.effective_priority == 32778


def test_root_bridge_is_flagged() -> None:
    (_vlan10, vlan99) = parse_spanning_tree("sw1", _capture("ios_show_spanning-tree.txt"))
    assert vlan99.bridge.is_root is True
    assert vlan99.bridge.base_priority == 24576


def test_port_roles_and_states_are_parsed_including_a_blocked_port() -> None:
    (vlan10, _vlan99) = parse_spanning_tree("sw1", _capture("ios_show_spanning-tree.txt"))
    ports = {port.interface: port for port in vlan10.ports}
    assert ports["Gi1/0/24"].role is StpRole.ROOT
    assert ports["Gi1/0/24"].state is StpState.FWD
    assert ports["Gi1/0/2"].role is StpRole.ALTERNATE
    assert ports["Gi1/0/2"].state is StpState.BLK
    assert ports["Gi1/0/2"].cost == 4


def test_interface_names_are_normalized() -> None:
    (_vlan10, vlan99) = parse_spanning_tree("sw1", _capture("ios_show_spanning-tree.txt"))
    assert {port.interface for port in vlan99.ports} == {"Gi1/0/24"}


def test_iosxe_variant_parses_the_same_way() -> None:
    (vlan10,) = parse_spanning_tree("sw1", _capture("iosxe_show_spanning-tree.txt"))
    assert vlan10.bridge.is_root is True
    assert {port.interface for port in vlan10.ports} == {"Gi1/0/1", "Te1/1/1"}


def test_returns_empty_list_when_command_absent() -> None:
    assert parse_spanning_tree("sw1", "sw1#show version\nCisco IOS Software\n") == []


def test_root_address_is_captured_even_when_this_bridge_is_not_the_root() -> None:
    (vlan10, vlan99) = parse_spanning_tree("sw1", _capture("ios_show_spanning-tree.txt"))
    assert vlan10.bridge.root_mac == "aaaa.bbbb.0001"  # another switch holds the root
    assert vlan99.bridge.root_mac == vlan99.bridge.mac  # this one is the root


def _awkward_ports() -> dict[str, object]:
    (vlan10,) = parse_spanning_tree("sw1", _capture("ios_show_spanning-tree_awkward_rows.txt"))
    return {port.interface: port for port in vlan10.ports}


def test_a_port_channel_is_parsed_under_its_bundle_name() -> None:
    ports = _awkward_ports()
    assert "Po1" in ports


def test_an_inconsistency_marker_glued_to_the_state_does_not_drop_the_row() -> None:
    # "BKN*ROOT_Inc" has no space before the cost; a stricter pattern loses the whole port
    # and, with it, every link the STP view would have drawn through it.
    ports = _awkward_ports()
    assert ports["Gi1/0/5"].state is StpState.BKN
    assert ports["Gi1/0/5"].role is StpRole.DESIGNATED
    assert ports["Gi1/0/5"].cost == 19


def test_the_type_column_is_captured_verbatim() -> None:
    ports = _awkward_ports()
    assert ports["Po1"].link_type == "P2p"
    assert ports["Gi1/0/7"].link_type == "Shr"
    assert ports["Gi1/0/8"].link_type == "P2p Edge"


def test_is_edge_reflects_the_type_column() -> None:
    ports = _awkward_ports()
    assert ports["Gi1/0/8"].is_edge is True
    assert ports["Gi1/0/6"].is_edge is True  # edge and inconsistent at the same time
    assert ports["Po1"].is_edge is False
    assert ports["Gi1/0/7"].is_edge is False
