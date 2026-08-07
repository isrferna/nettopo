"""Wires ingestion -> parsers -> `NetworkModel` population (PROJECT_SPEC.md section 4).

CDP/LLDP neighbors are frequently reported by their fully-qualified domain name (e.g.
`sw2-dist.example.com`) even though the same device's own capture identifies it by its
short hostname (`sw2-dist`, from `show version`). Left unresolved, that mismatch would
create a duplicate, non-source `Device` for every link between two source devices. This
module resolves neighbor names against the set of known source hostnames (exact match,
then short-name-vs-FQDN) once every capture's own hostname is known.

It also infers `Device.role` from CDP/LLDP capabilities so `render/icons.py` (Phase 3)
has real data to key off of. A device's own CDP/LLDP output never reports its own
capabilities, so a source device's role can only come from how its *neighbors* describe
it. This must run on every raw discovered link, before deduplication: when both ends of
a link are source devices, deduplication keeps only one direction's `Link` (see
`_resolve`/`links_by_key` below), which would silently discard the only capability report
naming whichever device ends up on the discarded side.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from nettopo.ingest.base import DataSource
from nettopo.model.entities import Device, DeviceRole, Link, NetworkModel, StpVlan
from nettopo.parsing.cdp import parse_cdp
from nettopo.parsing.interfaces import parse_interfaces
from nettopo.parsing.lldp import parse_lldp
from nettopo.parsing.spanning_tree import parse_spanning_tree
from nettopo.parsing.version import parse_version
from nettopo.parsing.vlan import parse_vlans

# Checked in priority order: a device reported with both "Router" and "Switch"
# capabilities (e.g. a multilayer switch) is classified as a router first.
_ROLE_BY_CAPABILITY: tuple[tuple[str, DeviceRole], ...] = (
    ("Router", DeviceRole.ROUTER),
    ("Switch", DeviceRole.SWITCH),
    ("Phone", DeviceRole.PHONE),
    ("Host", DeviceRole.HOST),
)


def build_network_model(source: DataSource, *, default_platform: str = "cisco_ios") -> NetworkModel:
    model = NetworkModel()
    captures = list(source.discover())

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

    known_hostnames = set(model.devices)
    links_by_key: dict[frozenset[tuple[str, str]], Link] = {}

    for capture in captures:
        platform = capture.platform_hint or default_platform
        local_device = hostname_by_hint[capture.device_hint]
        discovered = (
            *parse_cdp(local_device, capture.raw_text, platform=platform),
            *parse_lldp(local_device, capture.raw_text, platform=platform),
        )
        for link in discovered:
            resolved = replace(link, remote_device=_resolve(link.remote_device, known_hostnames))
            remote = model.devices.setdefault(
                resolved.remote_device, Device(hostname=resolved.remote_device)
            )
            if remote.role is DeviceRole.UNKNOWN:
                remote.role = _infer_role(resolved.remote_capabilities)
            links_by_key.setdefault(resolved.key(), resolved)

    model.links = list(links_by_key.values())
    return model


def _resolve(neighbor_name: str, known_hostnames: set[str]) -> str:
    if neighbor_name in known_hostnames:
        return neighbor_name
    short_name = neighbor_name.split(".", 1)[0]
    if short_name in known_hostnames:
        return short_name
    return neighbor_name


def _infer_role(capabilities: Iterable[str]) -> DeviceRole:
    capability_set = set(capabilities)
    for capability, role in _ROLE_BY_CAPABILITY:
        if capability in capability_set:
            return role
    return DeviceRole.UNKNOWN
