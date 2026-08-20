"""Tests for the device inventory (PROJECT_SPEC.md section 4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nettopo.ingest.inventory import InventoryError, load_inventory

EXPECTED = ("sw-core", "rtr-edge", "172.12.25.21", "sw-access-01")

TXT_INVENTORY = """# inventario.txt
sw-core
rtr-edge

172.12.25.21          # the access-layer stack's management address
sw-access-01
"""


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_line_format_reads_hostnames_and_addresses(tmp_path: Path) -> None:
    assert load_inventory(_write(tmp_path, "i.txt", TXT_INVENTORY)) == EXPECTED


def test_an_unrecognized_extension_is_read_as_lines(tmp_path: Path) -> None:
    assert load_inventory(_write(tmp_path, "devices.list", TXT_INVENTORY)) == EXPECTED


@pytest.mark.parametrize("name", ["i.yaml", "i.yml"])
def test_a_yaml_inventory_is_refused_by_name(tmp_path: Path, name: str) -> None:
    """YAML support was removed; the error must say so, not complain about the content."""
    path = _write(tmp_path, name, "- sw-core\n")
    with pytest.raises(InventoryError, match="no longer reads"):
        load_inventory(path)


def test_a_utf8_bom_does_not_swallow_the_first_device(tmp_path: Path) -> None:
    path = tmp_path / "i.txt"
    path.write_text(TXT_INVENTORY, encoding="utf-8-sig")
    assert load_inventory(path) == EXPECTED


def test_duplicate_entries_are_collected_once_in_file_order(tmp_path: Path) -> None:
    """A repeated line never means "connect and authenticate twice"."""
    path = _write(tmp_path, "i.txt", "sw-core\nrtr-edge\nsw-core\n")
    assert load_inventory(path) == ("sw-core", "rtr-edge")


def test_a_device_name_containing_whitespace_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path, "i.txt", "sw core\n")
    with pytest.raises(InventoryError, match="invalid device name"):
        load_inventory(path)


@pytest.mark.parametrize("content", ["", "# only a comment\n", "\n\n"])
def test_an_inventory_that_names_nothing_is_an_error(tmp_path: Path, content: str) -> None:
    """Better than silently starting a run against no devices."""
    with pytest.raises(InventoryError, match="names no devices"):
        load_inventory(_write(tmp_path, "i.txt", content))


def test_a_missing_file_is_reported_without_a_traceback(tmp_path: Path) -> None:
    with pytest.raises(InventoryError, match="cannot read inventory"):
        load_inventory(tmp_path / "nowhere.txt")
