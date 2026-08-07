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
