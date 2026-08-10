"""Dataclasses and enums for the normalized network model (PROJECT_SPEC.md section 6).

`model` depends on nothing but `nettopo.utils` and must never import `render`, `views`,
or N2G (layering rule, PROJECT_SPEC.md section 3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DeviceRole(Enum):
    ROUTER = "router"
    L3_SWITCH = "l3_switch"
    SWITCH = "switch"
    FIREWALL = "firewall"
    AP = "ap"
    PHONE = "phone"
    SERVER = "server"
    HOST = "host"
    UNKNOWN = "unknown"


class InterfaceType(Enum):
    PHYSICAL = "physical"
    SVI = "svi"
    PORT_CHANNEL = "port_channel"
    LOOPBACK = "loopback"
    SUBINTERFACE = "subinterface"
    MGMT = "mgmt"
    TUNNEL = "tunnel"
    UNKNOWN = "unknown"


class StpRole(Enum):
    ROOT = "root"
    DESIGNATED = "designated"
    ALTERNATE = "alternate"
    BACKUP = "backup"
    DISABLED = "disabled"


class StpState(Enum):
    FWD = "forwarding"
    BLK = "blocking"
    LRN = "learning"
    LIS = "listening"
    DIS = "disabled"


class HsrpRole(Enum):
    ACTIVE = "active"
    STANDBY = "standby"
    LISTEN = "listen"
    INIT = "init"
    SPEAK = "speak"


class BgpType(Enum):
    IBGP = "ibgp"
    EBGP = "ebgp"


@dataclass
class Interface:
    name: str  # normalized: "Gi1/0/1", "Vl10", "Po1"
    type: InterfaceType = InterfaceType.UNKNOWN
    description: str | None = None
    admin_up: bool | None = None
    oper_up: bool | None = None
    ip_address: str | None = None
    prefix_len: int | None = None
    vlan: int | None = None  # access VLAN, or the SVI number
    mode: str | None = None  # "access" | "trunk"
    trunk_vlans: list[int] = field(default_factory=list)
    po_id: int | None = None  # if this port is a member of a port-channel
    po_members: list[str] = field(default_factory=list)  # if this IS the port-channel (MLAG/LAG)


@dataclass
class Device:
    hostname: str  # canonical correlation key
    is_source: bool = False  # we have this device's own capture
    platform: str | None = None  # raw: "cisco C9300-48P"; own `show version`, or CDP/LLDP
    model: str | None = None  # parsed: "C9300-48P"
    os: str | None = None  # "ios" | "ios-xe" | "nxos"
    serial: str | None = None  # own `show version`, or the suffix NX-OS advertises
    role: DeviceRole = DeviceRole.UNKNOWN
    mgmt_ip: str | None = None
    asn: int | None = None  # for BGP
    interfaces: dict[str, Interface] = field(default_factory=dict)  # keyed by normalized name


@dataclass
class Link:
    local_device: str
    local_interface: str
    remote_device: str
    remote_interface: str
    discovery: str = "cdp"  # "cdp" | "lldp"
    remote_platform: str | None = None
    remote_capabilities: list[str] = field(default_factory=list)  # ["Router","Switch"] vs [...]

    def key(self) -> frozenset[tuple[str, str]]:
        """Direction-independent identity, used to de-duplicate A->B and B->A."""
        return frozenset(
            {
                (self.local_device, self.local_interface),
                (self.remote_device, self.remote_interface),
            }
        )


@dataclass
class StpBridge:
    device: str
    vlan: int
    base_priority: int  # configured base, e.g. 24576
    sys_id_ext: int  # normally equals the VLAN id
    mac: str
    is_root: bool = False

    @property
    def effective_priority(self) -> int:
        return self.base_priority + self.sys_id_ext


@dataclass
class StpPort:
    device: str
    vlan: int
    interface: str
    role: StpRole
    state: StpState
    cost: int | None = None


@dataclass
class StpVlan:
    vlan: int
    root_device: str | None = None
    bridges: dict[str, StpBridge] = field(default_factory=dict)
    ports: dict[tuple[str, str], StpPort] = field(default_factory=dict)  # (device, interface)


@dataclass
class HsrpMember:
    device: str
    interface: str  # the SVI: "Vl10"
    group: int
    priority: int
    role: HsrpRole
    preempt: bool | None = None


@dataclass
class HsrpGroup:
    vlan: int
    group: int
    virtual_ip: str | None = None
    members: dict[str, HsrpMember] = field(default_factory=dict)  # keyed by device


@dataclass
class BgpPeer:
    local_device: str
    local_asn: int
    peer_ip: str
    peer_asn: int
    state: str  # "Established", "Idle", "Active", ...
    type: BgpType
    peer_device: str | None = None  # v1: always None
    vrf: str = "default"


@dataclass
class Vlan:
    vlan_id: int
    name: str | None = None
    status: str | None = None


@dataclass
class NetworkModel:
    devices: dict[str, Device] = field(default_factory=dict)  # keyed by hostname
    links: list[Link] = field(default_factory=list)
    vlans: dict[int, Vlan] = field(default_factory=dict)
    stp: dict[int, StpVlan] = field(default_factory=dict)  # keyed by VLAN id
    hsrp: dict[tuple[int, int], HsrpGroup] = field(default_factory=dict)  # (vlan, group)
    bgp: list[BgpPeer] = field(default_factory=list)
