"""Tests for the package version string."""

from __future__ import annotations

from importlib.metadata import version

import pytest

import nettopo
from nettopo.cli import build_parser, main


def test_version_is_read_from_the_installed_distribution() -> None:
    # `__version__` was hardcoded and drifted from `pyproject.toml` (0.0.1 vs 0.2.0)
    # from the Phase 0 scaffolding until v0.3.0rc1. Deriving it is the fix; this test
    # is what stops a future edit from hardcoding it again.
    assert nettopo.__version__ == version("nettopo")


def test_cli_version_flag_reports_the_package_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])

    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == f"nettopo {nettopo.__version__}"


def test_cli_version_flag_does_not_require_a_subcommand() -> None:
    # `--version` has to short-circuit before argparse enforces the required subcommand,
    # otherwise `nettopo --version` would exit 2 asking for one.
    with pytest.raises(SystemExit) as excinfo:
        build_parser().parse_args(["--version"])
    assert excinfo.value.code == 0
