"""Zero-network-connections guarantee (PROJECT_SPEC.md section 11).

Monkeypatches `socket.socket` to fail and asserts every command still succeeds on a
fixture capture set — proving no code path in ingestion, parsing, model population,
rendering or CSV export opens a socket. This is a verifiable guarantee, not a promise in
prose. `nettopo all` is the one that makes it exhaustive: it drives every view and every
export in a single run, so a socket opened anywhere in the tool fails this test.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from nettopo.cli import main

CAPTURES = Path(__file__).parent / "fixtures" / "captures"
HSRP_TOPOLOGY = Path(__file__).parent / "fixtures" / "hsrp_topology"
BGP_TOPOLOGY = Path(__file__).parent / "fixtures" / "bgp_topology"
CAMPUS = Path(__file__).parent.parent / "examples" / "campus"


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


def test_hsrp_command_makes_zero_network_connections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(socket, "socket", _deny_all_sockets)

    exit_code = main(["hsrp", "-i", str(HSRP_TOPOLOGY), "-o", str(tmp_path / "output"), "--all"])

    assert exit_code == 0
    assert (tmp_path / "output" / "hsrp" / "hsrp_vlan10.drawio").exists()


def test_bgp_command_makes_zero_network_connections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(socket, "socket", _deny_all_sockets)

    exit_code = main(["bgp", "-i", str(BGP_TOPOLOGY), "-o", str(tmp_path / "output")])

    assert exit_code == 0
    assert (tmp_path / "output" / "bgp" / "bgp.drawio").exists()


def test_all_command_makes_zero_network_connections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exhaustive case: every view and every export, in one run, with no sockets.

    Two capture sets, because no single one covers all four views: `examples/campus/`
    exercises the CSV tables and the L2, STP and HSRP renderers, and `bgp_topology/` the
    BGP renderer.
    """
    monkeypatch.setattr(socket, "socket", _deny_all_sockets)

    campus_output = tmp_path / "campus"
    bgp_output = tmp_path / "bgp"
    assert main(["all", "-i", str(CAMPUS), "-o", str(campus_output)]) == 0
    assert main(["all", "-i", str(BGP_TOPOLOGY), "-o", str(bgp_output)]) == 0

    assert (campus_output / "csv" / "devices.csv").exists()
    assert (campus_output / "l2" / "l2_full_port-channels.drawio").exists()
    assert (campus_output / "stp" / "stp_vlan10.drawio").exists()
    assert (campus_output / "hsrp" / "hsrp_vlan10.drawio").exists()
    assert (bgp_output / "bgp" / "bgp.drawio").exists()
