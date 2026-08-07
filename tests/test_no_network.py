"""Zero-network-connections guarantee (PROJECT_SPEC.md section 11).

Monkeypatches `socket.socket` to fail and asserts `nettopo parse` still succeeds on a
fixture capture set — proving no code path in ingestion, parsing, model population, or
CSV export opens a socket. This is a verifiable guarantee, not a promise in prose.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from nettopo.cli import main

CAPTURES = Path(__file__).parent / "fixtures" / "captures"


def _deny_all_sockets(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("nettopo attempted to open a network socket")


def test_parse_command_makes_zero_network_connections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(socket, "socket", _deny_all_sockets)

    exit_code = main(["parse", "-i", str(CAPTURES), "-o", str(tmp_path / "output")])

    assert exit_code == 0
    assert (tmp_path / "output" / "csv" / "devices.csv").exists()


def test_l2_command_makes_zero_network_connections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Phase 3 adds N2G/igraph-backed rendering to the `l2` command; verify that new
    # code path is covered by the same zero-network-connections guarantee rather than
    # waiting for Phase 7's `all` command per the original plan in docs/architecture.md.
    monkeypatch.setattr(socket, "socket", _deny_all_sockets)

    exit_code = main(["l2", "-i", str(CAPTURES), "-o", str(tmp_path / "output")])

    assert exit_code == 0
    assert (tmp_path / "output" / "l2" / "l2_full.drawio").exists()


def test_stp_command_makes_zero_network_connections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(socket, "socket", _deny_all_sockets)

    exit_code = main(["stp", "-i", str(CAPTURES), "-o", str(tmp_path / "output"), "--vlan", "10"])

    assert exit_code == 0
    assert (tmp_path / "output" / "stp" / "stp_vlan10.drawio").exists()
