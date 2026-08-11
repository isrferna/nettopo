"""Parser for `show standby brief` (HSRP, PROJECT_SPEC.md section 4).

Unlike `show spanning-tree`, whose shipped template captures only part of what the model
needs, `cisco_ios_show_standby_brief` captures every column: interface, group, priority,
preempt flag, state, and the virtual IP. So this parser is a thin adapter over
ntc-templates -- there is nothing left for a hand-written regex to add, and `show standby`
(the per-group detail form) is not read at all.

IOS and IOS-XE print this command identically and share the one template;
`tests/fixtures/hsrp/` carries a fixture for each to prove that.

**Only SVIs are modeled.** `NetworkModel.hsrp` is keyed by `(vlan, group)`
(PROJECT_SPEC.md section 6), so a group on a routed port or a subinterface has no key to
live under and is skipped with a warning. That is a deliberate limit of the v1 data model,
matching the HSRP view's scope ("switches and their SVIs", section 7), not a parsing gap.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from ntc_templates.parse import ParsingException

from nettopo.model.entities import HsrpMember, HsrpRole
from nettopo.parsing._textfsm import run_template
from nettopo.utils.command_sections import extract_command_output
from nettopo.utils.interfaces import normalize, svi_vlan

logger = logging.getLogger("nettopo")

_COMMAND_PATTERN = re.compile(r"show\s+standby\s+br\w*\s*$", re.IGNORECASE)

_ROLE_BY_STATE: dict[str, HsrpRole] = {
    "active": HsrpRole.ACTIVE,
    "standby": HsrpRole.STANDBY,
    "listen": HsrpRole.LISTEN,
    "init": HsrpRole.INIT,
    "speak": HsrpRole.SPEAK,
    "learn": HsrpRole.LEARN,
}

# The device prints "unknown" in the Virtual IP column when it has not learned one yet,
# which is a placeholder rather than an address.
_UNKNOWN_VIRTUAL_IP = "unknown"


@dataclass(frozen=True)
class HsrpGroupCapture:
    """One device's view of one HSRP group, ready to merge into an `HsrpGroup`."""

    vlan: int
    group: int
    virtual_ip: str | None
    member: HsrpMember


def parse_hsrp(
    local_device: str, raw_text: str, *, platform: str = "cisco_ios"
) -> list[HsrpGroupCapture]:
    """Parse `local_device`'s `show standby brief` output into per-group captures."""
    output = extract_command_output(raw_text, _COMMAND_PATTERN)
    if not output:
        return []

    captures = []
    for record in _run(platform=platform, data=output):
        capture = _to_capture(local_device, record)
        if capture is not None:
            captures.append(capture)
    return captures


def _run(*, platform: str, data: str) -> list[dict[str, Any]]:
    """Run the template, downgrading a missing/unusable one to "no HSRP known".

    ntc-templates ships `show standby brief` for `cisco_ios` only. A capture from a
    platform it has no template for (NX-OS, which spells the command `show hsrp brief`)
    is a capture or `--platform` problem, not a reason to abort the whole run.
    """
    try:
        return run_template(platform=platform, command="show standby brief", data=data)
    except ParsingException as exc:
        logger.warning("Skipping HSRP data: %s", exc)
        return []


def _to_capture(local_device: str, record: dict[str, Any]) -> HsrpGroupCapture | None:
    interface = normalize(str(record.get("interface", "")))
    vlan = svi_vlan(interface)
    if vlan is None:
        logger.warning(
            "%s: HSRP group %s runs on %s, which is not an SVI -- skipping it, since the "
            "model keys HSRP groups by VLAN.",
            local_device,
            record.get("group"),
            interface or "an unnamed interface",
        )
        return None

    role = _ROLE_BY_STATE.get(str(record.get("state", "")).casefold())
    if role is None:
        logger.warning(
            "%s: unrecognized HSRP state '%s' on %s -- skipping that group.",
            local_device,
            record.get("state"),
            interface,
        )
        return None

    virtual_ip = str(record.get("virtual_ip_address", ""))
    return HsrpGroupCapture(
        vlan=vlan,
        group=int(record["group"]),
        virtual_ip=virtual_ip if virtual_ip and virtual_ip != _UNKNOWN_VIRTUAL_IP else None,
        member=HsrpMember(
            device=local_device,
            interface=interface,
            group=int(record["group"]),
            priority=int(record["priority"]),
            role=role,
            # The template reports the Preempt column verbatim, and it is a literal space
            # when the group does not preempt -- never absent, so this is a real boolean
            # rather than an unknown.
            preempt=str(record.get("preempt", "")).strip() == "P",
        ),
    )
