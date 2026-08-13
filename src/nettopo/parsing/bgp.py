"""Parser for `show ip bgp summary` (PROJECT_SPEC.md section 4).

A thin adapter over ntc-templates, like the HSRP parser: `cisco_ios_show_ip_bgp_summary`
captures every column the v1 model needs, so there is nothing for a hand-written regex to
add. IOS and IOS-XE print the command identically and share the one template;
`tests/fixtures/bgp/` carries a fixture for each.

Two columns need interpreting rather than copying:

- **State.** IOS overloads the last column: it prints the number of prefixes received
  once the session is up, and a state word (`Idle`, `Active`, `Idle (Admin)`) while it is
  not. A count therefore *means* `Established`, which is what `BgpPeer.state` records.
- **Session type.** The summary never says iBGP or eBGP; it is `IBGP` exactly when the
  neighbor's AS equals the local one.

One fact in the output belongs to no session at all: the **router ID** on the header line
(`BGP router identifier 10.255.0.1, local AS number 65001`), which names the reporting
router rather than any of its peerings. The template carries it down onto every row, so
returning it per `BgpPeer` would repeat one device-level fact once per session. Hence
`BgpCapture`: a session is still a complete `BgpPeer`, needing no merging across devices
the way an HSRP group does, but it is handed back alongside the one thing the summary says
about the router itself.

`BgpPeer.peer_device` stays `None` (PROJECT_SPEC.md section 2): resolving a peer IP to a
hostname is out of scope for v1's model. `vrf` stays `"default"` for the same kind of
reason -- `show ip bgp summary` covers the default VRF, and the template has no VRF column
to read one from.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from ntc_templates.parse import ParsingException

from nettopo.model.entities import BgpPeer, BgpType
from nettopo.parsing._textfsm import run_template
from nettopo.utils.command_sections import extract_command_output

logger = logging.getLogger("nettopo")

_COMMAND_PATTERN = re.compile(r"show\s+ip\s+bgp\s+(?:all\s+)?sum\w*\s*$", re.IGNORECASE)

# An AS number written in asdot notation ("1.10"), which IOS accepts alongside the plain
# form and the template captures verbatim.
_ASDOT = re.compile(r"^(\d+)\.(\d+)$")
_ASDOT_MULTIPLIER = 65536

_ESTABLISHED = "Established"


@dataclass(frozen=True)
class BgpCapture:
    """One device's `show ip bgp summary`: its own router ID, and one peer per session."""

    router_id: str | None
    peers: list[BgpPeer]


def parse_bgp(local_device: str, raw_text: str, *, platform: str = "cisco_ios") -> BgpCapture:
    """Parse `local_device`'s `show ip bgp summary` output into a capture of that router."""
    output = extract_command_output(raw_text, _COMMAND_PATTERN)
    if not output:
        return BgpCapture(router_id=None, peers=[])

    records = _run(platform=platform, data=output)

    peers = []
    for record in records:
        peer = _to_peer(local_device, record)
        if peer is not None:
            peers.append(peer)
    return BgpCapture(router_id=_router_id(records), peers=peers)


def _router_id(records: list[dict[str, Any]]) -> str | None:
    """The reporting router's BGP router ID, read off the first row.

    The template carries the header line's value down onto every row, so any of them
    settles it -- the same reasoning that lets `ingest/model_builder.py` take the device's
    AS number from a single session. A summary whose header printed but which listed no
    neighbors yields no rows at all, and so no router ID either.
    """
    if not records:
        return None
    return str(records[0].get("router_id") or "").strip() or None


def _run(*, platform: str, data: str) -> list[dict[str, Any]]:
    """Run the template, downgrading a missing/unusable one to "no BGP known".

    A capture from a platform ntc-templates has no matching template for is a capture or
    `--platform` problem, not a reason to abort the whole run.
    """
    try:
        return run_template(platform=platform, command="show ip bgp summary", data=data)
    except ParsingException as exc:
        logger.warning("Skipping BGP data: %s", exc)
        return []


def _to_peer(local_device: str, record: dict[str, Any]) -> BgpPeer | None:
    local_asn = _asn(record.get("local_as"))
    peer_asn = _asn(record.get("neighbor_as"))
    if local_asn is None or peer_asn is None:
        logger.warning(
            "%s: BGP neighbor %s reports AS numbers this parser cannot read "
            "(local '%s', neighbor '%s') -- skipping that session.",
            local_device,
            record.get("bgp_neighbor") or "with no address",
            record.get("local_as"),
            record.get("neighbor_as"),
        )
        return None

    return BgpPeer(
        local_device=local_device,
        local_asn=local_asn,
        peer_ip=str(record.get("bgp_neighbor", "")),
        peer_asn=peer_asn,
        state=_state(str(record.get("state_or_prefixes_received", ""))),
        type=BgpType.IBGP if peer_asn == local_asn else BgpType.EBGP,
    )


def _state(column: str) -> str:
    """Read the State/PfxRcd column, whose two meanings are told apart by its shape.

    A prefix count is only ever printed for a session that is up, so a numeric column is
    reported as `Established` -- the state the count implies -- and anything else is the
    state word IOS printed, kept verbatim so `Idle (Admin)` survives intact.
    """
    value = column.strip()
    return _ESTABLISHED if value.isdigit() else value


def _asn(value: object) -> int | None:
    """Read an AS number in either plain (`65001`) or asdot (`1.10`) notation."""
    text = str(value or "").strip()
    if text.isdigit():
        return int(text)

    asdot = _ASDOT.match(text)
    if asdot is None:
        return None
    high, low = asdot.groups()
    return int(high) * _ASDOT_MULTIPLIER + int(low)
