"""Tests for `show lldp neighbors detail` parsing (PROJECT_SPEC.md section 4)."""

from __future__ import annotations

from pathlib import Path

from nettopo.parsing.lldp import parse_lldp

FIXTURES = Path(__file__).parent / "fixtures" / "lldp"
FIXTURE = FIXTURES / "show_lldp_neighbors_detail.txt"
NXOS_NEIGHBOR_FIXTURE = FIXTURES / "show_lldp_neighbors_detail_nxos_neighbor.txt"
ARISTA_NEIGHBOR_FIXTURE = FIXTURES / "show_lldp_neighbors_detail_arista_neighbor.txt"


def _capture(fixture: Path = FIXTURE) -> str:
    return f"sw1-access#show lldp neighbors detail\n{fixture.read_text()}"


def test_parse_lldp_returns_one_link() -> None:
    links = parse_lldp("sw1-access", _capture())
    assert len(links) == 1


def test_parse_lldp_prefers_port_description_and_normalizes_names() -> None:
    (link,) = parse_lldp("sw1-access", _capture())
    assert link.local_device == "sw1-access"
    assert link.local_interface == "Gi1/0/24"
    assert link.remote_device == "sw2-dist.example.com"
    assert link.remote_interface == "Gi1/0/1"
    assert link.discovery == "lldp"
    assert link.remote_capabilities == ["B", "R"]
    assert link.remote_mgmt_ip == "10.0.0.2"


def test_parse_lldp_falls_back_to_port_id_when_the_description_is_free_text() -> None:
    # NX-OS advertises the port's configured description, not its name, so the port id
    # is the only field that correlates with what CDP reports for the same link.
    (link,) = parse_lldp("acc-sw3", _capture(NXOS_NEIGHBOR_FIXTURE))
    assert link.remote_interface == "Eth1/1"
    assert link.remote_device == "nxos-core1"


def test_parse_lldp_returns_empty_list_when_command_absent() -> None:
    assert parse_lldp("sw1-access", "sw1-access#show version\nCisco IOS Software\n") == []


def test_parse_lldp_captures_the_neighbors_chassis_address() -> None:
    # The only place a neighbor's base MAC is reported at all: CDP has no equivalent, and
    # the STP view matches it against the root bridge address to name an external root.
    (link,) = parse_lldp("sw1-access", _capture())
    assert link.remote_chassis_id == "001a.2b3c.4d02"


def test_parse_lldp_falls_back_to_the_system_description_for_platform() -> None:
    # LLDP only names a model through LLDP-MED, which network gear does not send; the
    # System Description is the vendor's own platform statement and fills the same field.
    (link,) = parse_lldp("core-sw1", _capture(ARISTA_NEIGHBOR_FIXTURE))
    assert link.remote_device == "arista-core1"
    assert (
        link.remote_platform
        == "Arista Networks EOS version 4.35.4M running on an Arista Networks DCS-7504N"
    )
    assert link.remote_capabilities == ["B", "R"]
    assert link.remote_interface == "Eth3/11/1"


def test_parse_lldp_reports_a_cisco_neighbors_description_as_its_platform() -> None:
    # The IOS fixture has no LLDP-MED model either, so its description takes the slot.
    (link,) = parse_lldp("sw1-access", _capture())
    assert (
        link.remote_platform
        == "Cisco IOS Software, Catalyst L3 Switch Software (CAT9K_IOSXE), Version 17.9.4a"
    )
