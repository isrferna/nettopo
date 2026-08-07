"""Tests for `show version` parsing (PROJECT_SPEC.md section 4)."""

from __future__ import annotations

from pathlib import Path

from nettopo.parsing.version import parse_version

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
