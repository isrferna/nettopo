"""Tests for `show cdp neighbors detail` parsing (PROJECT_SPEC.md section 4)."""

from __future__ import annotations

from pathlib import Path

from nettopo.parsing.cdp import parse_cdp

FIXTURES = Path(__file__).parent / "fixtures" / "cdp"
FIXTURE = FIXTURES / "show_cdp_neighbors_detail.txt"
NXOS_NEIGHBOR_FIXTURE = FIXTURES / "show_cdp_neighbors_detail_nxos_neighbor.txt"


def _capture(fixture: Path = FIXTURE) -> str:
    return f"sw1-access#show cdp neighbors detail\n{fixture.read_text()}"


def test_parse_cdp_returns_one_link_per_neighbor() -> None:
    links = parse_cdp("sw1-access", _capture())
    assert len(links) == 2


def test_parse_cdp_normalizes_interface_names_and_sets_local_device() -> None:
    links = parse_cdp("sw1-access", _capture())
    link = next(link for link in links if link.remote_device == "sw2-dist.example.com")
    assert link.local_device == "sw1-access"
    assert link.local_interface == "Gi1/0/24"
    assert link.remote_interface == "Gi1/0/1"
    assert link.discovery == "cdp"
    assert link.remote_platform == "cisco WS-C9300-24P"
    assert link.remote_capabilities == ["Switch", "IGMP"]


def test_parse_cdp_reports_the_device_id_verbatim_including_a_serial_suffix() -> None:
    # NX-OS advertises `hostname(SERIAL)` as its CDP device id by default. Parsers report
    # what the device said; correlating that with the plain name LLDP reports is
    # `utils/hostnames.py`'s job, via `ingest/model_builder.py`.
    (link,) = parse_cdp("acc-sw3", _capture(NXOS_NEIGHBOR_FIXTURE))
    assert link.remote_device == "nxos-core1(FDO21120U5D)"
    assert link.remote_interface == "Eth1/1"


def test_parse_cdp_prefers_the_management_address_over_the_entry_address() -> None:
    # The fixture's sw2-dist entry advertises both: 10.0.0.2 as its connected-interface
    # address, 192.168.1.2 as its management address. ntc-templates' `cisco_ios` template
    # exposes only the former, under a name that suggests the latter.
    links = parse_cdp("sw1-access", _capture())
    link = next(link for link in links if link.remote_device == "sw2-dist.example.com")
    assert link.remote_mgmt_ip == "192.168.1.2"


def test_parse_cdp_falls_back_to_the_entry_address_without_a_management_block() -> None:
    # Not every neighbor advertises a management address; the interface address it did
    # advertise still beats nothing at all.
    links = parse_cdp("sw1-access", _capture())
    link = next(link for link in links if link.remote_device == "core-rtr.example.com")
    assert link.remote_mgmt_ip == "10.0.0.254"


def test_parse_cdp_reads_the_nxos_spelling_of_the_management_block() -> None:
    # NX-OS writes "Mgmt address(es):" and "IPv4 Address:", and names its entries by
    # `System Name` while the device id carries the chassis serial.
    nxos_capture = (
        "nxos-core1# show cdp neighbors detail\n"
        "----------------------------------------\n"
        "Device ID:acc-sw3(FOC2134X0DEF)\n"
        "System Name: acc-sw3\n"
        "\n"
        "Interface address(es):\n"
        "    IPv4 Address: 10.0.0.3\n"
        "Platform: cisco WS-C2960X-24TS-L, Capabilities: Switch IGMP\n"
        "Interface: Ethernet1/1, Port ID (outgoing port): GigabitEthernet1/0/49\n"
        "Holdtime: 163 sec\n"
        "\n"
        "Version:\n"
        "Cisco IOS Software, C2960X Software\n"
        "\n"
        "Advertisement Version: 2\n"
        "Mgmt address(es):\n"
        "    IPv4 Address: 192.168.1.33\n"
    )
    (link,) = parse_cdp("nxos-core1", nxos_capture, platform="cisco_nxos")
    assert link.remote_device == "acc-sw3"
    assert link.remote_mgmt_ip == "192.168.1.33"


def test_parse_cdp_returns_empty_list_when_command_absent() -> None:
    assert parse_cdp("sw1-access", "sw1-access#show version\nCisco IOS Software\n") == []
