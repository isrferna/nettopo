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


def test_parse_cdp_returns_empty_list_when_command_absent() -> None:
    assert parse_cdp("sw1-access", "sw1-access#show version\nCisco IOS Software\n") == []
