"""Tests for the STP grouping fingerprint (PROJECT_SPEC.md sections 6 and 12).

The two boundary cases below are the most test-critical logic in the project:
- Same priority, different topology (the blocked link differs) must NOT group under
  `strict` or `topology`.
- Same topology, different priority must group under `topology` but NOT under `strict`.
"""

from __future__ import annotations

from nettopo.model.entities import StpBridge, StpPort, StpRole, StpState, StpVlan
from nettopo.model.grouping import GroupMode, stp_fingerprint


def _bridge(device: str, vlan: int, base_priority: int, is_root: bool = False) -> StpBridge:
    return StpBridge(
        device=device,
        vlan=vlan,
        base_priority=base_priority,
        sys_id_ext=vlan,
        mac=f"aaaa.bbbb.{vlan:04d}",
        is_root=is_root,
    )


def _port(device: str, vlan: int, interface: str, role: StpRole, state: StpState) -> StpPort:
    return StpPort(device=device, vlan=vlan, interface=interface, role=role, state=state)


def test_same_priority_different_topology_does_not_group_under_strict_or_topology() -> None:
    # Two VLANs, identical priorities on SW1/SW2, but the blocked port differs:
    # vlan 10 blocks SW2 Gi1/0/2, vlan 20 blocks SW2 Gi1/0/3.
    vlan10 = StpVlan(
        vlan=10,
        root_device="SW1",
        bridges={
            "SW1": _bridge("SW1", 10, base_priority=24576, is_root=True),
            "SW2": _bridge("SW2", 10, base_priority=32768),
        },
        ports={
            ("SW1", "Gi1/0/1"): _port("SW1", 10, "Gi1/0/1", StpRole.DESIGNATED, StpState.FWD),
            ("SW2", "Gi1/0/1"): _port("SW2", 10, "Gi1/0/1", StpRole.ROOT, StpState.FWD),
            ("SW2", "Gi1/0/2"): _port("SW2", 10, "Gi1/0/2", StpRole.ALTERNATE, StpState.BLK),
        },
    )
    vlan20 = StpVlan(
        vlan=20,
        root_device="SW1",
        bridges={
            "SW1": _bridge("SW1", 20, base_priority=24576, is_root=True),
            "SW2": _bridge("SW2", 20, base_priority=32768),
        },
        ports={
            ("SW1", "Gi1/0/1"): _port("SW1", 20, "Gi1/0/1", StpRole.DESIGNATED, StpState.FWD),
            ("SW2", "Gi1/0/1"): _port("SW2", 20, "Gi1/0/1", StpRole.ROOT, StpState.FWD),
            ("SW2", "Gi1/0/3"): _port("SW2", 20, "Gi1/0/3", StpRole.ALTERNATE, StpState.BLK),
        },
    )

    assert stp_fingerprint(vlan10, GroupMode.STRICT) != stp_fingerprint(vlan20, GroupMode.STRICT)
    assert stp_fingerprint(vlan10, GroupMode.TOPOLOGY) != stp_fingerprint(
        vlan20, GroupMode.TOPOLOGY
    )


def test_same_topology_different_priority_groups_under_topology_not_strict() -> None:
    # Two VLANs with the exact same blocked link and roles, but different configured
    # base priorities on SW2.
    vlan30 = StpVlan(
        vlan=30,
        root_device="SW1",
        bridges={
            "SW1": _bridge("SW1", 30, base_priority=24576, is_root=True),
            "SW2": _bridge("SW2", 30, base_priority=32768),
        },
        ports={
            ("SW1", "Gi1/0/1"): _port("SW1", 30, "Gi1/0/1", StpRole.DESIGNATED, StpState.FWD),
            ("SW2", "Gi1/0/1"): _port("SW2", 30, "Gi1/0/1", StpRole.ROOT, StpState.FWD),
            ("SW2", "Gi1/0/2"): _port("SW2", 30, "Gi1/0/2", StpRole.ALTERNATE, StpState.BLK),
        },
    )
    vlan40 = StpVlan(
        vlan=40,
        root_device="SW1",
        bridges={
            "SW1": _bridge("SW1", 40, base_priority=24576, is_root=True),
            "SW2": _bridge("SW2", 40, base_priority=28672),
        },
        ports={
            ("SW1", "Gi1/0/1"): _port("SW1", 40, "Gi1/0/1", StpRole.DESIGNATED, StpState.FWD),
            ("SW2", "Gi1/0/1"): _port("SW2", 40, "Gi1/0/1", StpRole.ROOT, StpState.FWD),
            ("SW2", "Gi1/0/2"): _port("SW2", 40, "Gi1/0/2", StpRole.ALTERNATE, StpState.BLK),
        },
    )

    assert stp_fingerprint(vlan30, GroupMode.TOPOLOGY) == stp_fingerprint(
        vlan40, GroupMode.TOPOLOGY
    )
    assert stp_fingerprint(vlan30, GroupMode.STRICT) != stp_fingerprint(vlan40, GroupMode.STRICT)


def test_per_vlan_mode_never_groups_even_identical_topologies() -> None:
    vlan10 = StpVlan(
        vlan=10,
        root_device="SW1",
        bridges={"SW1": _bridge("SW1", 10, base_priority=24576, is_root=True)},
        ports={("SW1", "Gi1/0/1"): _port("SW1", 10, "Gi1/0/1", StpRole.DESIGNATED, StpState.FWD)},
    )
    vlan20 = StpVlan(
        vlan=20,
        root_device="SW1",
        bridges={"SW1": _bridge("SW1", 20, base_priority=24576, is_root=True)},
        ports={("SW1", "Gi1/0/1"): _port("SW1", 20, "Gi1/0/1", StpRole.DESIGNATED, StpState.FWD)},
    )

    assert stp_fingerprint(vlan10, GroupMode.PER_VLAN) != stp_fingerprint(
        vlan20, GroupMode.PER_VLAN
    )
