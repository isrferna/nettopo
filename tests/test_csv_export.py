"""Tests for CSV export (PROJECT_SPEC.md section 8)."""

from __future__ import annotations

import csv
from pathlib import Path

from nettopo.export.csv_export import write_csv_tables
from nettopo.model.entities import (
    Device,
    Interface,
    Link,
    NetworkModel,
    StpBridge,
    StpPort,
    StpRole,
    StpState,
    StpVlan,
    Vlan,
)


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _sample_model() -> NetworkModel:
    model = NetworkModel()
    device = Device(
        hostname="sw1", is_source=True, platform="cisco C9300", os="ios", serial="FOC2134X0ABC"
    )
    device.interfaces["Gi1/0/1"] = Interface(name="Gi1/0/1", description="=cmd|calc")
    model.devices["sw1"] = device
    model.devices["sw2"] = Device(hostname="sw2")
    model.links.append(
        Link(
            local_device="sw1",
            local_interface="Gi1/0/1",
            remote_device="sw2",
            remote_interface="Gi1/0/2",
            remote_capabilities=["Switch", "IGMP"],
        )
    )
    model.vlans[10] = Vlan(vlan_id=10, name="users", status="active")
    return model


def test_write_csv_tables_creates_every_table(tmp_path: Path) -> None:
    csv_dir = write_csv_tables(_sample_model(), tmp_path)
    expected = {
        "devices.csv",
        "interfaces.csv",
        "neighbors.csv",
        "vlans.csv",
        "stp.csv",
        "hsrp.csv",
        "bgp.csv",
    }
    assert {path.name for path in csv_dir.iterdir()} == expected


def test_devices_csv_has_one_row_per_device(tmp_path: Path) -> None:
    csv_dir = write_csv_tables(_sample_model(), tmp_path)
    rows = _read_rows(csv_dir / "devices.csv")
    assert {row["hostname"] for row in rows} == {"sw1", "sw2"}
    sw1 = next(row for row in rows if row["hostname"] == "sw1")
    assert sw1["is_source"] == "True"
    assert sw1["platform"] == "cisco C9300"
    assert sw1["os"] == "ios"
    assert sw1["serial"] == "FOC2134X0ABC"


def test_neighbors_csv_joins_capabilities_with_semicolons(tmp_path: Path) -> None:
    csv_dir = write_csv_tables(_sample_model(), tmp_path)
    (row,) = _read_rows(csv_dir / "neighbors.csv")
    assert row["remote_capabilities"] == "Switch;IGMP"


def test_vlans_csv_is_sorted_by_vlan_id(tmp_path: Path) -> None:
    model = _sample_model()
    model.vlans[1] = Vlan(vlan_id=1, name="default", status="active")
    csv_dir = write_csv_tables(model, tmp_path)
    rows = _read_rows(csv_dir / "vlans.csv")
    assert [row["vlan_id"] for row in rows] == ["1", "10"]


def test_empty_stp_hsrp_bgp_tables_are_header_only(tmp_path: Path) -> None:
    csv_dir = write_csv_tables(_sample_model(), tmp_path)
    for name in ("stp.csv", "hsrp.csv", "bgp.csv"):
        lines = (csv_dir / name).read_text().splitlines()
        assert len(lines) == 1


def test_formula_prefixed_cell_values_are_neutralized(tmp_path: Path) -> None:
    csv_dir = write_csv_tables(_sample_model(), tmp_path)
    rows = _read_rows(csv_dir / "interfaces.csv")
    (row,) = [row for row in rows if row["name"] == "Gi1/0/1"]
    assert row["description"] == "'=cmd|calc"


def test_stp_csv_has_one_row_per_port_with_base_and_effective_priority(tmp_path: Path) -> None:
    model = _sample_model()
    model.stp[10] = StpVlan(
        vlan=10,
        root_device="sw1",
        bridges={
            "sw1": StpBridge(
                device="sw1",
                vlan=10,
                base_priority=24576,
                sys_id_ext=10,
                mac="aaaa.bbbb.0001",
                is_root=True,
            ),
            "sw2": StpBridge(
                device="sw2",
                vlan=10,
                base_priority=32768,
                sys_id_ext=10,
                mac="aaaa.bbbb.0002",
            ),
        },
        ports={
            ("sw1", "Gi1/0/1"): StpPort(
                device="sw1",
                vlan=10,
                interface="Gi1/0/1",
                role=StpRole.DESIGNATED,
                state=StpState.FWD,
                cost=4,
            ),
            ("sw2", "Gi1/0/2"): StpPort(
                device="sw2",
                vlan=10,
                interface="Gi1/0/2",
                role=StpRole.ROOT,
                state=StpState.FWD,
                cost=4,
            ),
        },
    )
    csv_dir = write_csv_tables(model, tmp_path)
    rows = _read_rows(csv_dir / "stp.csv")

    assert len(rows) == 2
    sw2_row = next(row for row in rows if row["device"] == "sw2")
    assert sw2_row["root_device"] == "sw1"
    assert sw2_row["base_priority"] == "32768"
    assert sw2_row["effective_priority"] == "32778"
    assert sw2_row["is_root"] == "False"
    assert sw2_row["interface"] == "Gi1/0/2"
    assert sw2_row["role"] == "root"
    assert sw2_row["state"] == "forwarding"
