"""Tests for `show lldp neighbors detail` parsing (PROJECT_SPEC.md section 4)."""

from __future__ import annotations

from pathlib import Path

from nettopo.parsing.lldp import parse_lldp

FIXTURE = Path(__file__).parent / "fixtures" / "lldp" / "show_lldp_neighbors_detail.txt"


def _capture() -> str:
    return f"sw1-access#show lldp neighbors detail\n{FIXTURE.read_text()}"


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


def test_parse_lldp_returns_empty_list_when_command_absent() -> None:
    assert parse_lldp("sw1-access", "sw1-access#show version\nCisco IOS Software\n") == []
