"""Phase 0 tests: the CLI skeleton parses arguments correctly but implements no logic yet."""

from __future__ import annotations

import pytest

from nettopo.cli import build_parser, main

EXPECTED_COMMANDS = {"parse", "l2", "stp", "hsrp", "bgp", "all"}


@pytest.mark.parametrize("command", sorted(EXPECTED_COMMANDS))
def test_every_subcommand_accepts_required_input_argument(command: str) -> None:
    parser = build_parser()
    args = parser.parse_args([command, "-i", "."])
    assert args.command == command


def test_help_exits_cleanly() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["--help"])
    assert excinfo.value.code == 0


def test_subcommand_requires_input_argument() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["l2"])
    assert excinfo.value.code == 2


def test_vlan_and_group_mode_are_mutually_exclusive() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["stp", "-i", ".", "--vlan", "10", "--group-mode", "strict"])
    assert excinfo.value.code == 2


@pytest.mark.parametrize("command", sorted(EXPECTED_COMMANDS))
def test_every_command_reports_not_implemented(command: str) -> None:
    exit_code = main([command, "-i", "."])
    assert exit_code == 1
