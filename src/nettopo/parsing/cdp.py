"""Parser for `show cdp neighbors detail` (PROJECT_SPEC.md section 4)."""

from __future__ import annotations

import re

from nettopo.model.entities import Link
from nettopo.parsing._textfsm import run_template
from nettopo.utils.command_sections import extract_command_output
from nettopo.utils.interfaces import normalize

_COMMAND_PATTERN = re.compile(r"show\s+cdp\s+neigh\w*\s+det\w*\s*$", re.IGNORECASE)


def parse_cdp(local_device: str, raw_text: str, *, platform: str = "cisco_ios") -> list[Link]:
    """Parse `local_device`'s CDP neighbors into `Link`s, local end first."""
    output = extract_command_output(raw_text, _COMMAND_PATTERN)
    if not output:
        return []

    records = run_template(platform=platform, command="show cdp neighbors detail", data=output)
    links: list[Link] = []
    for record in records:
        neighbor_name = record.get("neighbor_name", "").strip()
        local_interface = record.get("local_interface", "").strip()
        neighbor_interface = record.get("neighbor_interface", "").strip()
        if not (neighbor_name and local_interface and neighbor_interface):
            continue

        links.append(
            Link(
                local_device=local_device,
                local_interface=normalize(local_interface),
                remote_device=neighbor_name,
                remote_interface=normalize(neighbor_interface),
                discovery="cdp",
                remote_platform=record.get("platform") or None,
                remote_capabilities=(record.get("capabilities") or "").split(),
            )
        )
    return links
