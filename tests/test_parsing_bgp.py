"""Tests for `show ip bgp summary` parsing (PROJECT_SPEC.md sections 4, 6, 12).

Covers both IOS and IOS-XE fixture variants (identical command format -- see
`parsing/bgp.py`), the iBGP/eBGP classification the summary never states outright, the
State/PfxRcd column in each of its two meanings (a prefix count for a session that is up,
a state word for one that is not), and the router ID the header line carries about the
reporting device itself.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from nettopo.model.entities import BgpType
from nettopo.parsing.bgp import parse_bgp

FIXTURES = Path(__file__).parent / "fixtures" / "bgp"

_ASDOT_CAPTURE = (
    "r1#show ip bgp summary\n"
    "BGP router identifier 10.255.0.1, local AS number 1.10\n"
    "\n"
    "Neighbor        V           AS MsgRcvd MsgSent   TblVer  InQ OutQ Up/Down  State/PfxRcd\n"
    "10.255.0.2      4         1.20     101     104        6    0    0 1d02h           3\n"
)


def _capture(filename: str) -> str:
    return f"r1#show ip bgp summary\n{(FIXTURES / filename).read_text()}"


def test_returns_nothing_when_the_command_was_not_captured() -> None:
    capture = parse_bgp("r1", "r1#show version\nCisco IOS Software\n")
    assert (capture.router_id, capture.peers) == (None, [])


def test_the_router_id_is_read_off_the_header_line() -> None:
    """It names the reporting router, not any session, so it rides on the capture."""
    assert parse_bgp("r1", _capture("ios_show_ip_bgp_summary.txt")).router_id == "10.255.0.1"


def test_the_iosxe_variant_reports_its_own_router_id() -> None:
    assert parse_bgp("r1", _capture("iosxe_show_ip_bgp_summary.txt")).router_id == "10.255.0.3"


def test_parses_one_peer_per_neighbor_row() -> None:
    peers = parse_bgp("r1", _capture("ios_show_ip_bgp_summary.txt")).peers
    assert [peer.peer_ip for peer in peers] == [
        "10.255.0.2",
        "198.51.100.1",
        "203.0.113.9",
        "192.0.2.5",
        "192.0.2.6",
    ]


def test_a_peer_carries_both_as_numbers_and_the_reporting_device() -> None:
    (ibgp, *_rest) = parse_bgp("r1", _capture("ios_show_ip_bgp_summary.txt")).peers
    assert ibgp.local_device == "r1"
    assert ibgp.local_asn == 65001
    assert ibgp.peer_asn == 65001


@pytest.mark.parametrize(
    ("index", "session_type"),
    [(0, BgpType.IBGP), (1, BgpType.EBGP), (2, BgpType.EBGP)],
)
def test_a_session_is_ibgp_exactly_when_the_two_as_numbers_match(
    index: int, session_type: BgpType
) -> None:
    """The summary never says iBGP or eBGP; it is read off the two AS numbers."""
    peers = parse_bgp("r1", _capture("ios_show_ip_bgp_summary.txt")).peers
    assert peers[index].type is session_type


@pytest.mark.parametrize(
    ("index", "state"),
    [
        (0, "Established"),
        (1, "Established"),
        (2, "Idle"),
        (3, "Active"),
        (4, "Idle (Admin)"),
    ],
)
def test_the_state_column_is_read_in_both_of_its_meanings(index: int, state: str) -> None:
    """A prefix count is only printed for a session that is up, so it means Established."""
    peers = parse_bgp("r1", _capture("ios_show_ip_bgp_summary.txt")).peers
    assert peers[index].state == state


def test_v1_leaves_peer_device_unresolved_and_assumes_the_default_vrf() -> None:
    peers = parse_bgp("r1", _capture("ios_show_ip_bgp_summary.txt")).peers
    assert all(peer.peer_device is None for peer in peers)
    assert all(peer.vrf == "default" for peer in peers)


def test_iosxe_variant_parses_the_same_way() -> None:
    peers = parse_bgp("r1", _capture("iosxe_show_ip_bgp_summary.txt")).peers
    assert [(peer.peer_ip, peer.type, peer.state) for peer in peers] == [
        ("10.255.0.1", BgpType.IBGP, "Established"),
        ("10.255.0.2", BgpType.IBGP, "Established"),
        ("198.51.100.5", BgpType.EBGP, "Established"),
    ]


def test_as_numbers_written_in_asdot_notation_are_converted() -> None:
    """IOS accepts `1.10` for AS 65546, and the model stores an AS as a single int."""
    (peer,) = parse_bgp("r1", _ASDOT_CAPTURE).peers
    assert (peer.local_asn, peer.peer_asn) == (65546, 65556)
    assert peer.type is BgpType.EBGP


def test_a_platform_without_a_template_warns_instead_of_raising(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A capture parsed as the wrong platform must not abort the whole run."""
    with caplog.at_level(logging.WARNING, logger="nettopo"):
        capture = parse_bgp("r1", _capture("ios_show_ip_bgp_summary.txt"), platform="juniper_junos")

    assert (capture.router_id, capture.peers) == (None, [])
    assert "Skipping BGP data" in caplog.text
