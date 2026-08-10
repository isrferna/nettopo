"""CSV export of every intermediate table (PROJECT_SPEC.md section 8).

CSV is a first-class output, not an afterthought: it is both a deliverable and the
primary debugging aid for a wrong diagram. One table per model entity. `stp.csv`,
`hsrp.csv`, and `bgp.csv` are header-only until their parsers land in Phases 4-6.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from nettopo.model.entities import NetworkModel, StpPort

# OWASP A03: a cell value parsed from device data (e.g. a hostname) that happens to
# start with one of these characters would be interpreted as a formula by spreadsheet
# software opening the CSV. Prefixing with an apostrophe neutralizes that.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

_STP_HEADER = (
    "vlan",
    "device",
    "root_device",
    "bridge_mac",
    "base_priority",
    "effective_priority",
    "is_root",
    "interface",
    "role",
    "state",
    "cost",
)
_HSRP_HEADER = ("vlan", "group", "virtual_ip", "device", "interface", "priority", "role", "preempt")
_BGP_HEADER = (
    "local_device",
    "local_asn",
    "peer_ip",
    "peer_asn",
    "peer_device",
    "type",
    "state",
    "vrf",
)


def write_csv_tables(model: NetworkModel, output_root: Path) -> Path:
    """Write every CSV table under `output_root/csv/` and return that directory."""
    csv_dir = output_root / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)

    _write_devices(csv_dir / "devices.csv", model)
    _write_interfaces(csv_dir / "interfaces.csv", model)
    _write_neighbors(csv_dir / "neighbors.csv", model)
    _write_vlans(csv_dir / "vlans.csv", model)
    _write_stp(csv_dir / "stp.csv", model)
    _write_table(csv_dir / "hsrp.csv", _HSRP_HEADER, [])
    _write_table(csv_dir / "bgp.csv", _BGP_HEADER, [])

    return csv_dir


def _write_devices(path: Path, model: NetworkModel) -> None:
    header = (
        "hostname",
        "is_source",
        "platform",
        "model",
        "os",
        "serial",
        "role",
        "mgmt_ip",
        "asn",
    )
    rows = [
        (
            device.hostname,
            device.is_source,
            device.platform,
            device.model,
            device.os,
            device.serial,
            device.role.value,
            device.mgmt_ip,
            device.asn,
        )
        for device in model.devices.values()
    ]
    _write_table(path, header, rows)


def _write_interfaces(path: Path, model: NetworkModel) -> None:
    header = (
        "device",
        "name",
        "type",
        "description",
        "admin_up",
        "oper_up",
        "ip_address",
        "prefix_len",
        "vlan",
        "mode",
        "trunk_vlans",
        "po_id",
        "po_members",
    )
    rows = [
        (
            device.hostname,
            interface.name,
            interface.type.value,
            interface.description,
            interface.admin_up,
            interface.oper_up,
            interface.ip_address,
            interface.prefix_len,
            interface.vlan,
            interface.mode,
            ";".join(str(vlan_id) for vlan_id in interface.trunk_vlans),
            interface.po_id,
            ";".join(interface.po_members),
        )
        for device in model.devices.values()
        for interface in device.interfaces.values()
    ]
    _write_table(path, header, rows)


def _write_neighbors(path: Path, model: NetworkModel) -> None:
    header = (
        "local_device",
        "local_interface",
        "remote_device",
        "remote_interface",
        "discovery",
        "remote_platform",
        "remote_mgmt_ip",
        "remote_capabilities",
    )
    rows = [
        (
            link.local_device,
            link.local_interface,
            link.remote_device,
            link.remote_interface,
            link.discovery,
            link.remote_platform,
            link.remote_mgmt_ip,
            ";".join(link.remote_capabilities),
        )
        for link in model.links
    ]
    _write_table(path, header, rows)


def _write_vlans(path: Path, model: NetworkModel) -> None:
    header = ("vlan_id", "name", "status")
    rows = [
        (vlan.vlan_id, vlan.name, vlan.status)
        for vlan in sorted(model.vlans.values(), key=lambda vlan: vlan.vlan_id)
    ]
    _write_table(path, header, rows)


def _write_stp(path: Path, model: NetworkModel) -> None:
    rows: list[tuple[object, ...]] = []
    for stp_vlan in sorted(model.stp.values(), key=lambda stp_vlan: stp_vlan.vlan):
        ports_by_device: dict[str, list[StpPort]] = defaultdict(list)
        for (device, _interface), port in stp_vlan.ports.items():
            ports_by_device[device].append(port)

        for device, bridge in sorted(stp_vlan.bridges.items()):
            for port in sorted(ports_by_device[device], key=lambda port: port.interface):
                rows.append(
                    (
                        stp_vlan.vlan,
                        device,
                        stp_vlan.root_device,
                        bridge.mac,
                        bridge.base_priority,
                        bridge.effective_priority,
                        bridge.is_root,
                        port.interface,
                        port.role.value,
                        port.state.value,
                        port.cost,
                    )
                )
    _write_table(path, _STP_HEADER, rows)


def _write_table(path: Path, header: tuple[str, ...], rows: Sequence[tuple[object, ...]]) -> None:
    try:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            for row in rows:
                writer.writerow(_csv_safe(value) for value in row)
    except OSError as exc:
        raise OSError(f"failed to write CSV table '{path}': {exc}") from exc


def _csv_safe(value: object) -> str:
    text = "" if value is None else str(value)
    if text and text[0] in _FORMULA_PREFIXES:
        return "'" + text
    return text
