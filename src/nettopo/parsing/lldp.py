"""Parser for `show lldp neighbors detail` (PROJECT_SPEC.md section 4).

LLDP is also the only protocol that reports a neighbor's chassis MAC, which CDP has no
equivalent for. That address is what lets the STP view name a root bridge sitting outside
the captures, by matching it against the root address `show spanning-tree` reports.
"""

from __future__ import annotations

import re

from nettopo.model.entities import Link
from nettopo.parsing._textfsm import run_template
from nettopo.utils.command_sections import extract_command_output
from nettopo.utils.interfaces import looks_like_interface, normalize

_COMMAND_PATTERN = re.compile(r"show\s+lldp\s+neigh\w*\s+det\w*\s*$", re.IGNORECASE)


def parse_lldp(local_device: str, raw_text: str, *, platform: str = "cisco_ios") -> list[Link]:
    """Parse `local_device`'s LLDP neighbors into `Link`s, local end first."""
    output = extract_command_output(raw_text, _COMMAND_PATTERN)
    if not output:
        return []

    records = run_template(platform=platform, command="show lldp neighbors detail", data=output)
    links: list[Link] = []
    for record in records:
        neighbor_name = record.get("neighbor_name", "").strip()
        local_interface = record.get("local_interface", "").strip()
        neighbor_interface = _neighbor_interface(
            description=record.get("neighbor_interface", "").strip(),
            port_id=record.get("neighbor_port_id", "").strip(),
        )
        if not (neighbor_name and local_interface and neighbor_interface):
            continue

        links.append(
            Link(
                local_device=local_device,
                local_interface=normalize(local_interface),
                remote_device=neighbor_name,
                remote_interface=normalize(neighbor_interface),
                discovery="lldp",
                remote_platform=record.get("platform") or None,
                remote_mgmt_ip=record.get("mgmt_address") or None,
                remote_chassis_id=record.get("chassis_id", "").strip() or None,
                remote_capabilities=(record.get("capabilities") or "").replace(",", " ").split(),
            )
        )
    return links


def _neighbor_interface(*, description: str, port_id: str) -> str:
    """Pick whichever LLDP field actually names the neighbor's port.

    IOS reports the port name in "Port Description" and often a MAC address or an
    already-short name in "Port id", so the description is preferred. NX-OS instead puts
    the port's *configured description* ("uplink-to-acc-sw1") there, which correlates
    with nothing: the same physical link then reads differently in CDP and LLDP and
    survives de-duplication as a second, bogus edge. Whichever field looks like an
    interface name wins; the description keeps its historical precedence otherwise.
    """
    if looks_like_interface(description):
        return description
    if looks_like_interface(port_id):
        return port_id
    return description or port_id
