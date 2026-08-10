"""Wires ingestion -> parsers -> `NetworkModel` population (PROJECT_SPEC.md section 4).

CDP and LLDP rarely agree on what to call a neighbor: the same device is reported as
`nxos-core1` by one protocol, `nxos-core1(FDO21120U5D)` by the other (NX-OS appends the
chassis serial), and `nxos-core1.example.com` by a third device. Left unresolved, every
spelling becomes its own `Device` and one physical switch is drawn as several nodes.
`utils/hostnames.py` owns that correlation; this module feeds it every observed spelling
and rewrites each discovered link onto the canonical name it returns.

It also infers `Device.role` from CDP/LLDP capabilities so `render/icons.py` (Phase 3)
has real data to key off of. A device's own CDP/LLDP output never reports its own
capabilities, so a source device's role can only come from how its *neighbors* describe
it. This must run on every raw discovered link, before deduplication: when both ends of
a link are source devices, deduplication keeps only one direction's `Link` (see
`links_by_key` below), which would silently discard the only capability report naming
whichever device ends up on the discarded side.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import replace

from nettopo.ingest.base import Capture, DataSource
from nettopo.model.entities import Device, DeviceRole, Link, NetworkModel, StpVlan
from nettopo.parsing.cdp import parse_cdp
from nettopo.parsing.interfaces import parse_interfaces
from nettopo.parsing.lldp import parse_lldp
from nettopo.parsing.spanning_tree import parse_spanning_tree
from nettopo.parsing.version import parse_version
from nettopo.parsing.vlan import parse_vlans
from nettopo.utils.hostnames import resolve_device_identities, split_serial_suffix

# Checked in priority order: a device reported with both "Router" and "Switch"
# capabilities (e.g. a multilayer switch) is classified as a router first.
_ROLE_BY_CAPABILITY: tuple[tuple[str, DeviceRole], ...] = (
    ("Router", DeviceRole.ROUTER),
    ("Switch", DeviceRole.SWITCH),
    ("Phone", DeviceRole.PHONE),
    ("Host", DeviceRole.HOST),
)

# CDP names a neighbor's port more reliably than LLDP does, so it wins when both report
# the same adjacency out of one local port.
_DISCOVERY_RANK: dict[str, int] = {"cdp": 0, "lldp": 1}


def build_network_model(source: DataSource, *, default_platform: str = "cisco_ios") -> NetworkModel:
    captures = list(source.discover())

    model = NetworkModel()
    hostname_by_hint = _populate_source_devices(model, captures, default_platform)

    discovered = _discover_links(captures, hostname_by_hint, default_platform)
    canonical_by_spelling = resolve_device_identities(
        (link.remote_device for link in discovered), set(model.devices)
    )
    serial_by_hostname = _serials(canonical_by_spelling)

    # One entry per (local port, neighbor): the two protocols describing the same
    # adjacency collapse here, before the direction-independent pass below collapses the
    # same link as seen from each of its two ends.
    links_by_port: dict[tuple[str, str, str], Link] = {}
    for link in discovered:
        resolved = replace(link, remote_device=canonical_by_spelling[link.remote_device])
        remote = model.devices.setdefault(
            resolved.remote_device, Device(hostname=resolved.remote_device)
        )
        if remote.role is DeviceRole.UNKNOWN:
            remote.role = _infer_role(resolved.remote_capabilities)
        if remote.serial is None:
            remote.serial = serial_by_hostname.get(resolved.remote_device)

        port_key = (resolved.local_device, resolved.local_interface, resolved.remote_device)
        existing = links_by_port.get(port_key)
        if existing is None or _discovery_rank(resolved) < _discovery_rank(existing):
            links_by_port[port_key] = resolved

    links_by_key: dict[frozenset[tuple[str, str]], Link] = {}
    for link in links_by_port.values():
        links_by_key.setdefault(link.key(), link)

    model.links = list(links_by_key.values())
    return model


def _populate_source_devices(
    model: NetworkModel, captures: Sequence[Capture], default_platform: str
) -> dict[str, str]:
    """Register every device we hold a capture for and return its canonical hostname."""
    hostname_by_hint: dict[str, str] = {}
    for capture in captures:
        platform = capture.platform_hint or default_platform
        version_info = parse_version(capture.raw_text, platform=platform)
        hostname = (version_info.hostname if version_info else None) or capture.device_hint
        hostname_by_hint[capture.device_hint] = hostname

        device = model.devices.setdefault(hostname, Device(hostname=hostname))
        device.is_source = True
        if version_info:
            device.platform = version_info.platform
            device.model = version_info.model
            device.os = version_info.os
            device.serial = version_info.serial
        device.interfaces.update(parse_interfaces(capture.raw_text, platform=platform))

        for vlan in parse_vlans(capture.raw_text, platform=platform):
            model.vlans.setdefault(vlan.vlan_id, vlan)

        for stp_capture in parse_spanning_tree(hostname, capture.raw_text):
            stp_vlan = model.stp.setdefault(stp_capture.vlan, StpVlan(vlan=stp_capture.vlan))
            stp_vlan.bridges[hostname] = stp_capture.bridge
            for port in stp_capture.ports:
                stp_vlan.ports[(hostname, port.interface)] = port
            if stp_capture.bridge.is_root:
                stp_vlan.root_device = hostname

    return hostname_by_hint


def _discover_links(
    captures: Sequence[Capture], hostname_by_hint: dict[str, str], default_platform: str
) -> list[Link]:
    """Parse every capture's CDP and LLDP neighbors, neighbor names still as reported."""
    links: list[Link] = []
    for capture in captures:
        platform = capture.platform_hint or default_platform
        local_device = hostname_by_hint[capture.device_hint]
        links.extend(parse_cdp(local_device, capture.raw_text, platform=platform))
        links.extend(parse_lldp(local_device, capture.raw_text, platform=platform))
    return links


def _serials(canonical_by_spelling: dict[str, str]) -> dict[str, str]:
    """Recover the chassis serial NX-OS advertises inside its name, keyed by hostname."""
    return {
        canonical: serial
        for spelling, canonical in canonical_by_spelling.items()
        if (serial := split_serial_suffix(spelling)[1]) is not None
    }


def _discovery_rank(link: Link) -> int:
    return _DISCOVERY_RANK.get(link.discovery, len(_DISCOVERY_RANK))


def _infer_role(capabilities: Iterable[str]) -> DeviceRole:
    capability_set = set(capabilities)
    for capability, role in _ROLE_BY_CAPABILITY:
        if capability in capability_set:
            return role
    return DeviceRole.UNKNOWN
