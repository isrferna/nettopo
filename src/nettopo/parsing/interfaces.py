"""Parser for `show ip interface brief` and `show interfaces` (PROJECT_SPEC.md section 4)."""

from __future__ import annotations

import re

from nettopo.model.entities import Interface, InterfaceType
from nettopo.parsing._textfsm import run_template
from nettopo.utils.command_sections import extract_command_output
from nettopo.utils.interfaces import normalize

_IP_BRIEF_PATTERN = re.compile(r"show\s+ip\s+int\w*\s+br\w*\s*$", re.IGNORECASE)
_INTERFACES_PATTERN = re.compile(r"show\s+int\w*\s*$", re.IGNORECASE)

_UNASSIGNED = {"unassigned", ""}


def parse_interfaces(raw_text: str, *, platform: str = "cisco_ios") -> dict[str, Interface]:
    """Parse interface state from `show ip interface brief` and `show interfaces`.

    The two commands are merged by normalized interface name: `show interfaces` is the
    richer source (description, precise IP/prefix, link state) and wins on overlapping
    fields; `show ip interface brief` fills in any interface it lists that `show
    interfaces` did not capture.
    """
    interfaces: dict[str, Interface] = {}

    for record in _parse_ip_brief(raw_text, platform):
        interface = _get_or_create(interfaces, record["interface"])
        interface.admin_up = record["status"] != "administratively down"
        interface.oper_up = record["proto"] == "up"
        if record["ip_address"] not in _UNASSIGNED:
            interface.ip_address = record["ip_address"]

    for record in _parse_show_interfaces(raw_text, platform):
        interface = _get_or_create(interfaces, record["interface"])
        interface.description = record.get("description") or None
        interface.admin_up = record["link_status"] != "administratively down"
        interface.oper_up = _oper_up(record.get("protocol_status", ""))
        if record.get("ip_address"):
            interface.ip_address = record["ip_address"]
            interface.prefix_len = _to_int(record.get("prefix_length"))

    return interfaces


def _get_or_create(interfaces: dict[str, Interface], raw_name: str) -> Interface:
    name = normalize(raw_name)
    return interfaces.setdefault(name, Interface(name=name, type=_interface_type(name)))


def _parse_ip_brief(raw_text: str, platform: str) -> list[dict[str, str]]:
    output = extract_command_output(raw_text, _IP_BRIEF_PATTERN)
    if not output:
        return []
    return run_template(platform=platform, command="show ip interface brief", data=output)


def _parse_show_interfaces(raw_text: str, platform: str) -> list[dict[str, str]]:
    output = extract_command_output(raw_text, _INTERFACES_PATTERN)
    if not output:
        return []
    return run_template(platform=platform, command="show interfaces", data=output)


def _oper_up(protocol_status: str) -> bool | None:
    if not protocol_status:
        return None
    return protocol_status.split()[0] == "up"


def _to_int(value: str | None) -> int | None:
    return int(value) if value else None


def _interface_type(name: str) -> InterfaceType:
    if "." in name:
        return InterfaceType.SUBINTERFACE
    if name.startswith("Vl"):
        return InterfaceType.SVI
    if name.startswith("Po"):
        return InterfaceType.PORT_CHANNEL
    if name.startswith("Lo"):
        return InterfaceType.LOOPBACK
    if name.startswith("Tu"):
        return InterfaceType.TUNNEL
    if name.startswith("Mgmt"):
        return InterfaceType.MGMT
    return InterfaceType.PHYSICAL
