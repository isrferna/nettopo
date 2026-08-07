"""Tests for the multi-command capture splitter (PROJECT_SPEC.md section 4)."""

from __future__ import annotations

import re

from nettopo.utils.command_sections import extract_command_output, first_prompt_hostname

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
