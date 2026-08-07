"""Tests for interface parsing (PROJECT_SPEC.md section 4)."""

from __future__ import annotations

from pathlib import Path

from nettopo.model.entities import InterfaceType
from nettopo.parsing.interfaces import parse_interfaces

FIXTURES = Path(__file__).parent / "fixtures" / "interfaces"


def _capture() -> str:
    ip_brief = (FIXTURES / "show_ip_interface_brief.txt").read_text()
    interfaces = (FIXTURES / "show_interfaces.txt").read_text()
    return (
        f"sw1-access#show ip interface brief\n{ip_brief}\nsw1-access#show interfaces\n{interfaces}"
    )


def test_parse_interfaces_merges_both_commands_by_normalized_name() -> None:
    interfaces = parse_interfaces(_capture())
    assert set(interfaces) == {"Vl1", "Vl10", "Gi1/0/1", "Gi1/0/24"}


def test_parse_interfaces_prefers_show_interfaces_description_and_ip() -> None:
    interfaces = parse_interfaces(_capture())
    gi1 = interfaces["Gi1/0/1"]
    assert gi1.description == "Uplink to core-rtr"
    assert gi1.ip_address == "10.10.10.1"
    assert gi1.prefix_len == 24
    assert gi1.admin_up is True
    assert gi1.oper_up is True
    assert gi1.type is InterfaceType.PHYSICAL


def test_parse_interfaces_falls_back_to_ip_brief_for_interfaces_missing_from_show_interfaces() -> (
    None
):
    interfaces = parse_interfaces(_capture())
    vlan10 = interfaces["Vl10"]
    assert vlan10.ip_address == "10.10.10.1"
    assert vlan10.admin_up is True
    assert vlan10.oper_up is True
    assert vlan10.type is InterfaceType.SVI


def test_parse_interfaces_detects_administratively_down() -> None:
    interfaces = parse_interfaces(_capture())
    vlan1 = interfaces["Vl1"]
    assert vlan1.admin_up is False
    assert vlan1.oper_up is False


def test_parse_interfaces_returns_empty_dict_when_no_commands_present() -> None:
    assert parse_interfaces("sw1-access#show version\nCisco IOS Software\n") == {}


def test_parse_interfaces_types_every_interface_kind() -> None:
    capture = (
        "sw1-access#show ip interface brief\n"
        "Interface              IP-Address      OK? Method Status                Protocol\n"
        "Port-channel1          unassigned      YES unset  up                    up\n"
        "Loopback0               10.255.255.1    YES manual up                    up\n"
        "Tunnel0                 unassigned      YES unset  up                    up\n"
        "Management1             unassigned      YES unset  up                    up\n"
        "GigabitEthernet1/0/1.10 unassigned      YES unset  up                    up\n"
    )
    interfaces = parse_interfaces(capture)
    assert interfaces["Po1"].type is InterfaceType.PORT_CHANNEL
    assert interfaces["Lo0"].type is InterfaceType.LOOPBACK
    assert interfaces["Tu0"].type is InterfaceType.TUNNEL
    assert interfaces["Mgmt1"].type is InterfaceType.MGMT
    assert interfaces["Gi1/0/1.10"].type is InterfaceType.SUBINTERFACE
