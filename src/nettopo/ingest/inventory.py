"""Reads the device list `nettopo collect` works from (PROJECT_SPEC.md section 4).

An inventory is a flat list of devices, each named by hostname or IP. Two syntaxes are
accepted for the same content: one device per line (`.txt`, and anything unrecognized),
or a YAML list (`.yaml`, `.yml`). It carries no credentials and no per-device variables --
credentials are prompted for at run time and never stored, which is the whole reason this
file has nothing worth encrypting in it.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml

logger = logging.getLogger("nettopo")

_COMMENT = re.compile(r"#.*$")
_WHITESPACE = re.compile(r"\s")
_YAML_SUFFIXES = frozenset({".yaml", ".yml"})


class InventoryError(ValueError):
    """The inventory could not be read, or named no usable device."""


def load_inventory(path: str | Path) -> tuple[str, ...]:
    """Return the devices `path` names, in file order, without duplicates.

    Raises `InventoryError` for every failure -- an unreadable file, a malformed
    document, or one that names nothing -- so the CLI has a single exception to report
    and the user never sees a `yaml.YAMLError` or an `OSError` traceback.
    """
    inventory_path = Path(path).expanduser()
    try:
        text = inventory_path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise InventoryError(f"cannot read inventory '{inventory_path}': {exc}") from exc

    if inventory_path.suffix.lower() in _YAML_SUFFIXES:
        entries = _parse_yaml(text, inventory_path)
    else:
        entries = _parse_lines(text)

    devices = _deduplicate(_validated(entries, inventory_path))
    if not devices:
        raise InventoryError(f"inventory '{inventory_path}' names no devices")
    return devices


def _parse_lines(text: str) -> list[str]:
    """One device per line; `#` starts a comment, whole-line or trailing."""
    return [stripped for line in text.splitlines() if (stripped := _COMMENT.sub("", line).strip())]


def _parse_yaml(text: str, path: Path) -> list[str]:
    """A flat YAML list of the same device names the line format holds.

    `safe_load` only, never `yaml.load` (PROJECT_SPEC.md section 11): an inventory is
    ordinary user data and must not be able to construct arbitrary Python objects.
    """
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise InventoryError(f"inventory '{path}' is not valid YAML: {exc}") from exc

    if document is None:
        return []
    if not isinstance(document, list):
        raise InventoryError(
            f"inventory '{path}' must be a flat list of devices, "
            f"but its top level is a {type(document).__name__}"
        )
    return [_yaml_entry(entry, path) for entry in document]


def _yaml_entry(entry: object, path: Path) -> str:
    """Accept a device name; refuse the Ansible-style mapping people will reach for.

    Named explicitly because `- sw1: {ansible_host: ...}` is the obvious thing to try for
    anyone coming from Ansible, and a bare type name in the error would not tell them
    that the omission is deliberate.
    """
    if isinstance(entry, dict):
        raise InventoryError(
            f"inventory '{path}' contains a mapping where a device name was expected; "
            "nettopo inventories are a flat list of hostnames or IPs, with no per-device "
            "variables -- credentials are prompted for at run time"
        )
    if not isinstance(entry, str):
        raise InventoryError(
            f"inventory '{path}' contains a {type(entry).__name__} where a device name was expected"
        )
    return entry.strip()


def _validated(entries: list[str], path: Path) -> list[str]:
    """A device name is anything non-empty without internal whitespace.

    Nothing stricter: the entry may be a hostname, an FQDN or an IP, and validating it
    further here would only reject addressing schemes that resolve perfectly well.
    """
    for entry in entries:
        if not entry or _WHITESPACE.search(entry):
            raise InventoryError(f"inventory '{path}' contains an invalid device name: {entry!r}")
    return entries


def _deduplicate(entries: list[str]) -> tuple[str, ...]:
    """Keep the first occurrence of each device, in file order.

    Collecting the same device twice would connect twice, authenticate twice, and write
    one file over the other -- never what a repeated line means.
    """
    seen: dict[str, None] = {}
    for entry in entries:
        if entry in seen:
            logger.debug("Inventory names '%s' more than once; collecting it once.", entry)
            continue
        seen[entry] = None
    return tuple(seen)
