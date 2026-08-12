"""STP VLAN grouping fingerprint function (PROJECT_SPEC.md section 6, "Grouping").

Diagrams are grouped by the resulting *topology* fingerprint, never by raw configured
priority alone: equal priority does not guarantee equal topology (differing port costs
or states can move the blocked link), and `STRICT` vs `TOPOLOGY` differ only in whether
priority values participate in the fingerprint.

Two VLANs should be grouped together, under a given `GroupMode`, exactly when their
fingerprints compare equal. `PER_VLAN` fingerprints embed the VLAN id itself, so they are
unique by construction and never equal across VLANs — this is what "no grouping" means in
fingerprint terms. `STRICT` and `TOPOLOGY` fingerprints deliberately omit the VLAN id so
that unrelated VLANs sharing a topology (and, for `STRICT`, priorities) collide and group
together.

Grouping applies to the STP view alone. Two VLANs' HSRP never renders identically —
each carries its own virtual IP and its own SVI address per router — so `views/hsrp.py`
draws one diagram per VLAN and no HSRP fingerprint exists to compare them by.
"""

from __future__ import annotations

from enum import Enum

from nettopo.model.entities import StpVlan


class GroupMode(Enum):
    PER_VLAN = "per-vlan"
    STRICT = "strict"
    TOPOLOGY = "topology"


def stp_fingerprint(stp_vlan: StpVlan, mode: GroupMode) -> tuple[object, ...]:
    """Fingerprint identifying which other VLANs `stp_vlan` should be grouped with."""
    if mode is GroupMode.PER_VLAN:
        return (stp_vlan.vlan,)

    ports = tuple(
        sorted(
            (port.device, port.interface, port.role.value, port.state.value)
            for port in stp_vlan.ports.values()
        )
    )

    if mode is GroupMode.TOPOLOGY:
        return (stp_vlan.root_device, ports)

    bridges = tuple(
        sorted((bridge.device, bridge.base_priority) for bridge in stp_vlan.bridges.values())
    )
    return (stp_vlan.root_device, bridges, ports)
