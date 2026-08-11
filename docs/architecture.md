# Architecture

This document describes `nettopo`'s components, call flow, and the design decisions
behind them, in enough technical depth to work on the codebase without re-deriving it
from the source. It is kept in sync with the code — see the documentation-maintenance
rule in [`CLAUDE.md`](../CLAUDE.md). For scope, the full data model, and the CLI
reference, see [`PROJECT_SPEC.md`](../PROJECT_SPEC.md); for user-facing command/option
docs, see the [README](../README.md#usage).

## Current state (Phase 5)

| Command | Status | Reads | Writes |
|---|---|---|---|
| `nettopo parse` | real | every capture | `output/csv/*.csv` |
| `nettopo l2` | real | CDP/LLDP, interfaces | `output/l2/*.drawio` |
| `nettopo stp` | real | `show spanning-tree` | `output/stp/*.drawio`, `stp.csv` rows |
| `nettopo hsrp` | real | `show standby brief` | `output/hsrp/*.drawio`, `hsrp.csv` rows |
| `nettopo bgp` | argument parsing only | — | exits 1, "not implemented yet" |
| `nettopo all` | argument parsing only | — | exits 1, "not implemented yet" |

`bgp`/`all` land in Phases 6–7 (`PROJECT_SPEC.md` §14). The rest of this document
describes both what exists today and the target architecture those phases build into.

## System overview

Every subcommand follows the same pipeline: **ingest → parse → model → view → render or
export**. `cli.py` is the only module that knows about all five stages; each stage only
knows about the one inward of it (see [Layering rule](#layering-rule-dependency-inversion)).

```mermaid
flowchart LR
    ingest["ingest/<br/>DataSource, FileDataSource,<br/>model_builder.py"] --> model["model/<br/>NetworkModel, grouping fingerprints"]
    parsing["parsing/<br/>one parser per show command"] --> model
    views["views/<br/>l2, stp, hsrp, bgp"] --> model
    render["render/<br/>drawio, icons, legend, lucidify"] --> views
    render --> model
    export["export/<br/>csv_export"] --> views
    export --> model
    model --> utils["utils/<br/>interfaces, hostnames, command_sections, paths"]
    parsing --> utils
    cli["cli.py<br/>argument parsing + orchestration only"] -. orchestrates .-> ingest
    cli -. orchestrates .-> parsing
    cli -. orchestrates .-> views
    cli -. orchestrates .-> render
    cli -. orchestrates .-> export
```

| Package | Responsibility |
|---|---|
| `ingest/` | Data sources. `base.py` defines the `DataSource` interface; `files.py` implements it over a directory of saved captures; `model_builder.py` wires parser output into a populated `NetworkModel`. |
| `parsing/` | One parser per `show` command. Returns plain dataclasses/lists — never touches `NetworkModel` directly. |
| `model/` | `entities.py`: the normalized dataclasses and enums (`NetworkModel` and everything it contains). `grouping.py`: the STP/HSRP fingerprint functions that decide which VLANs render identically. `platforms.py`: the product-family table that turns a reported chassis into a `DeviceRole`. |
| `views/` | One module per diagram (`l2`, `stp`, `hsrp`; `bgp` pending). Reads the model, returns a render-ready `views/diagram.py` `Diagram`. Never parses text or writes files. `diagram.py` also holds what the two per-VLAN views share: the `VlanDiagramGroup` they return and the `vlan_diagram_filename()` both output names are built from. |
| `render/` | `drawio.py` (the only module importing N2G), `icons.py` (`DeviceRole` → Cisco icon, plus the palette and link styles), `legend.py` (the diagram's key), `lucidify.py` (Lucidchart-import post-process). |
| `export/` | `csv_export.py`: one CSV table per model entity. |
| `utils/` | Dependency-free shared services: `interfaces.py` (interface-name normalizer), `hostnames.py` (device-name normalizer), `command_sections.py` (multi-command capture splitter), `paths.py` (filename sanitization / output-root resolution). |
| `cli.py` | `argparse` setup and per-command orchestration only — no parsing or rendering logic lives here. |

### Layering rule (Dependency Inversion)

Dependencies point inward only:

```
parsing  -> model
views    -> model
render   -> views, model
export   -> views, model
cli      -> orchestrates all of the above
model    -> utils only
```

`model` never imports `render`, `views`, or N2G. This means the data model — the part
most worth protecting from churn — has no knowledge of how it is displayed or exported,
so a rendering-library change (see [Why N2G is isolated to one
module](#why-n2g-is-isolated-to-one-module)) or a new export format cannot ripple back
into parsing or modeling code.

## End-to-end call flow

`nettopo stp -i captures --all --group-mode topology` exercises every stage of the
pipeline (ingestion, three-phase model building, grouping, rendering), so it is used here
as the representative example. `nettopo l2` and `nettopo parse` follow the same shape
minus the grouping step.

```mermaid
sequenceDiagram
    participant User
    participant CLI as "cli.py: main()"
    participant FDS as FileDataSource
    participant MB as "model_builder.build_network_model()"
    participant P as "parsing.* functions"
    participant HN as "hostnames.resolve_device_identities()"
    participant STP as "views.stp.build_groups()"
    participant GRP as "grouping.stp_fingerprint()"
    participant DIO as "render.drawio.render_diagram()"
    participant N2G as "N2G / igraph"
    participant LUC as "render.lucidify.lucidify_xml()"

    User->>CLI: nettopo stp -i captures --all --group-mode topology
    CLI->>FDS: discover()
    FDS-->>CLI: Capture(device_hint, raw_text, platform_hint) x N
    CLI->>MB: build_network_model(source)
    loop phase 1: each capture
        MB->>P: parse_version / parse_interfaces / parse_vlans / parse_spanning_tree
        P-->>MB: Device fields, Vlan, StpVlanCapture
    end
    loop phase 2: each capture
        MB->>P: parse_cdp / parse_lldp
        P-->>MB: raw Link objects
    end
    MB->>HN: every reported neighbor spelling + source hostnames
    HN-->>MB: spelling -> canonical name
    Note over MB: phase 3: canonicalize remote_device, register devices,<br/>collapse CDP/LLDP duplicates, de-duplicate by Link.key()
    MB-->>CLI: NetworkModel
    CLI->>STP: build_groups(model, group_mode=TOPOLOGY)
    loop each StpVlan in model.stp
        STP->>GRP: stp_fingerprint(stp_vlan, TOPOLOGY)
        GRP-->>STP: fingerprint tuple
    end
    Note over STP: VLANs sharing a fingerprint become one VlanDiagramGroup
    STP-->>CLI: list of VlanDiagramGroup
    loop each group
        CLI->>DIO: render_diagram(group.diagram, output_path)
        DIO->>N2G: add_node(style) / add_link(style) / layout(kk)
        Note over DIO: scales the layout until the closest<br/>two nodes have room for their labels
        N2G-->>DIO: draw.io XML
        DIO->>LUC: lucidify_xml(xml)
        LUC-->>DIO: import-friendly XML
        DIO-->>CLI: writes output/stp/stp_vlans-<ids>.drawio
    end
    CLI-->>User: "Rendered N STP diagram(s) to output/stp"
```

## Ingestion and model building

### Why an ingestion interface

`ingest/base.py` defines a `DataSource` interface; `ingest/files.py` implements it by
reading a directory of saved captures. v1 ships file-based ingestion only (see
`PROJECT_SPEC.md` section 2, "out of scope"), but the interface exists now so that a
future live-collection source (netmiko/scrapli over SSH) can be added by implementing
the same interface, without touching `parsing/`, `model/`, or `views/`.

### Three-phase model building

`ingest/model_builder.py`'s `build_network_model()` cannot resolve neighbor identities
while it discovers them. Deciding what to call a neighbor needs two things that are only
complete once *every* capture has been read: the set of source-device hostnames, and the
set of all spellings that neighbor was reported under. So the build registers source
devices first, then collects raw links, then resolves identities and writes the links
into the model.

```mermaid
flowchart TD
    subgraph phase1["Phase 1 — establish every source device's canonical identity"]
        A["for each capture"] --> B["parse_version() -> hostname, platform, os, serial"]
        B --> C["model.devices[hostname] = Device(is_source=True)"]
        C --> D["parse_interfaces / parse_vlans / parse_spanning_tree<br/>populate that device + model.vlans + model.stp"]
    end
    phase1 --> E["known_hostnames = set(model.devices)"]
    subgraph phase2["Phase 2 — discover links, neighbor names still as reported"]
        E --> F["for each capture"] --> G["parse_cdp + parse_lldp -> raw Link objects"]
    end
    G --> H["resolve_device_identities(every reported spelling, known_hostnames)<br/>utils/hostnames.py"]
    subgraph phase3["Phase 3 — canonicalize, register, de-duplicate"]
        H --> I["rewrite Link.remote_device to its canonical name"]
        I --> J["register the remote Device<br/>(+ role from remote_capabilities, + serial, + platform, + mgmt_ip)"]
        J --> K["one link per (local device, local port, neighbor)<br/>CDP wins over LLDP"]
        K --> L["de-duplicate by Link.key()<br/>(direction-independent frozenset of both ends)"]
    end
    L --> M["model.links"]
```

**Why neighbor names are resolved instead of used as-is.** CDP and LLDP disagree about
what a device is called: the same Nexus is `nxos-core1` in one protocol's output and
`nxos-core1(FDO21120U5D)` in the other's, and a device's FQDN
(`sw2-dist.example.com`) routinely appears where its own capture says `sw2-dist`. Each
uncorrelated spelling becomes its own non-source `Device`, so one switch is drawn as
several nodes with parallel links. `utils/hostnames.py` owns the correlation rules
(`PROJECT_SPEC.md` §5.2); a neighbor whose spelling correlates with nothing else (e.g.
`core-rtr.example.com`, seen only in CDP output) is kept as a non-source `Device` under
the name it was reported by — it may still get a role (see below) even though it's never
a source device.

**Why one link is kept per local port and neighbor.** Both protocols describe the same
adjacency, and they do not always describe it identically: `Link.key()` alone cannot
collapse them when LLDP names the neighbor's port differently from CDP. Keeping one link
per `(local device, local port, neighbor)` — CDP first, since it names Cisco ports more
reliably — removes that second edge without touching genuinely distinct adjacencies: a
phone and a PC on one access port are different neighbors, and two links to the same
neighbor leave from different local ports.

**Why `Device.role` is inferred from neighbor capabilities, not self-reported.**
`render/icons.py` maps `DeviceRole` to a Cisco icon, but a device's own CDP/LLDP output
never reports its own capabilities — so role is inferred from how *other* devices'
CDP/LLDP describe it (`Capabilities: Router` / `Switch` / `Phone` / `Host`). This
inference is applied to every raw link as it is registered (step J above), before the
two directions of a source-to-source link are deduplicated into one `Link` (step L):
deduplication keeps only one direction's `remote_capabilities`, so inferring role only
from the deduplicated list would silently leave whichever device ended up on the
discarded side at `DeviceRole.UNKNOWN`. A device never described by any neighbor's
capabilities (e.g. an isolated source device) stays `UNKNOWN` and renders as a plain box
rather than a guessed icon.

**Why `Device.platform` and `Device.mgmt_ip` are backfilled from CDP/LLDP.** A device we
hold no capture for has no `show version` and no interface table of its own, yet every
neighbor that sees it advertises both its hardware (CDP's `Platform:` line, LLDP's
inventory `Model:`) and its management address — values already carried on the `Link` as
`remote_platform` and `remote_mgmt_ip`. Registering a remote device copies them across,
so `devices.csv` describes neighbors and not just source devices. `_best_reported()`
resolves both, and among competing reports CDP outranks LLDP on the same grounds as
everywhere else in the build: CDP carries what the device itself advertises, where LLDP's
equivalents are optional TLVs many implementations leave empty or fill loosely. That
ranking is resolved up front, over all raw links, rather than first-come inside the
registration loop — otherwise the answer would depend on the order the captures happened
to be read in.

The two fields differ in whether a source device accepts the backfill, and the difference
is about what else could fill them. `platform` is refused for source devices: their own
`show version` is authoritative *including* when it produced nothing, since a neighbor's
view of a device is never better than its own. `mgmt_ip` is accepted by every device,
because no parser reads a management address out of a device's own capture — a source
device has no self-reported value to protect, so refusing the backfill would just leave
the column permanently empty.

`Device.model` (the vendor-prefix-stripped form) is deliberately *not* derived this way:
CDP platform strings are free text and are not always a hardware model at all (`VMware
ESXi`), so inferring one would put noise in a column that today only ever holds a parsed
`show version` value.

### Why the platform string, not capabilities, decides a device's role

`Device.role` starts from the `Router`/`Switch`/`Phone`/`Host` capabilities a neighbor
advertises over CDP/LLDP, and that source has two limits it cannot get past. It cannot
separate a router from a multilayer switch, because a Catalyst 9500 advertises
`Router Switch` and `_ROLE_BY_CAPABILITY` has to commit to one of the two — which is why
the campus example used to draw both of its core switches as routers. And a device's own
CDP/LLDP output never reports its own capabilities, so a *source* device has no role at all
unless some neighbor happens to describe it.

`model/platforms.py` closes both. It matches the reported chassis — `cisco C9500-16X`,
`N9K-C93180YC-EX`, `cisco ISR4331/K9`, `VMware ESX` — against a table of product families,
and `_apply_platform_roles()` runs it over every device once both platform sources have
settled. A fact about the device beats a fact about who saw it, so it wins. Until this
existed, `DeviceRole.L3_SWITCH`, `FIREWALL`, `AP` and `SERVER` had icons mapped in
`render/icons.py` that no code path could ever reach.

It lives in `model/` rather than `ingest/` because it is domain knowledge about Cisco
product names with no dependency on captures, files or parsing — `ingest` importing from
`model` keeps the arrows pointing inward, where the reverse would not. The table is
explicitly a heuristic: it classifies `C9300` as an access `SWITCH` and `C9500` as an
`L3_SWITCH` even though both route, because access-versus-core is the distinction a
topology drawing needs, and matching is unanchored and case-insensitive because NX-OS
reports no vendor prefix where IOS does.

### Why interface-name normalization is centralized

The same physical port can appear as `Gi1/0/1` in one `show` command's output and
`GigabitEthernet1/0/1` in another. If parsers normalized independently, or not at all,
correlation across commands (and across devices) would silently fail. `utils/interfaces.py`
is the single source of truth for this normalization; every parser routes interface
names through it before the name is stored anywhere in the model. See `PROJECT_SPEC.md`
§5.1 for the canonical abbreviation table.

### Why device-name normalization is centralized

Device names have the same problem one level up, with worse consequences: a mismatched
interface name splits one port, a mismatched device name splits an entire node and every
link attached to it. `utils/hostnames.py` is the single source of truth here, and unlike
interface names it is applied in `ingest/model_builder.py` rather than in the parsers —
correlating spellings requires seeing all of them at once, which no individual parser
does. Parsers therefore report neighbor names exactly as the device printed them.
`PROJECT_SPEC.md` §5.2 has the resolution rules; the important property is that a
canonical name is always one of the observed spellings, never a constructed one.

## Parsing layer

Every parser takes raw multi-command capture text plus (usually) the local device's
hostname, and returns plain dataclasses — it never writes into `NetworkModel` itself;
`ingest/model_builder.py` owns that. `utils/command_sections.py`'s
`extract_command_output()` is the shared first step: it finds the prompt line whose
command matches a pattern and returns just that command's output slice.

| `show` command | Parser | Technique | Populates |
|---|---|---|---|
| `show version` | `parsing/version.py` | ntc-templates | hostname, `Device.platform/model/os/serial` |
| `show ip interface brief`, `show interfaces` | `parsing/interfaces.py` | ntc-templates | `Device.interfaces` |
| `show vlan brief` | `parsing/vlan.py` | ntc-templates | `NetworkModel.vlans` |
| `show cdp neighbors detail` | `parsing/cdp.py` | ntc-templates + own regex (see below) | raw `Link`s (`discovery="cdp"`) |
| `show lldp neighbors detail` | `parsing/lldp.py` | ntc-templates | raw `Link`s (`discovery="lldp"`, see below), plus the neighbor's chassis MAC (`Device.chassis_id`), which CDP never reports |
| `show etherchannel summary`, `show port-channel summary` | `parsing/etherchannel.py` | ntc-templates (see below) | `Interface.po_id`, `Interface.po_members` |
| `show spanning-tree` | `parsing/spanning_tree.py` | **own regexes** (see below) | `NetworkModel.stp` (`StpBridge`, `StpPort`) — and, when links are bundled, needs `show etherchannel summary` alongside it for the STP view to resolve `Po1` onto its members |
| `show standby brief` | `parsing/hsrp.py` | ntc-templates | `NetworkModel.hsrp` (`HsrpGroup`, `HsrpMember`) |
| `show ip bgp summary` | `parsing/bgp.py` | not yet implemented | — (Phase 6) |

All ntc-templates-backed parsers go through `parsing/_textfsm.py`, a thin typed wrapper
around `ntc_templates.parse_output` — the one place the untyped `ntc_templates` import
boundary exists.

### Why the port-channel parser picks its template from the prompt line

Every other parser derives its ntc-templates command name from a fixed string, because
one command has one name. The bundle table does not: IOS and IOS-XE print it under
`show etherchannel summary`, NX-OS under `show port-channel summary`, and ntc-templates
ships one template per spelling — never both for the same platform. `parsing/
etherchannel.py` therefore matches both prompt-line spellings and uses whichever one the
capture actually contains to select the template. A capture whose spelling has no
template for the platform in effect (an NX-OS capture parsed under the `cisco_ios`
default, say) logs a warning and yields no bundles, rather than aborting the run over a
`--platform` mismatch.

### Why CDP's management address is parsed outside ntc-templates

A CDP entry advertises two unrelated addresses: `Entry address(es)` (`Interface
address(es)` on NX-OS), the address of the neighbor's *connected interface*, and
`Management address(es)` (`Mgmt address(es)` on NX-OS), the address you would actually
manage it on. They are routinely on different networks — a transit link vs. an
out-of-band management VLAN. The two ntc-templates templates disagree about which one
they expose under the name `MGMT_ADDRESS`: `cisco_nxos` reads the management block and
keeps the interface address in a separate field, while `cisco_ios` reads the *entry*
address into `MGMT_ADDRESS` and never looks at the management block at all. Taking that
field at face value would silently put a link address into `Device.mgmt_ip` on every IOS
capture. `parsing/cdp.py` therefore walks the entries itself for the management block —
matching both spellings — and uses the template's value only as a fallback for neighbors
that advertise no management address, where an interface address still beats nothing.
The walk is keyed by device id, which is what the `cisco_ios` template reports as the
neighbor name; NX-OS names its entries by `System Name` instead, so lookups miss there
and fall through to the template value, which on that platform is already correct.

### Which LLDP field names the neighbor's port

LLDP offers two candidates for the remote interface and neither is reliable on its own.
IOS puts the port's name in "Port Description" and often a MAC address in "Port id";
NX-OS puts the port's *configured description* ("uplink-to-acc-sw3") in "Port
Description", which correlates with nothing — CDP and LLDP then describe the same
physical link differently and it survives de-duplication as a second, bogus edge.
`parsing/lldp.py` picks whichever field `utils/interfaces.py`'s `looks_like_interface()`
recognizes (an interface type immediately followed by a number), preferring the
description when both qualify, and falls back to the description when neither does — a
non-Cisco port name like `vmnic0` is still better than nothing.

### Why `spanning_tree.py` doesn't use ntc-templates

`show spanning-tree`'s shipped template (`cisco_ios_show_spanning-tree`) only captures
the per-interface role/state/cost table — it has no fields for the "Root ID"/"Bridge ID"
blocks that carry the data `StpBridge` needs (priority, MAC, root-election flag). Rather
than mixing a TextFSM pass for the port table with hand-written regex for the bridge
blocks, `parsing/spanning_tree.py` parses the whole command output itself: both blocks
are simple, line-anchored, stable text, so one self-contained regex-based parser is
simpler than two parsing strategies for one command. IOS and IOS-XE emit this command
identically (unlike `show version`, which does differ enough to need the OS-detection
logic in `parsing/version.py`), so the same parser serves both —
`tests/fixtures/spanning_tree/` carries one fixture per OS to prove it.

Concretely, per VLAN block it extracts two things independently:

1. **Root ID / Bridge ID** — `Root ID` gives this device's view of the root bridge (and
   whether *this* device is the root, via the "This bridge is the root" line); `Bridge
   ID` gives this device's own priority, sys-id-extension, and MAC. Together these
   become one `StpBridge`.
2. **The port table** — the `Interface / Role / Sts / Cost / Prio.Nbr / Type` rows,
   parsed into `StpPort`s after mapping Cisco's abbreviations (`Root`/`Desg`/`Altn`/
   `Back`/`Disb`, `FWD`/`BLK`/`LRN`/`LIS`/`DIS`/`BKN`) onto `StpRole`/`StpState`. The
   Type column is kept verbatim in `StpPort.link_type`, which `StpPort.is_edge` reads to
   tell a port facing a switch from a PortFast port facing a host. The state is matched as
   letters plus an optional starred suffix, because IOS glues the reason for an
   inconsistency straight onto it (`BKN*ROOT_Inc`) and a stricter pattern loses the whole
   row — and with it every link the STP view would have drawn through that port.

`ingest/model_builder.py` then folds each device's per-VLAN `StpBridge` + `StpPort`s
into the shared `model.stp[vlan_id]: StpVlan`, records whichever device reported
itself as root as that VLAN's `root_device`, and keeps the reported root address in
`root_mac` — which is the only trace of the root left when no captured device is it.

### How the STP view joins spanning-tree state to a topology

`show spanning-tree` never names the device on the other end of a port, so the STP view
takes its links from the CDP/LLDP topology in `model.links` and looks up each end's
`StpPort` to label and color it. The two sources name interfaces differently in exactly
one case, and it is the common one: a **port-channel** appears in spanning-tree only as
`Po1`, and in CDP/LLDP only as its members `Gi1/0/1`, `Gi1/0/2`. `NetworkModel.port_channel_name()`
(shared with the L2 view, and populated by `parsing/etherchannel.py`) is what maps one
onto the other; the members then collapse into a single drawn link, since spanning-tree
runs over the bundle as one logical port. Without `show etherchannel summary` in the
captures there is no mapping to make, and a fully bundled network yields a diagram of
disconnected nodes — which `cli.py` reports as an explicit warning rather than leaving
the user to notice.

The view draws two kinds of node. A device with a capture comes from its own `StpBridge`.
A device seen only in a neighbor's output has no bridge data at all, so it is drawn faded
(`DiagramNode.inferred` -> `render/icons.py`) and labeled with its name alone, and is
admitted only through a non-Edge port. When such a device is the root, it is highlighted
only if `Device.chassis_id` — which LLDP alone reports — matches `StpVlan.root_mac`
exactly; an exact match either names the root or says nothing, where a looser heuristic
could highlight the wrong switch.

## The data model and grouping

`model/entities.py` holds the full normalized data model (`NetworkModel` and every
dataclass/enum it's built from) — see `PROJECT_SPEC.md` section 6 for the exact shapes;
it is not duplicated here to avoid the two documents drifting out of sync.

### Why grouping is a separate concern from views

STP and HSRP views can be generated per-VLAN, or with VLANs grouped by resulting
topology fingerprint (`strict` groups on exact configured priority + topology; `topology`
groups on topology alone, ignoring priority). The fingerprint functions live in
`model/grouping.py`, not in the view modules, because the notion of "these VLANs produce
the same diagram" is a property of the model, independent of how that diagram is later
rendered.

### STP grouping flow

```mermaid
flowchart TD
    A["model.stp: dict[vlan_id, StpVlan]"] --> B{"--vlan N given?"}
    B -- yes --> C["render just that VLAN,<br/>ignore --group-mode entirely"]
    B -- no --> D["for each StpVlan,<br/>compute stp_fingerprint(stp_vlan, group_mode)"]
    D --> E{group_mode}
    E -- per-vlan --> F["fingerprint = (vlan,)<br/>unique by construction, so nothing ever groups"]
    E -- strict --> G["fingerprint = root_device<br/>+ sorted(device, base_priority)<br/>+ sorted(device, interface, role, state)"]
    E -- topology --> H["fingerprint = root_device<br/>+ sorted(device, interface, role, state)<br/>(priority values omitted)"]
    F --> I["group VLANs whose fingerprints compare equal"]
    G --> I
    H --> I
    I --> J["sort each group's VLAN ids ascending"]
    J --> K["render the lowest VLAN id as the group's representative diagram"]
    K --> L["name the output file after every VLAN id in the group:<br/>stp_vlan10.drawio, or stp_vlans-10_20_30.drawio"]
```

`strict` and `topology` differ only in whether priority values participate in the
fingerprint — equal priority does not guarantee equal topology (differing port costs or
states can move the blocked link), which is why grouping is defined by the *resulting*
fingerprint and never by raw configured priority alone. See
`tests/test_grouping.py` for the two boundary cases this must get right (same priority
but different topology; same topology but different priority), reconfirmed against real
parsed captures in `tests/test_views_stp.py` and `tests/fixtures/stp_topology/`.

## Views

| View | Module | Reads | Options | Produces |
|---|---|---|---|---|
| L2 | `views/l2.py` | `model.devices`, `model.links` | `--endpoints all\|network-only`, `--link-mode physical\|port-channel` | one `Diagram` |
| STP | `views/stp.py` | `model.stp`, `model.links`, `model.devices` | `--vlan`, `--group-mode` | one `Diagram` per VLAN or per topology group |
| HSRP | `views/hsrp.py` | `model.hsrp`, `model.devices` (for each member's SVI address) | `--vlan`, `--group-mode` | one `Diagram` per VLAN or per matching group |
| BGP | `views/bgp.py` | — | — | not yet implemented (Phase 6) |

### Why the STP view cross-references `model.links`

A `StpPort` records a device's own port role/state for a VLAN, but not which device is
on the other end of that port — spanning-tree data alone cannot say "this link goes to
sw2". `views/stp.py` gets that from `model.links` (built from CDP/LLDP, the only place
that records device-to-device physical adjacency) and looks up each link's two ends in
the VLAN's `StpPort` map to label and color it. A link where neither end has STP data
for that VLAN (e.g. a link outside the VLAN's spanning tree) is excluded. Root-bridge
highlighting and port-state link coloring are carried on the `Diagram` itself
(`DiagramNode.highlight`, `DiagramLink.color`) so `render/` can apply them as generic
style overrides without knowing anything about STP.

### Why the HSRP view draws a star and not a topology

The STP view's whole difficulty is that `show spanning-tree` never names the device on the
other end of a port, so the view has to join port state onto a CDP/LLDP topology. The HSRP
view has no equivalent problem, because it has no equivalent question: HSRP is not a
topology. `show standby brief` says which routers share a virtual IP and which of them is
currently active, and the segment they share is a broadcast domain rather than a set of
point-to-point links. Drawing the cables between the gateways would be redrawing the L2 or
STP diagram with fewer nodes.

So `views/hsrp.py` never reads `model.links`. Each HSRP group becomes a **virtual gateway
node** — the address hosts are actually configured with — and each member router gets one
link to it, labeled with that router's SVI, role and priority and colored green for active
or amber for standby. The gateway node is deliberately `DeviceRole.UNKNOWN`, which
`render/icons.py` draws as a plain box: it is an address, not a device, and giving it a
Cisco icon would say otherwise. Its id is namespaced (`hsrp:vlan10:group10`) so it cannot
collide with a member node, which is keyed by hostname.

**Where each member's own address comes from.** A router node is labeled with the address
its SVI holds in that VLAN, beside the group's virtual one, because that is what identifies
the box behind a traceroute hop or a ping reply. `show standby brief` cannot supply it:
its Active and Standby columns name those two routers by address and no one else, so in a
group with four members the two that are merely listening have no address anywhere in that
output. The view therefore reads `Device.interfaces[svi].ip_address`, populated by
`parsing/interfaces.py` from `show ip interface brief`/`show interfaces` — data the model
already held, joined rather than re-parsed. A capture with neither command leaves the node
labeled with its name alone. Any of a router's members supplies the SVI name to look up:
a diagram covers one VLAN, so every group in it sits on that VLAN's single SVI.

A diagram covers one VLAN and **every** group on it, because one SVI can carry several
(two gateways load-sharing a VLAN, each active for one group). That also fixes the unit of
grouping: `model/grouping.py` fingerprints one `HsrpGroup`, and the view compares two VLANs
by their groups' fingerprints in group-number order, so VLANs group together only when
their entire first-hop setup matches group for group.

Grouped diagrams render one representative VLAN, exactly as the STP view does — but with
one extra obligation. The virtual IP and the SVI name are precisely the two things that
*must* differ between VLANs grouped under `strict` or `topology`, and the virtual IP is
the headline fact of the whole diagram. So the gateway node names the VLAN it was drawn
from (`VLAN 10 group 10` above `10.10.10.1`): a diagram that says which VLAN its address
belongs to cannot be misread as claiming that address for every VLAN in the filename.

### Why grouped STP diagrams render one representative VLAN

`model/grouping.py`'s fingerprints guarantee that VLANs grouped under `strict` or
`topology` produce an identical rendered diagram — that is what "grouped" means (see
[STP grouping flow](#stp-grouping-flow) above). `views/stp.py` exploits that guarantee:
instead of re-deriving a merged diagram, it renders the lowest-numbered VLAN in each
group and labels the output file with every VLAN id the group covers
(`stp_vlans-10_20_30.drawio`).

### Why MLAG grouping is a mode rather than the default

`views/l2.py`'s `LinkMode` decides what one drawn link means: `PHYSICAL` draws one link
per discovered adjacency, `PORT_CHANNEL` collapses every adjacency belonging to the same
bundle into one. Both are needed and neither subsumes the other — the physical view is
what you want when tracing a cable or a single port's state, the bundle view is what you
want when reading the logical topology of a network where every uplink is an
EtherChannel. `PHYSICAL` stays the default because it is the lossless one: it never hides
a member port. Where no bundles exist, the two modes produce identical output, so the
option costs nothing on networks without port-channels.

The member interfaces a bundle hides are not lost — they travel in `DiagramLink.tooltip`
and are rendered as the draw.io `tooltip` attribute on the link's `<object>` cell, which
draw.io shows on hover in place of its default attribute dump.

**Bundling is keyed on the device pair, not on link direction.** A bundle end is
identified by its port-channel name — `Interface.po_id` for a member port,
`Interface.po_members` for the port-channel interface itself, since CDP/LLDP on NX-OS may
report an adjacency on `Po1` rather than on a member port. Only source devices have
interfaces populated, so an adjacency toward a device we hold no capture for is bundled
by its near end alone; that far end is then labeled with the member ports the neighbor
reported instead of a `Po` name. The key sorts its two ends by device name rather than
using the link's own local/remote direction, because `ingest/model_builder.py` keeps one
direction per physical link and *which* direction depends on whose capture reported it
first — two members of one bundle reported from opposite ends would otherwise become two
separate bundles.

## Rendering and export

### Why N2G is isolated to one module

`render/drawio.py` is the only module that imports N2G. If N2G is ever replaced, only
that module changes — `views/` and `model/` are unaffected because they depend on
neither N2G nor draw.io concepts. `render/icons.py` maps `DeviceRole` (plus `highlight`
and `inferred` flags) to a draw.io style string and the geometry that style needs;
`render/drawio.py` turns each `DiagramNode`/`DiagramLink` into an `add_node`/`add_link`
call, applies N2G's igraph-backed `kk` layout, draws the legend, then hands the dumped XML
to `lucidify.py` unless `--no-lucidify` was passed.

### Why the icons carry their own size, and why marks are fills rather than strokes

The icons are draw.io's `mxgraph.cisco19.*` set, and two of its properties shape
`render/icons.py` more than any design preference did.

**`strokeColor` is the glyph color.** These shapes paint the icon and its card outline in
`strokeColor` over a light `fillColor`, which is what makes a per-role palette possible —
a router is violet, a layer-3 switch deep blue, an access switch teal, an endpoint slate.
It is also why the two node markings could not stay as they were. Overriding the stroke to
gold, which is how the old isometric stencils marked the STP root bridge, turns the icon
into an unreadable monochrome blob; the root is now marked by a gold card fill that leaves
the glyph alone. And `dashed=1`, which used to mark a device held with no capture, renders
nothing at all on these shapes — their outline is too thin for a dash pattern to register,
so an inferred device was drawn identically to a measured one. Fading the whole node
(`opacity=40`, with an italic label) is what actually reads.

**`aspect=fixed`**, so a node's geometry has to match its icon's native ratio or the
drawing is stretched. `NodeStyle` therefore carries width and height alongside the style
string, taken from draw.io's own sidebar and scaled uniformly. `MAX_NODE_WIDTH_PX` is
derived from that same table rather than restated, because `render/drawio.py`'s spacing
rule needs the widest node a diagram can contain and the two must not drift apart.

Links are undirected in every view, and `link_style()` spells `endArrow=none` out on every
one of them rather than leaning on N2G's default. N2G *substitutes* its
`default_link_style` for whatever style it is handed instead of merging the two, so a link
that carries a color — which only the STP view sets, for port state — would silently lose
the default and render with draw.io's arrowhead. That arrow would also be a lie: the STP
view orders an edge's ends by device name (`views/stp.py`, `_build_edges`), so it would
point from the alphabetically-earlier device to the later one, which says nothing about
root ports or designated ports.

### Node spacing: why the layout is scaled after igraph runs

N2G's `layout()` hands the graph to igraph, then calls `fit_into()` to squeeze the result
into the diagram's canvas — which `add_diagram()` fixes at 1360x864 for every diagram it
will ever draw. Two consequences follow, and together they are why `render/drawio.py` does
not stop at `drawing.layout(algo="kk")`:

- **The algorithm only picks the layout's shape.** Absolute spacing is whatever dividing
  that one canvas among the nodes happens to give. Any igraph argument that spreads
  vertices further apart is normalized straight back out by the fit.
- **Spacing therefore ignores the labels.** The L2 view labels a link end `Gi1/0/23` and
  the STP view labels the same end `Gi1/0/23 designated/forwarding` — three times the
  width, in the same space. The STP view is the one that breaks: in the campus example its
  two closest nodes came out ~157px apart, and icons, node labels and link end labels
  merged into an unreadable pile.

`_spread_nodes()` scales the finished layout up until the closest pair of nodes is
`_minimum_node_separation()` apart — one node icon, plus `_LABEL_CLEARANCE` times the width
of the longest label the diagram carries, because draw.io centers a node's label under its
icon *and* pins each link end label near that same end, so the gap between two neighbors
has to hold both nodes' labels and the link end label between them. Deriving it from the
labels is what lets one rule serve both views: the STP diagrams spread out, the L2 diagrams
stay compact. The scale is uniform, so the layout igraph computed is preserved exactly.

**Why the closest pair and not a typical gap.** Measuring the global minimum has an obvious
cost: one unusually tight pair drags the whole canvas out with it, and the campus STP
diagram used to come out mostly whitespace with specks in it. Scaling to the *median*
nearest-neighbour distance instead was tried and rejected on measurement — in that same
diagram the nearest-neighbour distances are bimodal (`158, 158, 169, 317, 430, 439, 439`
px), so the median sits above the separation the labels need and three of seven nodes stay
close enough to overlap. A diagram larger than it strictly needs to be is a smaller problem
than one whose labels sit on top of each other. The sparseness was addressed where it
actually came from instead: `_LABEL_CLEARANCE` dropped from 1.5 to 1.3 now that link end
labels are set smaller than node labels, and the icons themselves are drawn larger.

Kamada-Kawai (`kk`) is kept as the algorithm. The alternatives N2G exposes were compared on
the campus example and all place the closest pair *worse*: `fr` packs it tighter than `kk`
at equal canvas size, `drl` collapses a graph this size almost to a point, and `rt` — a
tree layout on a graph with two cycles in it — flattens the whole thing into rows of
touching nodes. `kk` is also deterministic here, which keeps the committed example diagrams
from churning every time they are regenerated.

### The lucidify post-process

N2G emits each link's per-end interface label (`src_label`/`trgt_label`) as a child
`mxCell` vertex of the link's own edge cell, positioned along it by a *relative* geometry
(`x="-0.5"` near the source, `x="0.5"` near the target). That is the correct draw.io
construct and `lucidify` leaves it alone. A vertex parented to an edge is that edge's
label: it travels with the link when the link moves, and the Arrange layouts (Circle,
Tree, Organic) skip it. Re-homing those labels onto the canvas as free-standing text cells
— which this module did briefly — breaks exactly that: draw.io then reads each label as a
*node*, and Arrange → Circle lays the labels out on the circle alongside the devices,
scattering every label away from the link it describes.

Keeping the two ends as separate labels is also what the STP view needs. Merging them into
one centered string produces `Po110 designated/forwarding — Po110 root/forwarding`, which
says nothing about which switch is which.

What N2G gets wrong is the flag that declares the geometry relative. Its
`drawio_link_label_xml` template is called with `rel="1"` for the source-end label but
`rel="-1"` for the target-end one (`N2G_DrawIO.py` lines 380-404). draw.io tolerates it —
mxGraph parses the attribute as a number and any non-zero value is truthy — but an importer
that tests for the literal `"1"` sees a label with no relative positioning at all and drops
it at the edge's origin. That is the likeliest explanation for the Lucid mangling this
module was written for, so `lucidify` normalizes `relative` to `"1"` on every link end
label. It also cleans up the doubled semicolons N2G's XML templates leave in style strings.

```mermaid
flowchart LR
    subgraph before["N2G's raw output"]
        E1["edge object cell"]
        L1["child label cell<br/>x=-0.5, relative=1<br/>value: Gi1/0/1 (source end)"]
        L2["child label cell<br/>x=0.5, <b>relative=-1</b><br/>value: Gi1/0/24 (target end)"]
        E1 --- L1
        E1 --- L2
    end
    before -- "lucidify_xml()" --> after
    subgraph after["After lucidify (default; --no-lucidify skips this)"]
        E2["edge object cell<br/>(unchanged)"]
        M1["child label cell<br/>x=-0.5, relative=1"]
        M2["child label cell<br/>x=0.5, <b>relative=1</b>"]
        E2 --- M1
        E2 --- M2
    end
```

Both labels stay children of their edge either way; only the flag changes. Applied to every
generated diagram by default; `--no-lucidify` leaves N2G's raw output in place, including
the `relative="-1"`.

### Known limitation: Cisco icons under Lucid import

`render/icons.py` maps device roles to `mxgraph.cisco19.*` shapes, verified against the
actual names in jgraph/drawio's `Sidebar-Cisco19.js` and then rendered through the draw.io
CLI rather than guessed. Lucidchart uses a different shape library, so these may still
degrade to plain boxes on import even with the correct names.

**This got worse, deliberately.** The classic `mxgraph.cisco.*` stencils these replaced were
named stencils an importer could at least look up; a cisco19 icon is drawn by a draw.io
JavaScript shape (`mxgraph.cisco19.rect` plus a `prIcon` name), which nothing outside
draw.io implements. The tradeoff was taken with that understood: draw.io is where these
diagrams are read, edited and exported to PNG, and the visual gain there is large.
`render/lucidify.py`'s label `relative` normalization (above) still gives the interface
labels their best chance of surviving an import.

**Status: implementation complete, live-import validation still pending.** Real
fidelity against an actual Lucidchart import has not yet been checked by a human with
Lucid access, since it requires interactive access this project's automation does not
have. Everything the renderer emits should be treated as unvalidated there — including the
root-bridge card fill, the `opacity` fade on uncaptured devices, and the legend, all of
which are draw.io style overrides. Checklist for whoever runs this:

1. Generate samples:
   `nettopo l2 -i tests/fixtures/captures -o /tmp/lucid-check`
   `nettopo stp -i tests/fixtures/stp_topology -o /tmp/lucid-check --all --group-mode topology`
2. Import `/tmp/lucid-check/l2/l2_full.drawio` and one of
   `/tmp/lucid-check/stp/*.drawio` into a Lucidchart document.
3. Record, here in this section: whether the Cisco device shapes render recognizably or
   degrade to plain boxes; whether the per-end link labels (e.g. `Gi1/0/1` at one end of
   the link and `Gi1/0/24` at the other) survived the import and stayed attached to their
   link; whether the root-bridge fill, the inferred-device fade and the
   forwarding/blocking link colors survived; and whether the legend box arrived intact.
   If the icons do degrade, the fallback worth costing is embedding SVG icons as
   `shape=image;image=data:image/svg+xml;base64,…`, which any importer can render.

## Security posture

`nettopo` makes zero network connections by design — it only reads local capture files
and writes local output files. `tests/test_no_network.py` enforces this by
monkeypatching `socket.socket` to fail and asserting a full run still succeeds; Phase 3
extends the base `parse`-only test to cover `nettopo l2` now that it pulls in
N2G/igraph, Phase 4 extends it again to cover `nettopo stp`, Phase 5 again for
`nettopo hsrp`, and it will extend further to cover `nettopo all` once Phase 7 adds that
command.

`utils/paths.py`'s `resolve_output_root()` is used by every command to resolve `-o`/
`--output` to an absolute path before anything is written. Its `sanitize_filename_component()`
and `safe_join()` guard against a filename derived from parsed data (e.g. a hostname
like `../../etc`) escaping the output directory; today's real output filenames don't
yet need them in practice — `l2`'s two filenames are a fixed lookup table, and `stp`'s
and `hsrp`'s come from the same `vlan_diagram_filename()` over VLAN ids, which are ints
parsed out of the model rather than arbitrary path input, so they can't contain a path
separator — but the helpers are unit-tested
(`tests/test_paths.py`) and ready for the day a filename is built from a raw string like
a hostname. `export/csv_export.py` separately neutralizes *cell* values that start with
a formula-triggering character (`=`, `+`, `-`, `@`) so a hostname or description can't
execute as a formula when the CSV is opened in spreadsheet software — a different attack
surface (CSV formula injection) from filename path traversal. See `PROJECT_SPEC.md`
section 11 for the full OWASP-adapted security review.
