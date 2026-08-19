"""Tests for `show version` parsing (PROJECT_SPEC.md section 4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nettopo.parsing.version import detect_os, parse_version

FIXTURES = Path(__file__).parent / "fixtures" / "version"


def _wrap(command_output_path: Path) -> str:
    return f"router#show version\n{command_output_path.read_text()}"


def test_parse_version_ios() -> None:
    info = parse_version(_wrap(FIXTURES / "ios_show_version.txt"))
    assert info is not None
    assert info.hostname == "sw1-access"
    assert info.model == "WS-C2960X-24TS-L"
    assert info.platform == "cisco WS-C2960X-24TS-L"
    assert info.os == "ios"


def test_parse_version_iosxe() -> None:
    info = parse_version(_wrap(FIXTURES / "iosxe_show_version.txt"))
    assert info is not None
    assert info.hostname == "sw2-dist"
    assert info.model == "C9300-24P"
    assert info.os == "ios-xe"


def test_parse_version_returns_none_when_command_absent() -> None:
    assert parse_version("router#show clock\n10:00:00 UTC\n") is None


@pytest.mark.parametrize(
    ("fixture_name", "expected_os"),
    [("ios_show_version.txt", "ios"), ("iosxe_show_version.txt", "ios-xe")],
)
def test_detect_os_classifies_the_captured_platforms(fixture_name: str, expected_os: str) -> None:
    """Public because the collector needs the answer before any template can be chosen."""
    assert detect_os((FIXTURES / fixture_name).read_text()) == expected_os


def test_detect_os_recognizes_nxos() -> None:
    """Inline rather than a fixture: there is no NX-OS `show version` capture in the tree,
    and `detect_os` reads one banner line, so a whole chassis dump would prove nothing more."""
    banner = "Cisco Nexus Operating System (NX-OS) Software\n  system: version 9.3(8)"
    assert detect_os(banner) == "nxos"


def test_detect_os_falls_back_to_ios_for_unrecognized_output() -> None:
    assert detect_os("something that mentions no platform at all") == "ios"
