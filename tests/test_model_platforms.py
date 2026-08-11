"""Tests for platform-string -> DeviceRole classification (PROJECT_SPEC.md section 6)."""

from __future__ import annotations

import pytest

from nettopo.model.entities import DeviceRole
from nettopo.model.platforms import classify_platform


@pytest.mark.parametrize(
    ("platform", "expected"),
    [
        # Every string below is one that appears in `examples/` or `tests/fixtures/`.
        ("cisco ISR4331/K9", DeviceRole.ROUTER),
        ("cisco ISR4451-X/K9", DeviceRole.ROUTER),
        ("cisco IOSv", DeviceRole.ROUTER),
        ("cisco C9500-16X", DeviceRole.L3_SWITCH),
        ("cisco WS-C3850-24P", DeviceRole.L3_SWITCH),
        ("cisco C9300-24P", DeviceRole.SWITCH),
        ("cisco WS-C9300-24P", DeviceRole.SWITCH),
        ("cisco WS-C2960X-24TS-L", DeviceRole.SWITCH),
        ("VMware ESX", DeviceRole.SERVER),
        ("VMware ESXi", DeviceRole.SERVER),
    ],
)
def test_classifies_the_platforms_the_fixtures_actually_contain(
    platform: str, expected: DeviceRole
) -> None:
    assert classify_platform(platform) is expected


def test_a_nexus_is_recognized_without_the_vendor_prefix() -> None:
    """NX-OS reports no `cisco ` prefix, so anchored matching would miss every Nexus."""
    assert classify_platform("N9K-C93180YC-EX") is DeviceRole.L3_SWITCH


def test_matching_ignores_case() -> None:
    assert classify_platform("CISCO C9500-16X") is DeviceRole.L3_SWITCH


@pytest.mark.parametrize(
    ("platform", "expected"),
    [
        ("cisco ASA5525", DeviceRole.FIREWALL),
        ("Cisco Firepower 1010", DeviceRole.FIREWALL),
        ("cisco AIR-AP2802I-B-K9", DeviceRole.AP),
        ("cisco C9800-L-C-K9", DeviceRole.AP),
        ("Cisco IP Phone 7960", DeviceRole.PHONE),
        ("CP-8841", DeviceRole.PHONE),
    ],
)
def test_classifies_the_families_no_fixture_covers_yet(platform: str, expected: DeviceRole) -> None:
    assert classify_platform(platform) is expected


def test_a_wireless_controller_is_not_mistaken_for_a_catalyst_switch() -> None:
    """`C9800` would match the Catalyst 9000 pattern if order were not load-bearing."""
    assert classify_platform("cisco C9800-40-K9") is DeviceRole.AP


@pytest.mark.parametrize("platform", [None, "", "some-appliance-nobody-has-heard-of"])
def test_no_opinion_is_returned_rather_than_unknown(platform: str | None) -> None:
    """None leaves the caller's capability-derived role alone; UNKNOWN would erase it."""
    assert classify_platform(platform) is None
