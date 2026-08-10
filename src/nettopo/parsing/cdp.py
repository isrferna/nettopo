"""Parser for `show cdp neighbors detail` (PROJECT_SPEC.md section 4).

CDP prints two different addresses per neighbor and the ntc-templates templates disagree
about which one they expose. `cisco_nxos` reads `Mgmt address(es)` into `MGMT_ADDRESS`
and keeps the interface address in a separate field; `cisco_ios` reads `Entry address(es)`
-- the address of the neighbor's *connected interface* -- into the identically named
field and never looks at `Management address(es)` at all. Those are routinely different
subnets (a link address vs. an out-of-band management network), so taking the templates'
`mgmt_address` at face value would put a link address in `Device.mgmt_ip` on IOS. The
management block is therefore read here directly, and the template's value is used only
as a fallback for neighbors that advertise no management address.
"""

from __future__ import annotations

import re

from nettopo.model.entities import Link
from nettopo.parsing._textfsm import run_template
from nettopo.utils.command_sections import extract_command_output
from nettopo.utils.interfaces import normalize

_COMMAND_PATTERN = re.compile(r"show\s+cdp\s+neigh\w*\s+det\w*\s*$", re.IGNORECASE)

# Entry headers sit at column 0 and their values are indented under them; IOS spells the
# management block "Management address(es):" where NX-OS spells it "Mgmt address(es):".
_DEVICE_ID_PATTERN = re.compile(r"Device\s+ID\s*:\s*(?P<device_id>\S+)", re.IGNORECASE)
_MANAGEMENT_HEADER_PATTERN = re.compile(r"(?:Management|Mgmt)\s+address\(es\)\s*:", re.IGNORECASE)
_IP_ADDRESS_PATTERN = re.compile(
    r"IP(?:v4)?\s+address\s*:\s*(?P<ip>\d{1,3}(?:\.\d{1,3}){3})", re.IGNORECASE
)


def parse_cdp(local_device: str, raw_text: str, *, platform: str = "cisco_ios") -> list[Link]:
    """Parse `local_device`'s CDP neighbors into `Link`s, local end first."""
    output = extract_command_output(raw_text, _COMMAND_PATTERN)
    if not output:
        return []

    records = run_template(platform=platform, command="show cdp neighbors detail", data=output)
    management_ips = _management_ips(output)
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
                remote_mgmt_ip=management_ips.get(neighbor_name)
                or record.get("mgmt_address")
                or None,
                remote_capabilities=(record.get("capabilities") or "").split(),
            )
        )
    return links


def _management_ips(output: str) -> dict[str, str]:
    """Map each entry's device id to the address in its management block, if it has one.

    Keyed by device id because that is what the `cisco_ios` template reports as the
    neighbor name. NX-OS names its entries by `System Name` instead, so lookups miss
    there and the caller falls back to the template's `mgmt_address` -- which on that
    platform already *is* the management address.
    """
    management_ips: dict[str, str] = {}
    device_id: str | None = None
    in_management_block = False

    for line in output.splitlines():
        if not line.strip():
            continue
        if not line[:1].isspace():
            device_match = _DEVICE_ID_PATTERN.match(line)
            if device_match:
                device_id = device_match.group("device_id")
            in_management_block = _MANAGEMENT_HEADER_PATTERN.match(line) is not None
            continue

        ip_match = _IP_ADDRESS_PATTERN.search(line)
        if in_management_block and device_id is not None and ip_match:
            management_ips.setdefault(device_id, ip_match.group("ip"))
            in_management_block = False

    return management_ips
