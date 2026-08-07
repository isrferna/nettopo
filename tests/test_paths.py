"""Tests for path/filename safety helpers (PROJECT_SPEC.md section 11, path handling)."""

from __future__ import annotations

from pathlib import Path

from nettopo.utils.paths import resolve_output_root, safe_join, sanitize_filename_component


def test_sanitize_filename_component_strips_path_separators() -> None:
    assert "/" not in sanitize_filename_component("../../etc")
    assert "\\" not in sanitize_filename_component("..\\..\\windows")


def test_sanitize_filename_component_cannot_collapse_to_dot_segments() -> None:
    for malicious in ("../../etc", "..", ".", "....//....//etc"):
        result = sanitize_filename_component(malicious)
        assert result not in (".", "..")


def test_sanitize_filename_component_strips_quotes_and_whitespace() -> None:
    assert sanitize_filename_component('sw1"; rm -rf') == "sw1_;_rm_-rf"


def test_sanitize_filename_component_falls_back_when_nothing_safe_remains() -> None:
    assert sanitize_filename_component("../..") == "unknown"
    assert sanitize_filename_component("") == "unknown"


def test_sanitize_filename_component_leaves_normal_hostnames_untouched() -> None:
    assert sanitize_filename_component("sw1-access") == "sw1-access"


def test_resolve_output_root_creates_missing_directories(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "output"
    resolved = resolve_output_root(target)
    assert resolved.is_dir()
    assert resolved == target.resolve()


def test_safe_join_with_a_malicious_hostname_stays_inside_root(tmp_path: Path) -> None:
    root = resolve_output_root(tmp_path)
    joined = safe_join(root, "../../etc", "devices.csv")
    assert root in joined.parents or joined == root


def test_safe_join_with_repeated_dot_dot_components_stays_inside_root(tmp_path: Path) -> None:
    root = resolve_output_root(tmp_path)
    joined = safe_join(root, "..", "..", "etc", "passwd")
    assert root in joined.parents or joined == root
