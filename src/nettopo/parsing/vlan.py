"""Parser for `show vlan brief` (PROJECT_SPEC.md section 4)."""

from __future__ import annotations

import re

from nettopo.model.entities import Vlan
from nettopo.parsing._textfsm import run_template
from nettopo.utils.command_sections import extract_command_output

_COMMAND_PATTERN = re.compile(r"show\s+vlan(?:\s+br\w*)?\s*$", re.IGNORECASE)


def parse_vlans(raw_text: str, *, platform: str = "cisco_ios") -> list[Vlan]:
    output = extract_command_output(raw_text, _COMMAND_PATTERN)
    if not output:
        return []

    records = run_template(platform=platform, command="show vlan brief", data=output)
    return [
        Vlan(
            vlan_id=int(record["vlan_id"]),
            name=record.get("vlan_name") or None,
            status=record.get("status") or None,
        )
        for record in records
    ]
