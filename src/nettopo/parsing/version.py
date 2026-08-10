"""Parser for `show version`: platform/model/os detection (PROJECT_SPEC.md section 4).

Determines the device's hostname, model, and OS family so ingestion can pick the right
ntc-templates platform for the remaining parsers and correlate this device's own capture
with mentions of it in neighbors' CDP/LLDP output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from nettopo.parsing._textfsm import run_template
from nettopo.utils.command_sections import extract_command_output

_COMMAND_PATTERN = re.compile(r"show\s+ver(?:sion)?\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class VersionInfo:
    hostname: str | None
    platform: str | None  # raw: "cisco C9300-24P"
    model: str | None  # parsed: "C9300-24P"
    os: str | None  # "ios" | "ios-xe" | "nxos"
    serial: str | None  # chassis serial, when the platform prints one


def parse_version(raw_text: str, *, platform: str = "cisco_ios") -> VersionInfo | None:
    """Parse this device's own `show version` output, if present in `raw_text`."""
    output = extract_command_output(raw_text, _COMMAND_PATTERN)
    if not output:
        return None

    records = run_template(platform=platform, command="show version", data=output)
    if not records:
        return None

    record = records[0]
    # HARDWARE and SERIAL are `List`-typed in the template: one entry per stack member.
    # The first is the master, which is the chassis this capture speaks for.
    hardware: list[str] = record.get("hardware") or []
    serials: list[str] = record.get("serial") or []
    model = hardware[0] if hardware else None

    return VersionInfo(
        hostname=record.get("hostname") or None,
        platform=f"cisco {model}" if model else None,
        model=model,
        os=_detect_os(output),
        serial=serials[0] if serials else None,
    )


def _detect_os(version_output: str) -> str:
    lowered = version_output.lower()
    if "nx-os" in lowered:
        return "nxos"
    if "ios xe" in lowered or "ios-xe" in lowered:
        return "ios-xe"
    return "ios"
