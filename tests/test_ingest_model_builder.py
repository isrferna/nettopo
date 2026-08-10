"""Tests for the ingest -> parse -> model wiring (PROJECT_SPEC.md section 4).

Uses `tests/fixtures/captures/`: two source devices (`sw1-access`, IOS; `sw2-dist`,
IOS-XE) that are CDP/LLDP neighbors of each other and of a third, non-source device
(`core-rtr`) that only appears in CDP output. Both source devices also carry VLAN 10
`show spanning-tree` output (`sw2-dist` as root) for the STP wiring tests below.

`tests/fixtures/captures_nxos/` is a separate directory for neighbor identity
resolution. One Nexus is uplinked to two access switches and named differently by each
report: `acc-sw3` sees it as `nxos-core1(FDO21120U5D)` over CDP (NX-OS appends the
chassis serial to its device id) and as plain `nxos-core1` over LLDP, while `acc-sw4`
sees it as `NXOS-CORE1.example.com`. `acc-sw3` likewise sees one host as `esxi-host03`
over CDP and `esxi-host03.example.com` over LLDP.
"""

from __future__ import annotations

from pathlib import Path

from nettopo.ingest.files import FileDataSource
from nettopo.ingest.model_builder import build_network_model
from nettopo.model.entities import DeviceRole, NetworkModel

FIXTURES = Path(__file__).parent / "fixtures" / "captures"
NXOS_FIXTURES = Path(__file__).parent / "fixtures" / "captures_nxos"


def _build_model() -> NetworkModel:
    return build_network_model(FileDataSource(FIXTURES))


def _build_nxos_model() -> NetworkModel:
    return build_network_model(FileDataSource(NXOS_FIXTURES))


def test_every_source_device_is_registered_and_marked_as_source() -> None:
    model = _build_model()
    assert model.devices["sw1-access"].is_source is True
    assert model.devices["sw2-dist"].is_source is True


def test_source_devices_get_platform_and_os_from_show_version() -> None:
    model = _build_model()
    assert model.devices["sw1-access"].os == "ios"
    assert model.devices["sw2-dist"].os == "ios-xe"


def test_neighbor_fqdn_is_resolved_to_the_matching_source_hostname() -> None:
    model = _build_model()
    assert "sw2-dist.example.com" not in model.devices
    remote_devices = {link.remote_device for link in model.links}
    assert "sw2-dist" in remote_devices


def test_non_source_neighbor_is_kept_as_a_non_source_device() -> None:
    model = _build_model()
    core_rtr = model.devices["core-rtr.example.com"]
    assert core_rtr.is_source is False


def test_the_same_physical_link_seen_from_both_ends_is_deduplicated() -> None:
    model = _build_model()
    sw1_to_sw2 = [
        link
        for link in model.links
        if {link.local_device, link.remote_device} == {"sw1-access", "sw2-dist"}
    ]
    assert len(sw1_to_sw2) == 1


def test_interfaces_and_vlans_are_populated_per_device() -> None:
    model = _build_model()
    assert "Gi1/0/1" in model.devices["sw1-access"].interfaces
    assert 10 in model.vlans


def test_device_role_is_inferred_from_a_neighbors_reported_capabilities() -> None:
    # core-rtr is only ever seen as a CDP neighbor (never a source device), reported
    # with "Capabilities: Router".
    model = _build_model()
    assert model.devices["core-rtr.example.com"].role is DeviceRole.ROUTER


def test_stp_bridges_are_populated_per_vlan_from_both_devices() -> None:
    model = _build_model()
    vlan10 = model.stp[10]
    assert set(vlan10.bridges) == {"sw1-access", "sw2-dist"}
    assert vlan10.bridges["sw2-dist"].base_priority == 24576


def test_stp_root_device_is_the_bridge_that_reports_itself_as_root() -> None:
    model = _build_model()
    assert model.stp[10].root_device == "sw2-dist"


def test_stp_ports_are_keyed_by_device_and_interface() -> None:
    model = _build_model()
    vlan10 = model.stp[10]
    assert ("sw1-access", "Gi1/0/24") in vlan10.ports
    assert vlan10.ports[("sw1-access", "Gi1/0/24")].role.value == "root"


def test_both_ends_of_a_source_to_source_link_get_a_role() -> None:
    # Both sw1-access and sw2-dist are source devices, so the physical link between
    # them is discovered from both ends and then deduplicated to one `Link`, which
    # keeps only one direction's remote_capabilities. Role inference must still see
    # both directions' capability reports before that deduplication happens, or one
    # of the two devices would be silently left at DeviceRole.UNKNOWN.
    model = _build_model()
    assert model.devices["sw1-access"].role is DeviceRole.SWITCH
    assert model.devices["sw2-dist"].role is DeviceRole.SWITCH


def test_source_device_serial_comes_from_its_own_show_version() -> None:
    model = _build_model()
    assert model.devices["sw1-access"].serial == "FOC2134X0ABC"


def test_a_neighbor_named_with_and_without_its_serial_is_one_device() -> None:
    model = _build_nxos_model()
    assert set(model.devices) == {"acc-sw3", "acc-sw4", "nxos-core1", "esxi-host03"}


def test_one_neighbor_named_differently_by_two_switches_keeps_both_of_its_links() -> None:
    # Merging the spellings must not merge the adjacencies: the Nexus has one uplink to
    # each access switch, out of a different port on each side.
    model = _build_nxos_model()
    uplinks = {
        (link.local_device, link.local_interface, link.remote_interface)
        for link in model.links
        if link.remote_device == "nxos-core1"
    }
    assert uplinks == {
        ("acc-sw3", "Gi1/0/49", "Eth1/1"),
        ("acc-sw4", "Gi1/0/49", "Eth1/2"),
    }


def test_the_serial_a_neighbor_advertises_in_its_name_is_kept_as_data() -> None:
    model = _build_nxos_model()
    assert model.devices["nxos-core1"].serial == "FDO21120U5D"


def test_cdp_and_lldp_reporting_one_adjacency_produce_a_single_link() -> None:
    model = _build_nxos_model()
    (uplink,) = [
        link
        for link in model.links
        if link.local_device == "acc-sw3" and link.remote_device == "nxos-core1"
    ]
    assert uplink.local_interface == "Gi1/0/49"
    assert uplink.remote_interface == "Eth1/1"
    assert uplink.discovery == "cdp"


def test_a_non_source_neighbor_seen_short_and_as_an_fqdn_is_one_device() -> None:
    model = _build_nxos_model()
    assert "esxi-host03.example.com" not in model.devices
    assert model.devices["esxi-host03"].role is DeviceRole.HOST
