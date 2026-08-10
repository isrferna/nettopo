"""Tests for port-channel parsing (PROJECT_SPEC.md section 4).

`tests/fixtures/etherchannel/` carries one fixture per command spelling: IOS/IOS-XE
`show etherchannel summary` and NX-OS `show port-channel summary`.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from nettopo.parsing.etherchannel import parse_port_channels

FIXTURES = Path(__file__).parent / "fixtures" / "etherchannel"


def _ios_capture() -> str:
    output = (FIXTURES / "show_etherchannel_summary.txt").read_text()
    return f"sw1-access#show etherchannel summary\n{output}"


def _nxos_capture() -> str:
    output = (FIXTURES / "show_port-channel_summary.txt").read_text()
    return f"nxos-core1#show port-channel summary\n{output}"


def test_parses_every_bundle_and_its_members_from_show_etherchannel_summary() -> None:
    port_channels = parse_port_channels(_ios_capture())

    assert [(bundle.name, bundle.po_id) for bundle in port_channels] == [("Po1", 1), ("Po150", 150)]
    assert port_channels[0].members == ("Gi1/0/1", "Gi1/0/2")
    assert port_channels[1].members == ("Te1/1/1", "Te1/1/2", "Te1/1/3")


def test_parses_the_nx_os_spelling_of_the_same_command() -> None:
    port_channels = parse_port_channels(_nxos_capture(), platform="cisco_nxos")

    assert [bundle.name for bundle in port_channels] == ["Po1", "Po99"]
    assert port_channels[0].members == ("Eth1/1", "Eth1/2")


def test_a_bundle_with_no_members_reports_none() -> None:
    # NX-OS prints "--" in the member column for an empty bundle; it is not an interface.
    port_channels = parse_port_channels(_nxos_capture(), platform="cisco_nxos")
    assert port_channels[1].members == ()


def test_member_names_are_normalized() -> None:
    capture = (
        "sw1#show etherchannel summary\n"
        "Group  Port-channel  Protocol    Ports\n"
        "------+-------------+-----------+---------------------------------------\n"
        "7      Port-channel7(SU)  LACP    GigabitEthernet1/0/7(P)\n"
    )
    port_channels = parse_port_channels(capture)

    assert port_channels[0].name == "Po7"
    assert port_channels[0].members == ("Gi1/0/7",)


def test_a_capture_without_the_command_yields_no_bundles() -> None:
    assert parse_port_channels("sw1-access#show version\nCisco IOS Software\n") == []


def test_a_command_spelling_the_platform_has_no_template_for_is_skipped_with_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # An NX-OS capture parsed under the `cisco_ios` default: a capture/--platform
    # mismatch must not abort the run.
    with caplog.at_level(logging.WARNING, logger="nettopo"):
        assert parse_port_channels(_nxos_capture(), platform="cisco_ios") == []

    assert "port-channel" in caplog.text
