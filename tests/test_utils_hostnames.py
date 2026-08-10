"""Table-driven tests for the device-name normalizer (PROJECT_SPEC.md section 5)."""

from __future__ import annotations

import pytest

from nettopo.utils.hostnames import (
    identity_key,
    resolve_device_identities,
    split_serial_suffix,
)

SERIAL_SUFFIX_CASES = [
    ("nxos-core1(FDO21120U5D)", ("nxos-core1", "FDO21120U5D")),
    ("nxos-core1 (FDO21120U5D)", ("nxos-core1", "FDO21120U5D")),
    ("nxos-core1.example.com(FDO21120U5D)", ("nxos-core1.example.com", "FDO21120U5D")),
    ("nxos-core1", ("nxos-core1", None)),
    ("  acc-sw1  ", ("acc-sw1", None)),
    ("SEP001A2B3C5E01", ("SEP001A2B3C5E01", None)),
    # Parentheses that are not a trailing token are part of the name.
    ("sw(1)-access", ("sw(1)-access", None)),
]

IDENTITY_KEY_CASES = [
    ("nxos-core1", ("nxos-core1", "")),
    ("nxos-core1(FDO21120U5D)", ("nxos-core1", "")),
    ("NXOS-Core1.Example.COM", ("nxos-core1", "example.com")),
    ("esxi-host01.example.com", ("esxi-host01", "example.com")),
]


@pytest.mark.parametrize(("name", "expected"), SERIAL_SUFFIX_CASES)
def test_split_serial_suffix(name: str, expected: tuple[str, str | None]) -> None:
    assert split_serial_suffix(name) == expected


@pytest.mark.parametrize(("name", "_expected"), SERIAL_SUFFIX_CASES)
def test_split_serial_suffix_is_idempotent(name: str, _expected: object) -> None:
    bare, _serial = split_serial_suffix(name)
    assert split_serial_suffix(bare) == (bare, None)


@pytest.mark.parametrize(("name", "expected"), IDENTITY_KEY_CASES)
def test_identity_key(name: str, expected: tuple[str, str]) -> None:
    assert identity_key(name) == expected


def test_a_source_hostname_always_wins_over_other_spellings() -> None:
    resolved = resolve_device_identities(
        ["sw2-dist.example.com", "sw2-dist(FOC1911X0GG)", "SW2-DIST"],
        ["sw2-dist"],
    )
    assert set(resolved.values()) == {"sw2-dist"}


@pytest.mark.parametrize(
    "spellings",
    [
        # NX-OS defaults to `hostname(SERIAL)` as its CDP device id and a plain system
        # name over LLDP, but the suffix has been observed on either protocol. Which one
        # carries it must not matter.
        ["nxos-core1(FDO21120U5D)", "nxos-core1"],
        ["nxos-core1", "nxos-core1(FDO21120U5D)"],
    ],
)
def test_either_protocol_may_be_the_one_carrying_the_serial(spellings: list[str]) -> None:
    assert set(resolve_device_identities(spellings, []).values()) == {"nxos-core1"}


def test_the_serial_suffix_never_reaches_the_canonical_name() -> None:
    # The only spelling ever seen carries the serial: it must still be stripped.
    resolved = resolve_device_identities(["nxos-core1(FDO21120U5D)"], [])
    assert resolved == {"nxos-core1(FDO21120U5D)": "nxos-core1"}


def test_a_short_spelling_and_an_fqdn_spelling_fold_together() -> None:
    resolved = resolve_device_identities(["esxi-host01", "esxi-host01.example.com"], [])
    assert set(resolved.values()) == {"esxi-host01"}


def test_an_only_ever_fqdn_neighbor_keeps_its_fqdn() -> None:
    # No shorter spelling was observed, so none may be invented.
    resolved = resolve_device_identities(["core-rtr.example.com"], [])
    assert resolved == {"core-rtr.example.com": "core-rtr.example.com"}


def test_two_domains_sharing_a_short_label_are_not_merged() -> None:
    resolved = resolve_device_identities(["sw1.site-a.com", "sw1.site-b.com"], [])
    assert resolved == {
        "sw1.site-a.com": "sw1.site-a.com",
        "sw1.site-b.com": "sw1.site-b.com",
    }


def test_two_source_devices_sharing_a_short_label_keep_their_own_identities() -> None:
    # Neither source can claim the label, so grouping falls back to per-domain.
    resolved = resolve_device_identities(
        ["sw1.site-a.com", "sw1.site-b.com"],
        ["sw1.site-a.com", "sw1.site-b.com"],
    )
    assert resolved == {
        "sw1.site-a.com": "sw1.site-a.com",
        "sw1.site-b.com": "sw1.site-b.com",
    }


def test_resolution_is_deterministic_regardless_of_input_order() -> None:
    spellings = ["esxi-host01.example.com", "ESXI-HOST01", "esxi-host01(FOC123)"]
    assert resolve_device_identities(spellings, []) == resolve_device_identities(
        list(reversed(spellings)), []
    )
