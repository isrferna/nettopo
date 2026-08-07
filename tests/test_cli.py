"""CLI tests: argument parsing for every subcommand, plus the `parse` command's
ingest -> model -> CSV pipeline (PROJECT_SPEC.md sections 4, 8, 9)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nettopo.cli import build_parser, main

ALL_COMMANDS = {"parse", "l2", "stp", "hsrp", "bgp", "all"}
UNIMPLEMENTED_COMMANDS = ALL_COMMANDS - {"parse", "l2"}

CAPTURES = Path(__file__).parent / "fixtures" / "captures"


@pytest.mark.parametrize("command", sorted(ALL_COMMANDS))
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


@pytest.mark.parametrize("command", sorted(UNIMPLEMENTED_COMMANDS))
def test_unimplemented_commands_report_not_implemented(command: str, tmp_path: Path) -> None:
    exit_code = main([command, "-i", str(tmp_path)])
    assert exit_code == 1


def test_parse_command_writes_every_csv_table(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    exit_code = main(["parse", "-i", str(CAPTURES), "-o", str(output_dir)])

    assert exit_code == 0
    csv_dir = output_dir / "csv"
    for name in ("devices.csv", "interfaces.csv", "neighbors.csv", "vlans.csv"):
        assert (csv_dir / name).exists()


def test_parse_command_fails_cleanly_on_a_missing_input_directory(tmp_path: Path) -> None:
    exit_code = main(["parse", "-i", str(tmp_path / "does-not-exist")])
    assert exit_code == 1


def test_l2_command_writes_the_full_diagram_by_default(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    exit_code = main(["l2", "-i", str(CAPTURES), "-o", str(output_dir)])

    assert exit_code == 0
    assert (output_dir / "l2" / "l2_full.drawio").exists()
    assert not (output_dir / "l2" / "l2_network-only.drawio").exists()


def test_l2_command_endpoints_network_only_writes_the_other_filename(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    exit_code = main(
        ["l2", "-i", str(CAPTURES), "-o", str(output_dir), "--endpoints", "network-only"]
    )

    assert exit_code == 0
    assert (output_dir / "l2" / "l2_network-only.drawio").exists()


def test_l2_command_fails_cleanly_on_a_missing_input_directory(tmp_path: Path) -> None:
    exit_code = main(["l2", "-i", str(tmp_path / "does-not-exist")])
    assert exit_code == 1
