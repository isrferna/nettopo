"""Tests for the multi-command capture splitter (PROJECT_SPEC.md section 4)."""

from __future__ import annotations

import re

import pytest

from nettopo.utils.command_sections import (
    extract_command_output,
    first_prompt_hostname,
    format_command_section,
)

_CAPTURE = """sw1#show version
Cisco IOS Software, Version 15.2(7)E3

sw1#show vlan brief
1    default    active
"""


def test_extract_command_output_returns_only_that_commands_block() -> None:
    output = extract_command_output(_CAPTURE, re.compile(r"show\s+version"))
    assert output == "Cisco IOS Software, Version 15.2(7)E3"


def test_extract_command_output_reads_to_eof_for_the_last_command() -> None:
    output = extract_command_output(_CAPTURE, re.compile(r"show\s+vlan\s+brief"))
    assert output == "1    default    active"


def test_extract_command_output_returns_none_when_command_absent() -> None:
    assert extract_command_output(_CAPTURE, re.compile(r"show\s+cdp\s+neighbors\s+detail")) is None


def test_first_prompt_hostname_reads_the_first_prompt_line() -> None:
    assert first_prompt_hostname(_CAPTURE) == "sw1"


def test_first_prompt_hostname_returns_none_without_a_prompt_line() -> None:
    assert first_prompt_hostname("just some free text\nwith no prompt line\n") is None


def test_format_command_section_round_trips_through_the_extractor() -> None:
    """The writer and the reader must agree; this is the property that binds them."""
    output = "Cisco IOS Software, Version 15.2(7)E3\nuptime is 3 weeks"
    section = format_command_section("sw1", "show version", output)

    assert extract_command_output(section, re.compile(r"show\s+version")) == output


@pytest.mark.parametrize(
    ("command", "pattern"),
    [
        ("show version", r"show\s+ver(?:sion)?\s*$"),
        ("show cdp neighbors detail", r"show\s+cdp\s+neigh\w*\s+det\w*\s*$"),
        ("show lldp neighbors detail", r"show\s+lldp\s+neigh\w*\s+det\w*\s*$"),
        ("show ip interface brief", r"show\s+ip\s+int\w*\s+br\w*\s*$"),
        ("show interfaces", r"show\s+int\w*\s*$"),
        ("show vlan brief", r"show\s+vlan(?:\s+br\w*)?\s*$"),
        ("show spanning-tree", r"show\s+span\w*(?:-tree)?\s*$"),
        ("show standby brief", r"show\s+standby\s+br\w*\s*$"),
        ("show etherchannel summary", r"show\s+etherchannel\s+sum\w*\s*$"),
        ("show port-channel summary", r"show\s+port-channel\s+sum\w*\s*$"),
        ("show ip bgp summary", r"show\s+ip\s+bgp\s+(?:all\s+)?sum\w*\s*$"),
    ],
)
def test_every_collected_command_is_found_by_its_parsers_pattern(
    command: str, pattern: str
) -> None:
    """A command a collector sends must be one its parser can find again."""
    section = format_command_section("sw1", command, "some output")

    assert extract_command_output(section, re.compile(pattern, re.IGNORECASE)) == "some output"


def test_joined_sections_split_back_into_their_parts() -> None:
    capture = "".join(
        (
            format_command_section("sw1", "show version", "version output"),
            format_command_section("sw1", "show vlan brief", "vlan output"),
        )
    )

    assert extract_command_output(capture, re.compile(r"show\s+version")) == "version output"
    assert extract_command_output(capture, re.compile(r"show\s+vlan\s+brief")) == "vlan output"


def test_format_command_section_normalizes_crlf_line_endings() -> None:
    section = format_command_section("sw1", "show version", "line one\r\nline two")

    assert "\r" not in section
    assert extract_command_output(section, re.compile(r"show\s+version")) == "line one\nline two"


@pytest.mark.parametrize("hostname", ["sw 1", "", "sw\t1", "sw\n1"])
def test_format_command_section_refuses_a_hostname_that_would_break_the_format(
    hostname: str,
) -> None:
    """`_PROMPT_LINE` matches `\\S+`, so whitespace here would silently corrupt the file."""
    with pytest.raises(ValueError, match="single non-empty token"):
        format_command_section(hostname, "show version", "output")
