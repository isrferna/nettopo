"""Tests for the package version string."""

from __future__ import annotations

from importlib.metadata import version

import nettopo


def test_version_is_read_from_the_installed_distribution() -> None:
    # `__version__` was hardcoded and drifted from `pyproject.toml` (0.0.1 vs 0.2.0)
    # from the Phase 0 scaffolding until v0.3.0rc1. Deriving it is the fix; this test
    # is what stops a future edit from hardcoding it again.
    assert nettopo.__version__ == version("nettopo")
