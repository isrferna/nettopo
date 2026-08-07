"""Typed wrapper around `ntc_templates.parse_output` (which ships no type stubs).

Every parser goes through this instead of calling `ntc_templates` directly, so the
untyped-import boundary exists in exactly one place.
"""

from __future__ import annotations

from typing import Any, cast

from ntc_templates.parse import parse_output


def run_template(*, platform: str, command: str, data: str) -> list[dict[str, Any]]:
    """Run a TextFSM template and return its records.

    Most fields are plain strings, but a template's `List`-typed values (e.g. `show
    version`'s HARDWARE/SERIAL/MAC_ADDRESS) come back as `list[str]`, so callers reading
    one of those must annotate accordingly rather than assume `str`.
    """
    records = parse_output(platform=platform, command=command, data=data)
    return cast(list[dict[str, Any]], records)
