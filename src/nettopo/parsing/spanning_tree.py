"""Parser for `show spanning-tree` (per-VLAN Rapid-PVST, PROJECT_SPEC.md section 4).

ntc-templates' `cisco_ios_show_spanning-tree` template only captures the per-interface
role/state/cost table -- it does not capture the "Root ID"/"Bridge ID" blocks that carry
the bridge priority, MAC, and root-election flag the data model needs (`StpBridge`,
PROJECT_SPEC.md section 6). Both blocks are simple, stable, line-anchored text, so this
parser reads the full command output with its own regexes instead of round-tripping
through TextFSM for only part of the data.

IOS and IOS-XE emit this command in the same format (unlike `show version`, which does
differ enough to need OS detection -- see `parsing/version.py`), so one parser serves
both; `tests/fixtures/spanning_tree/` carries a fixture for each to prove that.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from nettopo.model.entities import StpBridge, StpPort, StpRole, StpState
from nettopo.utils.command_sections import extract_command_output
from nettopo.utils.interfaces import normalize

_COMMAND_PATTERN = re.compile(r"show\s+span\w*(?:-tree)?\s*$", re.IGNORECASE)

_VLAN_HEADER = re.compile(r"^VLAN(?P<vlan_id>\d+)\s*$", re.MULTILINE)

_ROOT_ID_BLOCK = re.compile(
    r"Root ID\s+Priority\s+\d+\s*\n"
    r"\s*Address\s+(?P<root_address>[0-9A-Fa-f.]+)\s*\n"
    r"(?P<is_root>\s*This bridge is the root\s*\n)?"
)
_BRIDGE_ID_BLOCK = re.compile(
    r"Bridge ID\s+Priority\s+\d+\s+\(priority\s+(?P<base_priority>\d+)\s+"
    r"sys-id-ext\s+(?P<sys_id_ext>\d+)\)\s*\n"
    r"\s*Address\s+(?P<bridge_address>[0-9A-Fa-f.]+)"
)
_PORT_TABLE_HEADER = re.compile(
    r"^Interface\s+Role\s+Sts\s+Cost\s+Prio\.Nbr\s+Type\s*$", re.MULTILINE
)
# IOS marks an inconsistent port by gluing the reason onto the state ("BKN*ROOT_Inc",
# "BKN*PVID_Inc"), so the state is read as letters plus an optional starred suffix rather
# than as a whole whitespace-delimited field. Requiring a space there instead drops the
# entire row -- the bridge is still created but its ports are not, which silently costs
# the STP view every link through that port.
_PORT_ROW = re.compile(
    r"^(?P<interface>\S+)\s+(?P<role>[A-Za-z]+)\s+(?P<state>[A-Za-z]+)(?:\*\S*)?\s+"
    r"(?P<cost>\d+)\s+\S+\s+(?P<link_type>\S.*?)\s*$"
)

_ROLE_BY_ABBREVIATION: dict[str, StpRole] = {
    "root": StpRole.ROOT,
    "desg": StpRole.DESIGNATED,
    "altn": StpRole.ALTERNATE,
    "back": StpRole.BACKUP,
    "disb": StpRole.DISABLED,
}
_STATE_BY_ABBREVIATION: dict[str, StpState] = {
    "fwd": StpState.FWD,
    "blk": StpState.BLK,
    "lrn": StpState.LRN,
    "lis": StpState.LIS,
    "dis": StpState.DIS,
    "bkn": StpState.BKN,
}


@dataclass(frozen=True)
class StpVlanCapture:
    """One device's view of one VLAN's spanning tree, ready to merge into a `StpVlan`."""

    vlan: int
    bridge: StpBridge
    ports: tuple[StpPort, ...]


def parse_spanning_tree(local_device: str, raw_text: str) -> list[StpVlanCapture]:
    """Parse `local_device`'s `show spanning-tree` output into per-VLAN captures."""
    output = extract_command_output(raw_text, _COMMAND_PATTERN)
    if not output:
        return []

    headers = list(_VLAN_HEADER.finditer(output))
    captures: list[StpVlanCapture] = []
    for index, header in enumerate(headers):
        start = header.end()
        end = headers[index + 1].start() if index + 1 < len(headers) else len(output)
        capture = _parse_vlan_block(local_device, int(header.group("vlan_id")), output[start:end])
        if capture is not None:
            captures.append(capture)
    return captures


def _parse_vlan_block(local_device: str, vlan_id: int, block: str) -> StpVlanCapture | None:
    root_match = _ROOT_ID_BLOCK.search(block)
    bridge_match = _BRIDGE_ID_BLOCK.search(block)
    if root_match is None or bridge_match is None:
        return None

    bridge = StpBridge(
        device=local_device,
        vlan=vlan_id,
        base_priority=int(bridge_match.group("base_priority")),
        sys_id_ext=int(bridge_match.group("sys_id_ext")),
        mac=bridge_match.group("bridge_address"),
        is_root=root_match.group("is_root") is not None,
        root_mac=root_match.group("root_address"),
    )
    return StpVlanCapture(
        vlan=vlan_id, bridge=bridge, ports=tuple(_parse_ports(local_device, vlan_id, block))
    )


def _parse_ports(local_device: str, vlan_id: int, block: str) -> list[StpPort]:
    header_match = _PORT_TABLE_HEADER.search(block)
    if header_match is None:
        return []

    ports: list[StpPort] = []
    for line in block[header_match.end() :].lstrip("\n").splitlines():
        stripped = line.strip()
        if not stripped:
            break
        if set(stripped) <= {"-"}:
            continue  # the "----" underline row between the header and the data

        row_match = _PORT_ROW.match(line)
        if row_match is None:
            continue
        role = _ROLE_BY_ABBREVIATION.get(row_match.group("role").lower())
        state = _STATE_BY_ABBREVIATION.get(row_match.group("state").lower())
        if role is None or state is None:
            continue

        ports.append(
            StpPort(
                device=local_device,
                vlan=vlan_id,
                interface=normalize(row_match.group("interface")),
                role=role,
                state=state,
                cost=int(row_match.group("cost")),
                link_type=row_match.group("link_type"),
            )
        )
    return ports
