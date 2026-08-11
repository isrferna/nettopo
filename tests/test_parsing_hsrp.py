"""Tests for `show standby brief` parsing (PROJECT_SPEC.md sections 4, 6, 12).

Covers both IOS and IOS-XE fixture variants (identical command format -- see
`parsing/hsrp.py`), the preempt column with and without its flag, several groups on one
SVI, and the two rows the model cannot represent: a group on a non-SVI interface, and a
virtual IP the device has not learned.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from nettopo.model.entities import HsrpRole
from nettopo.parsing.hsrp import parse_hsrp

FIXTURES = Path(__file__).parent / "fixtures" / "hsrp"


def _capture(filename: str) -> str:
    return f"sw1#show standby brief\n{(FIXTURES / filename).read_text()}"


def test_returns_nothing_when_the_command_was_not_captured() -> None:
    assert parse_hsrp("sw1", "sw1#show version\nCisco IOS Software\n") == []


def test_parses_every_group_keyed_by_vlan_and_group() -> None:
    captures = parse_hsrp("sw1", _capture("ios_show_standby_brief.txt"))
    assert [(capture.vlan, capture.group) for capture in captures] == [(10, 10), (20, 20), (30, 30)]


def test_member_carries_priority_role_and_normalized_svi() -> None:
    (vlan10, *_rest) = parse_hsrp("sw1", _capture("ios_show_standby_brief.txt"))
    assert vlan10.virtual_ip == "10.10.10.1"
    assert vlan10.member.device == "sw1"
    assert vlan10.member.interface == "Vl10"
    assert vlan10.member.group == 10
    assert vlan10.member.priority == 150
    assert vlan10.member.role is HsrpRole.ACTIVE


@pytest.mark.parametrize(
    ("index", "role", "preempt"),
    [(0, HsrpRole.ACTIVE, True), (1, HsrpRole.STANDBY, False), (2, HsrpRole.LISTEN, True)],
)
def test_state_and_preempt_columns(index: int, role: HsrpRole, preempt: bool) -> None:
    """The preempt column is a literal space when unset, never absent, so it is a boolean."""
    captures = parse_hsrp("sw1", _capture("ios_show_standby_brief.txt"))
    assert captures[index].member.role is role
    assert captures[index].member.preempt is preempt


def test_iosxe_variant_parses_several_groups_on_one_svi() -> None:
    captures = parse_hsrp("sw1", _capture("iosxe_show_standby_brief.txt"))
    vlan10 = [capture for capture in captures if capture.vlan == 10]
    assert [(capture.group, capture.virtual_ip) for capture in vlan10] == [
        (10, "10.10.10.1"),
        (11, "10.10.10.5"),
    ]


def test_an_unlearned_virtual_ip_is_none_rather_than_the_word_unknown() -> None:
    captures = parse_hsrp("sw1", _capture("iosxe_show_standby_brief.txt"))
    (vlan40,) = [capture for capture in captures if capture.vlan == 40]
    assert vlan40.virtual_ip is None
    assert vlan40.member.role is HsrpRole.INIT


def test_a_group_on_a_routed_port_is_skipped_with_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`NetworkModel.hsrp` is keyed by VLAN, so a group on `Gi1/0/24` has nowhere to live."""
    with caplog.at_level(logging.WARNING, logger="nettopo"):
        captures = parse_hsrp("sw1", _capture("iosxe_show_standby_brief.txt"))

    assert all(capture.member.interface.startswith("Vl") for capture in captures)
    assert "Gi1/0/24" in caplog.text


def test_an_unrecognized_state_is_skipped_with_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    capture = (
        "sw1#show standby brief\n"
        "Interface   Grp  Pri P State    Active          Standby         Virtual IP\n"
        "Vl10        10   150 P Napping  local           10.10.10.3      10.10.10.1\n"
    )
    with caplog.at_level(logging.WARNING, logger="nettopo"):
        assert parse_hsrp("sw1", capture) == []
    assert "Napping" in caplog.text


def test_a_platform_without_a_template_warns_instead_of_raising(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """NX-OS spells the command `show hsrp brief`, so ntc-templates has nothing to run."""
    with caplog.at_level(logging.WARNING, logger="nettopo"):
        captures = parse_hsrp("sw1", _capture("ios_show_standby_brief.txt"), platform="cisco_nxos")

    assert captures == []
    assert "Skipping HSRP data" in caplog.text
