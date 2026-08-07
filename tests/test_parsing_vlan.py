"""Tests for `show vlan brief` parsing (PROJECT_SPEC.md section 4)."""

from __future__ import annotations

from pathlib import Path

from nettopo.parsing.vlan import parse_vlans

FIXTURE = Path(__file__).parent / "fixtures" / "vlan" / "show_vlan_brief.txt"


def _capture() -> str:
    return f"sw1-access#show vlan brief\n{FIXTURE.read_text()}"


def test_parse_vlans_returns_every_vlan_row() -> None:
    vlans = parse_vlans(_capture())
    assert [vlan.vlan_id for vlan in vlans] == [1, 10, 99]


def test_parse_vlans_captures_name_and_status() -> None:
    (vlan1, _vlan10, vlan99) = parse_vlans(_capture())
    assert vlan1.name == "default"
    assert vlan1.status == "active"
    assert vlan99.name == "mgmt"


def test_parse_vlans_returns_empty_list_when_command_absent() -> None:
    assert parse_vlans("sw1-access#show version\nCisco IOS Software\n") == []
