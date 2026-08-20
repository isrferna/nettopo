"""Reads the device list `nettopo collect` works from (PROJECT_SPEC.md section 4).

An inventory is a flat list of devices, each named by hostname or IP, one device per line.
It carries no credentials and no per-device variables -- credentials are prompted for at
run time and never stored, which is the whole reason this file has nothing worth
encrypting in it.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

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
    and the user never sees an `OSError` traceback.
    """
    inventory_path = Path(path).expanduser()

    # Refused by name rather than misread line by line: a YAML list would fail the
    # whitespace check below with a message that says nothing about why.
    if inventory_path.suffix.lower() in _YAML_SUFFIXES:
        raise InventoryError(
            f"inventory '{inventory_path}' looks like YAML, which nettopo no longer "
            "reads; list one device per line in a plain text file instead"
        )

    try:
        text = inventory_path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise InventoryError(f"cannot read inventory '{inventory_path}': {exc}") from exc

    devices = _deduplicate(_validated(_parse_lines(text), inventory_path))
    if not devices:
        raise InventoryError(f"inventory '{inventory_path}' names no devices")
    return devices


def _parse_lines(text: str) -> list[str]:
    """One device per line; `#` starts a comment, whole-line or trailing."""
    return [stripped for line in text.splitlines() if (stripped := _COMMENT.sub("", line).strip())]


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
