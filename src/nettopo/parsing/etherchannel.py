"""Parser for `show etherchannel summary` / `show port-channel summary`.

The two commands print the same bundle-to-members table under different names: IOS and
IOS-XE call it `show etherchannel summary`, NX-OS calls it `show port-channel summary`,
and ntc-templates ships one template per spelling (never both for the same platform).
The capture itself says which one was run, so the prompt line picks the template rather
than the platform picking it.

This is what makes the L2 view's port-channel mode (`views/l2.py`) work against real
captures: it populates `Interface.po_id` on every bundle member and `Interface.po_members`
on the port-channel interface itself.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from ntc_templates.parse import ParsingException

from nettopo.parsing._textfsm import run_template
from nettopo.utils.command_sections import extract_command_output
from nettopo.utils.interfaces import looks_like_interface, normalize

logger = logging.getLogger("nettopo")

# Each pattern is paired with the ntc-templates command name it implies.
_COMMAND_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"show\s+ether\w*\s+sum\w*\s*$", re.IGNORECASE), "show etherchannel summary"),
    (re.compile(r"show\s+port-channel\s+sum\w*\s*$", re.IGNORECASE), "show port-channel summary"),
)

_PORT_CHANNEL_NAME = re.compile(r"^Po(?P<po_id>\d+)$")


@dataclass(frozen=True)
class PortChannelCapture:
    """One bundle as the device reports it, ready to merge into `Device.interfaces`."""

    name: str  # normalized port-channel name, e.g. "Po150"
    po_id: int
    members: tuple[str, ...]  # normalized member interface names


def parse_port_channels(raw_text: str, *, platform: str = "cisco_ios") -> list[PortChannelCapture]:
    """Parse the device's port-channel bundles, or return [] if it captured neither command."""
    for pattern, command in _COMMAND_PATTERNS:
        output = extract_command_output(raw_text, pattern)
        if output is None:
            continue
        return _to_captures(_run(platform=platform, command=command, data=output))
    return []


def _run(*, platform: str, command: str, data: str) -> list[dict[str, Any]]:
    """Run the template, downgrading a missing/unusable one to "no bundles known".

    A capture may pair a command spelling with a platform ntc-templates has no template
    for (an NX-OS capture parsed under the `cisco_ios` default, say). That is a capture
    or `--platform` problem, not a reason to abort the whole run.
    """
    try:
        return run_template(platform=platform, command=command, data=data)
    except ParsingException as exc:
        logger.warning("Skipping port-channel data: %s", exc)
        return []


def _to_captures(records: list[dict[str, Any]]) -> list[PortChannelCapture]:
    captures: list[PortChannelCapture] = []
    for record in records:
        name = normalize(str(record.get("bundle_name", "")))
        match = _PORT_CHANNEL_NAME.match(name)
        if match is None:
            continue
        captures.append(
            PortChannelCapture(
                name=name,
                po_id=int(match.group("po_id")),
                members=_members(record.get("member_interface", [])),
            )
        )
    return captures


def _members(raw_members: list[str]) -> tuple[str, ...]:
    """Normalize the member list, dropping NX-OS's "--" placeholder for an empty bundle."""
    normalized = (normalize(member) for member in raw_members if looks_like_interface(member))
    return tuple(dict.fromkeys(normalized))
