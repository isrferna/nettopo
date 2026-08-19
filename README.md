# nettopo

A Python CLI that reads **saved Cisco `show` command outputs** (files only — no live
device connections in v1) and generates **network diagrams** in **draw.io format with
Cisco icons**, plus the intermediate data as **CSV tables**.

Four diagram views are produced from the same parsed data model:

- **L2** — physical/link-layer topology from CDP/LLDP, with interface labels and MLAG.
- **STP** — per-VLAN Rapid-PVST spanning-tree state (root, bridge IDs, priorities, port roles/states).
- **HSRP** — first-hop redundancy per SVI (virtual IP, priority, active/standby/listen).
- **BGP** — BGP neighbor (session) graph (AS numbers, session state, iBGP vs eBGP).

> `nettopo` is a working title — see [`PROJECT_SPEC.md`](PROJECT_SPEC.md) section 1.

## Status

**Phase 6 — BGP.** `nettopo bgp -i <dir>` now renders the BGP session graph: one diagram
for the whole network, with each captured router labeled by its AS number and BGP router
ID, each session labeled with its state and colored blue for iBGP or purple for eBGP, and
any peer no capture covers drawn faded and labeled by the address and AS the session named
it by. It takes no view-specific options, and `bgp.csv` is now populated.
`nettopo hsrp -i <dir>` (Phase 5) renders per-VLAN first-hop-redundancy diagrams: each
HSRP group is drawn as a virtual gateway carrying its virtual IP, with a link to every
router that offers it labeled with that router's SVI, role and priority — green for
active, amber for standby — and the active router highlighted. It takes `--vlan N` or
`--all` and writes one diagram per VLAN. `nettopo stp -i <dir>` (Phase 4) renders per-VLAN
spanning-tree diagrams: the root bridge is highlighted, links are colored by forwarding vs
blocking port state and labeled with role/state at each end. `nettopo l2 -i <dir>`
(Phase 3) renders devices styled with Cisco icons (`render/icons.py`) by inferred
`DeviceRole`, with per-end interface labels, `--endpoints all|network-only` filtering and
`--link-mode physical|port-channel` (MLAG links drawn once per bundle). Every diagram is
plain draw.io XML, written as N2G emits it: draw.io is the one tool these files target.
`nettopo all -i <dir>` (Phase 7) runs all
four views and every CSV export in one pass over a single ingest, writing the whole
`output/` tree. Every view is shown
end to end under [Example diagrams](#example-diagrams), generated from the capture sets in
[`examples/`](examples). See the delivery plan in
[`PROJECT_SPEC.md`](PROJECT_SPEC.md#14-delivery-plan-sequential-github-issues) and the
open issues for the phased build-out.

> **draw.io only.** The Cisco `mxgraph.cisco19.*` icons are drawn by draw.io's own code
> and no other tool implements them, so these files are meant to be opened in draw.io.
> Lucidchart export was tried and dropped — [`docs/architecture.md`](docs/architecture.md#why-there-is-no-lucidchart-export)
> records what its importer does to a generated file and why supporting it was not worth
> the cost.

## Installation

```bash
pip install nettopo
```

Pre-releases (`0.3.0rc1` and the like) are published from the same pipeline but `pip`
skips them unless asked: `pip install --pre nettopo`, or pin the exact version. Each
release is published to PyPI by `.github/workflows/publish.yml` when a `v*` tag is
pushed. To install from source for development:

```bash
git clone https://github.com/isrferna/nettopo.git
cd nettopo
pip install -e ".[dev]"
```

Requires Python 3.11+.

## Example diagrams

[`examples/campus/`](examples/campus) is a complete, self-contained capture set for a
six-switch campus: two core switches joined by a port-channel, two distribution
switches, two access switches, plus an edge router, two ESXi hosts and a third access
switch that no capture covers — ten devices in total. It is the source of every diagram
below except the last two, which come from the smaller
[`examples/hsrp-quad/`](examples/hsrp-quad) and
[`examples/bgp-edge/`](examples/bgp-edge). Every image is nettopo's own output, and the
`.drawio` files behind them are committed next to the captures. Regenerate them with:

```bash
nettopo l2   -i examples/campus -o examples/campus/diagrams
nettopo l2   -i examples/campus -o examples/campus/diagrams --endpoints network-only --link-mode port-channel
nettopo stp  -i examples/campus -o examples/campus/diagrams --all
nettopo hsrp -i examples/campus -o examples/campus/diagrams --all
nettopo hsrp -i examples/hsrp-quad -o examples/hsrp-quad/diagrams --all
nettopo bgp  -i examples/bgp-edge -o examples/bgp-edge/diagrams
```

The PNGs are exports of those same files, made with
[draw.io Desktop](https://www.drawio.com/)'s CLI — leaving out `-t/--transparent` is what
gives them a white background:

```bash
drawio -x -f png -s 2 -b 20 -o examples/campus/diagrams/l2/l2_full.png examples/campus/diagrams/l2/l2_full.drawio
```

> A PNG is a snapshot. Open the `.drawio` in [draw.io](https://app.diagrams.net) for the
> editable diagram — draggable nodes, and the hover tooltips that carry a port-channel's
> member interfaces.

### `nettopo l2` — physical topology

Ten nodes, thirteen links; each link is labeled with the physical interface at each end,
and each node is drawn with the icon for its role. The role comes from the chassis the
device reports — `cisco C9500-16X` for the core pair, `cisco WS-C2960X` for the access
switches, `cisco ISR4331/K9` for `edge-rtr`, `VMware ESX` for the two ESXi hosts — falling
back to the capabilities its neighbors advertised over CDP/LLDP when the platform names
nothing recognizable. A legend names every role the diagram actually contains.

![L2 topology of the campus example: ten devices, thirteen links, each end labeled with
its physical interface](examples/campus/diagrams/l2/l2_full.png)

Source: [`l2/l2_full.drawio`](examples/campus/diagrams/l2/l2_full.drawio).

### `nettopo l2 --endpoints network-only --link-mode port-channel`

The same topology with the two flags applied: the ESXi hosts are gone (they advertise
neither `Router` nor `Switch`), and the two physical core links have collapsed into the
single bundle both switches call `Po1`. Its member interfaces move into the link's
draw.io hover tooltip (`Gi1/0/1 — Gi1/0/1`, `Gi1/0/2 — Gi1/0/2`), which the PNG below
cannot show but the `.drawio` does. Eight nodes, ten links.

![The same topology without the ESXi hosts, with the two core links collapsed into a
single link labeled Po1 at both ends](examples/campus/diagrams/l2/l2_network-only_port-channels.png)

Source:
[`l2/l2_network-only_port-channels.drawio`](examples/campus/diagrams/l2/l2_network-only_port-channels.drawio).

### `nettopo stp --vlan 10` — spanning tree for the user VLAN

Switches only: `edge-rtr` and the two ESXi hosts are gone. `core-sw1` is the root bridge
(gold card); every other node carries its bridge MAC and effective priority.
`acc-sw3` has no capture of its own, so it is drawn faded, in italics, and labeled with its
name alone — it is included because the port facing it (`dist-sw2 Gi1/0/22`) is not an Edge
port, the same filter that keeps the ESXi hosts out. Green links forward at both ends;
red links have a blocked end. The three blocked ports are what breaks the two loops in
the topology. The legend lists only the markings this particular tree uses.

![Spanning tree for VLAN 10: core-sw1 with a gold card as root bridge, green forwarding
links, three red links with a blocked end, acc-sw3 drawn
faded](examples/campus/diagrams/stp/stp_vlan10.png)

Source: [`stp/stp_vlan10.drawio`](examples/campus/diagrams/stp/stp_vlan10.drawio).

Note that the core-to-core link is drawn **once**, labeled `Po1`: spanning tree treats a
bundle as one logical port, and `show spanning-tree` only ever names `Po1` while
CDP/LLDP only ever name `Gi1/0/1`/`Gi1/0/2`. `show etherchannel summary` is what joins
the two — drop it from `core-sw1.txt`/`core-sw2.txt` and this link disappears.

### `nettopo stp --vlan 30` — the same network, a different tree

VLAN 30 is rooted on `core-sw2` (`spanning-tree vlan 30 root primary`, with `core-sw1`
as secondary). Same devices, same cabling, different tree: the blocked ports move from
`Gi1/0/2` to `Gi1/0/1` on both distribution switches, and the core port-channel reverses
role. This is why the view renders one diagram per VLAN rather than a single "STP
diagram".

![Spanning tree for VLAN 30: the same devices with core-sw2 as root bridge and the
blocked ports moved to the other core switch](examples/campus/diagrams/stp/stp_vlan30.png)

Source: [`stp/stp_vlan30.drawio`](examples/campus/diagrams/stp/stp_vlan30.drawio).

### What `--group-mode` does to this capture set

The example has four VLANs, and VLANs 10, 20 and 99 produce the identical picture above
— only VLAN 30 differs. VLAN 99 is the interesting case: its tree matches 10 and 20
exactly, but nobody configured `core-sw2` as its secondary root, so its *priorities*
differ. That is precisely the line between the two grouping modes:

| Command | Files written into `output/stp/` |
|---|---|
| `nettopo stp -i examples/campus --all` | `stp_vlan10`, `stp_vlan20`, `stp_vlan30`, `stp_vlan99` — four identical-looking diagrams for three identical trees |
| `nettopo stp -i examples/campus --all --group-mode strict` | `stp_vlans-10_20`, `stp_vlan30`, `stp_vlan99` — 99 splits off on its priority |
| `nettopo stp -i examples/campus --all --group-mode topology` | `stp_vlans-10_20_99`, `stp_vlan30` — two diagrams, one per distinct tree |

### `nettopo hsrp --vlan 10` — who answers for the default gateway

The core pair also runs HSRP on VLANs 10, 20 and 30, aligned with the spanning trees:
`core-sw1` is active where it is root, `core-sw2` is active for VLAN 30. The rounded box
is not a device — it is the virtual gateway `10.10.10.1`, the address the VLAN's hosts are
configured with. Each router carries its own SVI address (`10.10.10.2`, `10.10.10.3`)
under its name, so both halves of the first hop are on the page, and links to the gateway
labeled with its SVI, HSRP role and priority: green for the router currently answering,
amber for the one waiting to take over. The active router carries the same gold card the
STP view gives a root bridge.

![HSRP for VLAN 10: core-sw1 at 10.10.10.2 active with priority 150 on a green link to the
virtual gateway 10.10.10.1, core-sw2 at 10.10.10.3 standby with priority 100 on an amber
link](examples/campus/diagrams/hsrp/hsrp_vlan10.png)

Source: [`hsrp/hsrp_vlan10.drawio`](examples/campus/diagrams/hsrp/hsrp_vlan10.drawio).

There is no `--group-mode` here, unlike `stp`: `nettopo hsrp -i examples/campus --all`
writes `hsrp_vlan10`, `hsrp_vlan20` and `hsrp_vlan30`, always one per VLAN. VLANs 10 and
20 have the same active/standby split, so the STP view would happily group them — but
their gateways are `10.10.10.1` and `10.10.20.1`, and every router holds a different SVI
address in each. There is no picture that covers both without either hiding one VLAN's
addresses or printing two of everything.

### A group with four members — active, standby, and two listening

A two-switch gateway pair is the common case, but an HSRP group can have any number of
members and only ever two of them are named: one active, one standby. Everybody else sits
in **Listen**, watching the hellos and waiting for an election.
[`examples/hsrp-quad/`](examples/hsrp-quad) is a small capture set for exactly that — VLAN
50 spans two buildings, each with a pair of layer-3 switches, and all four share one
group:

| Router | SVI address | Priority | State |
|---|---|---|---|
| `bldg-a-sw1` | `10.20.50.2` | 150 | Active — highlighted, green link |
| `bldg-a-sw2` | `10.20.50.3` | 140 | Standby — amber link |
| `bldg-b-sw1` | `10.20.50.4` | 110 | Listen — neutral link |
| `bldg-b-sw2` | `10.20.50.5` | 100 | Listen — neutral link |

![HSRP for VLAN 50 with four members: the virtual gateway 10.20.50.1 in the middle, the
active bldg-a-sw1 on a green link, the standby bldg-a-sw2 on an amber link, and two
listening switches on neutral gray links](examples/hsrp-quad/diagrams/hsrp/hsrp_vlan50.png)

Source: [`hsrp/hsrp_vlan50.drawio`](examples/hsrp-quad/diagrams/hsrp/hsrp_vlan50.drawio).

The two listeners are why every node carries its **own** address and not just the virtual
one. `show standby brief` reports the active and standby routers by address — that is
what its Active and Standby columns are — but it never names anyone else, so
`10.20.50.4` and `10.20.50.5` appear nowhere in any of the four captures' HSRP output.
They come from `show ip interface brief` instead, which is why that command is worth
capturing even though the HSRP view needs no topology. The legend lists only the two
colors this group uses; a neutral link means the router is in the group but neither
answering for it nor next in line.

### `nettopo bgp` — who peers with whom, and where the AS boundary is

The campus switches run no BGP, so this one comes from
[`examples/bgp-edge/`](examples/bgp-edge): three routers in AS 65001 — two core, one edge
— fully meshed over iBGP, with `edge-r1` holding the two eBGP sessions to the outside.

![BGP session graph: core-r1, core-r2 and edge-r1 drawn as routers labeled AS 65001 over
their router IDs 10.255.0.1, 10.255.0.2 and 10.255.0.3, joined by three blue iBGP links
labeled Established, with edge-r1 also joined by purple eBGP links to two faded boxes —
198.51.100.1 AS 65100, labeled Established, and 203.0.113.9 AS 65200, labeled
Idle](examples/bgp-edge/diagrams/bgp/bgp.png)

Source: [`bgp/bgp.drawio`](examples/bgp-edge/diagrams/bgp/bgp.drawio).

Each router carries its AS number and its BGP router ID under its name — here the
loopback each one uses as its identity, which is also what makes the matching below work.
Each session is drawn once, though the mesh's three sessions are each reported twice —
once by the router at each end. `show ip bgp summary` names the far end by IP and nothing
else, so nettopo matches each peer address against the addresses the captures report in
`show ip interface brief`: where it finds one, the two reports become one link between two
named routers. `198.51.100.1` and `203.0.113.9` match nothing — no capture covers them —
so they keep a node of their own, faded like any other device known only through someone
else's report, and labeled with the address and AS number the session named them by.

The state on each link is read from the summary's last column, which IOS overloads: it
prints a prefix count for a session that is up and a state word for one that is not, so a
count is reported as `Established` and anything else verbatim — `203.0.113.9` here never
came up at all. `bgp.csv` carries the same data per reported session, both directions
included.

## Usage

```
nettopo [--version] [--log-level LEVEL] <command> [options]
```

Every command reads a **directory** of saved capture files (see
[Preparing captures](#preparing-captures) below) and writes into an output directory,
creating it if needed. `parse`, `l2`, `stp`, `hsrp` and `bgp` each produce one part of
that output; [`all`](#nettopo-all) produces all of it in one run.

That input directory defaults to `~/configs`, so once your captures live there you can
drop `-i` entirely and just run `nettopo all`.

### Global options

| Option | Values | Default | Meaning |
|---|---|---|---|
| `--version` | flag | — | Print the installed version and exit, without a subcommand: `nettopo --version`. Read from the installed distribution's metadata, so after bumping `pyproject.toml` re-run `pip install -e .` for it to catch up. |
| `--log-level` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | `INFO` | Logging verbosity. Goes before the subcommand: `nettopo --log-level DEBUG l2 -i ./captures`. |

### Options common to every command

| Option | Values | Default | Meaning |
|---|---|---|---|
| `-i`, `--input` | directory path | `~/configs` | Directory of saved device captures to read. See [Preparing captures](#preparing-captures). The tilde is expanded by nettopo, so the default works even when the shell never sees it. |
| `-o`, `--output` | directory path | `./output` | Directory to write generated output into (created if it doesn't exist). |
| `--platform` | an [ntc-templates](https://github.com/networktocode/ntc-templates) platform name | `cisco_ios` | Fallback platform used to pick the right parsing template when a device's own platform can't be detected from its `show version` output. IOS and IOS-XE both use `cisco_ios`. |

### `nettopo parse`

Ingests captures, builds the data model, and writes every CSV table — no diagrams. This
is the primary debugging aid: if a diagram looks wrong, inspect the CSVs first to
localize the fault to parsing vs. rendering.

```bash
nettopo parse -i ./captures -o ./output
```

Writes `output/csv/devices.csv` (including each device's serial, from its own
`show version` or from the name a Nexus neighbor advertises; its platform, from its own
`show version` or from the CDP/LLDP report of a neighbor; and its management IP, from
CDP's `Management address(es)` block or LLDP's management TLV), `interfaces.csv`,
`neighbors.csv`, `vlans.csv`, `stp.csv` (base *and* effective bridge priority — see
[PROJECT_SPEC.md §6](PROJECT_SPEC.md#6-data-model)), `hsrp.csv` (one row per group member,
with the group's virtual IP beside that member's SVI, priority, role and preempt flag),
and `bgp.csv` (one row per session as each device reported it).

One row per device and per adjacency, regardless of how many names its neighbors use for
it: CDP and LLDP disagree constantly (`nxos-core1` vs `nxos-core1(FDO21120U5D)` vs
`nxos-core1.example.com`), and those spellings are correlated into one device before the
model is built — see
[PROJECT_SPEC.md §5.2](PROJECT_SPEC.md#5-normalization-central-services).

### `nettopo l2`

Renders the physical/link-layer topology (from CDP/LLDP) as a draw.io diagram: nodes are
devices styled with Cisco icons by inferred role, and links carry per-end interface
labels. Needs `show cdp neighbors detail` and/or `show lldp neighbors detail` in the
captures — see [Which commands each subcommand
needs](#which-commands-each-subcommand-needs).

| Option | Values | Default | Meaning |
|---|---|---|---|
| `--endpoints` | `all`, `network-only` | `all` | `all` includes every discovered device. `network-only` drops any device that isn't a source capture and wasn't reported by a neighbor with `Router`/`Switch` CDP/LLDP capabilities (i.e. drops hosts/phones, keeps the network). |
| `--link-mode` | `physical`, `port-channel` | `physical` | What a drawn link represents. `physical`: one link per discovered adjacency, labeled with the physical interface at each end. `port-channel`: adjacencies belonging to the same bundle collapse into a single link labeled `Po150` (MLAG), with the member interfaces in the link's hover tooltip. Links with no port-channel on either end are drawn the same way in both modes, so this option only changes the diagram where bundles actually exist. |

```bash
nettopo l2 -i ./captures --endpoints network-only --link-mode port-channel
```

Writes `output/l2/l2_full.drawio` (endpoints `all`) or
`output/l2/l2_network-only.drawio` (endpoints `network-only`); under `--link-mode
port-channel` the filename gains a `_port-channels` suffix
(`l2_full_port-channels.drawio`), so both link modes of the same topology can live side
by side in one output directory.

Port-channel mode needs `show etherchannel summary` (IOS/IOS-XE) or `show port-channel
summary` (NX-OS) in the capture — without it no bundles are known and the diagram is
identical to `physical`. Bundle membership is also exported in `interfaces.csv`
(`po_id`, `po_members`), which is the quickest way to check whether that command was
captured and parsed. The tooltip is a draw.io feature: hover the link in draw.io to see
which physical ports the bundle carries.

### `nettopo stp`

Renders per-VLAN Rapid-PVST spanning-tree diagrams: switches only, root bridge
highlighted, links colored by forwarding (green) vs. blocking (red) port state and
labeled with role/state at each end. Node labels show the bridge MAC and effective
priority (base priority is in `stp.csv`).

Needs `show spanning-tree` **and** a neighbor-discovery command (`show cdp neighbors
detail` / `show lldp neighbors detail`) in the captures: spanning-tree output alone never
says who is on the other end of a port, so without CDP/LLDP the diagram has nodes and no
links. If the switches are joined by **port-channels**, `show etherchannel summary`
(IOS/IOS-XE) or `show port-channel summary` (NX-OS) is required as well — spanning-tree
names the bundle (`Po1`) while CDP/LLDP name its members (`Gi1/0/1`), and only the bundle
table connects the two. See [Which commands each subcommand
needs](#which-commands-each-subcommand-needs).

Each port-channel is drawn as a single link labeled with the bundle name, with the member
interfaces in the link's hover tooltip: spanning-tree treats a bundle as one logical port,
so drawing one line per member would misrepresent it.

Switches that appear only in a neighbor's CDP/LLDP output — no capture of their own — are
included **faded, in italics** and labeled with their name alone, since there is no
bridge data to show for them. They are reached only through ports that are *not*
Edge/PortFast, which is what keeps phones, access points and servers out of a
spanning-tree diagram.

If the root bridge is one of those uncaptured switches, it is highlighted only when an
LLDP chassis address matches the root address exactly. Without a match the run logs a
warning naming the root's MAC and highlights nothing, rather than guessing.

A diagram with several nodes and no links is always reported as a warning. To see why each
individual link was dropped, raise the log level — note that `--log-level` is a global
option, so it goes *before* the subcommand:

```bash
nettopo --log-level DEBUG stp -i ./captures --all
```

| Option | Values | Default | Meaning |
|---|---|---|---|
| `--vlan` | VLAN id, e.g. `10` | *(none)* | Restrict to a single VLAN's diagram. Mutually exclusive with `--group-mode`. |
| `--group-mode` | `per-vlan`, `strict`, `topology` | `per-vlan` | How to group VLANs that would render identically. `per-vlan`: one diagram per VLAN, no grouping. `strict`: group VLANs whose root, bridge priorities, *and* port roles/states all match. `topology`: group VLANs whose root and port roles/states match, ignoring configured priorities (a looser match than `strict`). Mutually exclusive with `--vlan`. |
| `--all` | flag | off | Write every resulting diagram (one per VLAN, or one per group under `--group-mode`) into `output/stp/`. |

Either `--vlan` or `--all` is required — with neither, there's no single sensible
default to render out of a potentially many-VLAN model, so the command exits with an
error asking you to pick one.

```bash
nettopo stp -i ./captures --vlan 10                       # one diagram, VLAN 10 only
nettopo stp -i ./captures --all                            # one diagram per VLAN
nettopo stp -i ./captures --all --group-mode strict         # grouped by exact match
nettopo stp -i ./captures --all --group-mode topology       # grouped by topology only
```

Filenames: `output/stp/stp_vlan10.drawio` for a single VLAN; for a group, a sorted,
filesystem-safe name listing every VLAN it covers, e.g.
`output/stp/stp_vlans-10_20_30.drawio`.

### `nettopo hsrp`

Renders per-VLAN HSRP diagrams: which routers offer the VLAN's default gateway, which one
currently answers for it, at what priority, and on which address. Needs only `show standby
brief` in the captures — unlike `stp`, this view draws no physical links, so no
neighbor-discovery command is required (`show version` still helps, by naming each device
from its own capture rather than from its filename).

Each HSRP group is drawn as a **virtual gateway**: a plain rounded box labeled with the
VLAN, the group number and the virtual IP. It is deliberately not given a Cisco icon,
because it is an address rather than a device. Every router running that group links to
it, labeled `Vl10 active/150` — its SVI, HSRP role and priority — with the link colored
green when that router is active for the group and amber when it is the standby. The
active router itself is highlighted with a gold card.

Each router is also labeled with **its own SVI address** in that VLAN, beside the virtual
one, which is what tells you which box a given traceroute hop or ping reply actually is.
That address comes from `show ip interface brief` (or `show interfaces`), not from `show
standby brief` — the brief output names only the active and standby routers, and only by
address, so a member that is merely listening cannot be placed from it at all. Add one of
those two commands to the captures and every member gets its address; without them the
nodes are labeled with their names alone rather than a guess.

One VLAN is one diagram, including when its SVI carries **several groups**: two gateways
load-sharing a VLAN (each active for one group, standby for the other) is one picture with
two virtual gateways in it, not two pictures.

HSRP running on a routed port or a subinterface rather than an SVI is skipped with a
warning naming the interface: diagrams and CSV rows alike are keyed by VLAN, and such a
group has no VLAN to be keyed by.

| Option | Values | Default | Meaning |
|---|---|---|---|
| `--vlan` | VLAN id, e.g. `10` | *(none)* | Restrict to a single VLAN's diagram. |
| `--all` | flag | off | Write one diagram per VLAN into `output/hsrp/`. |

As with `stp`, either `--vlan` or `--all` is required.

```bash
nettopo hsrp -i ./captures --vlan 10                        # one diagram, VLAN 10 only
nettopo hsrp -i ./captures --all                            # one diagram per VLAN
```

Filenames are `output/hsrp/hsrp_vlan10.drawio`, one per VLAN.

Unlike `stp`, this view has no `--group-mode`, and passing one is an error. Grouping means
several VLANs render identically, and two VLANs' HSRP never does: each has its own virtual
IP and its own SVI address on every router, and the virtual IP is the headline fact of the
diagram. A grouped picture would have to drop every VLAN's addresses but one, or stack
three sets of addresses onto the same two boxes. `hsrp.csv` lists every VLAN's detail side
by side when that is what you need.

### `nettopo bgp`

Renders the BGP neighbor (session) graph: which routers peer with which, in what AS, and
whether each session is up. Needs only `show ip bgp summary` in the captures;
`show ip interface brief` (or `show interfaces`) is what lets two captured routers be
recognized as the two ends of one session rather than as four separate boxes.

```bash
nettopo bgp -i ./captures
```

There is one diagram for the whole network, at `output/bgp/bgp.drawio` — a fixed
filename, since the command takes no view-specific options. BGP sessions do not partition
into VLANs the way STP and HSRP do, so there is nothing for a `--vlan`/`--all` pair to
select between; a network large enough to want splitting up wants it by AS or by region,
which v1 does not model.

Nodes are labeled with the router's name over its AS number and its BGP router ID
(`RID 10.255.0.1`, read from the summary's `BGP router identifier` header line), links
with the session's state (`Established`, `Idle`, `Active`, …) and colored by session
type — blue for iBGP, purple for eBGP. When both ends of a session were captured and they
disagree about its state, both are shown (`Established / Active`), in device-name order.
A line is left out when its value is unknown, so a device we hold no summary for is
labeled with its name alone.

A peer whose address matches no captured interface keeps a node of its own, drawn faded
and labeled with its address and AS number — never a router ID, since the summary prints
one for the device reporting it and names every far end by address only. `peer_device` in `bgp.csv` stays empty
regardless: resolving a peer IP to a hostname in the *model* is out of scope for v1
(see [`PROJECT_SPEC.md` §2](PROJECT_SPEC.md)), so the address matching is a drawing
decision only and the CSV stays a faithful record of what each device reported.

v1 draws the session graph and nothing more — no route tables, policies, communities or
route-reflector modeling. Only the default VRF is read: `show ip bgp summary` covers it,
and every row's `vrf` column is `default`.

### `nettopo all`

Runs every view and every CSV export in one invocation, producing the complete `output/`
tree from [`PROJECT_SPEC.md` §8](PROJECT_SPEC.md#8-rendering-and-export).

```bash
nettopo all -i ./captures -o ./output
```

```
output/
├── csv/          devices, interfaces, neighbors, vlans, stp, hsrp, bgp
├── l2/           l2_full.drawio, l2_full_port-channels.drawio, l2_network-only.drawio
├── stp/          one diagram per VLAN
├── hsrp/         one diagram per VLAN
└── bgp/          bgp.drawio
```

It takes only the [common options](#options-common-to-every-command) — no `--vlan`,
`--endpoints`, `--link-mode` or `--group-mode`. `all` is the "everything these captures
support" command, so those choices are made for you:

- **Per-VLAN, always.** The STP view runs as `--group-mode per-vlan`, which never
  collapses two VLANs into one drawing, and both per-VLAN views draw every VLAN they
  found. To collapse VLANs that render identically, run
  [`nettopo stp --group-mode topology`](#nettopo-stp) separately.
- **Three L2 diagrams.** The physical view, the same view with port-channels collapsed
  into one link per bundle, and the network-only view (endpoints dropped). The fourth
  combination — `network-only` *and* port-channels — is left out on purpose: dropping
  endpoints already removes what makes a dense L2 diagram unreadable, so it would differ
  from `l2_network-only.drawio` only on the occasional bundle between two network devices.
  Run [`nettopo l2`](#nettopo-l2) directly if you want it.
- **A view with no data is skipped, not an error.** Access switches that speak no BGP, or
  routers with no spanning tree, are ordinary input. Each such view logs a `WARNING`
  naming what it skipped, no directory is created for it, and the run still exits `0`.
  Only an unreadable input directory or a failed write makes `all` exit non-zero. A view
  you asked for by name (`nettopo bgp`) still writes its file, empty — being explicit is
  the difference.

Ingestion and parsing — the expensive stages — run **once** for all five outputs, rather
than once per command as running them in sequence would. `all` drives the same views the
individual commands do, not a second implementation of them: every file it writes is
byte-identical to what the corresponding command would have produced.

### Preparing captures

The `-i`/`--input` directory holds one text file per device. Each file concatenates the
outputs of several `show` commands, each preceded by that device's prompt line
(`hostname#show ...`) — this is how `nettopo` both identifies the device as a *source*
device (as opposed to one only ever mentioned by a neighbor) and splits the file back
into per-command sections. `tests/fixtures/captures/` has worked examples. Files are read
as `utf-8-sig`, so a leading UTF-8 BOM is handled transparently.

#### Which commands each subcommand needs

Nothing is mandatory: a missing command means the data it feeds is simply absent (empty
CSV columns, missing links, a view with nothing to draw), never an error. The table below
is what each subcommand needs to produce a *complete* result.

| Subcommand | Required | Optional, adds |
|---|---|---|
| `parse` | — | every command in the next table; each fills its own CSV table or columns |
| `l2` | `show cdp neighbors detail` and/or `show lldp neighbors detail` | `show version` (device naming) · `show etherchannel summary` / `show port-channel summary` (only for `--link-mode port-channel`) |
| `stp` | `show spanning-tree` **and** `show cdp neighbors detail` / `show lldp neighbors detail` | `show version` (device naming) · `show etherchannel summary` / `show port-channel summary` (**required** when links are bundled) · `show lldp neighbors detail` (to identify a root bridge outside the captures) |
| `hsrp` | `show standby brief` | `show ip interface brief` / `show interfaces` (each member's own SVI address on its node) · `show version` (device naming) |
| `bgp` | `show ip bgp summary` | `show ip interface brief` / `show interfaces` (matches a peer's address to a captured router, so one session is drawn as one link) · `show version` (device naming) |
| `all` | — | everything in this table; each view it finds no data for is skipped with a warning |

> **`stp` needs CDP/LLDP too.** `show spanning-tree` reports a device's *own* bridge and
> port roles/states, but never says who is on the other end of a port — on its own it
> yields nodes and no edges. The STP view draws its links from the CDP/LLDP topology and
> labels each end with the spanning-tree state found there, so without a neighbor
> discovery command you get a diagram of disconnected boxes.
>
> **`stp` needs the bundle table when links are bundled.** The join between the two
> sources above is the interface name, and for a port-channel the two sources disagree:
> spanning-tree only ever says `Po1`, CDP/LLDP only ever say `Gi1/0/1`. `show etherchannel
> summary` (or `show port-channel summary`) is what maps one to the other. Without it, a
> fully bundled network produces the same disconnected boxes — every switch drawn, not one
> line between them.

What each command contributes, whichever subcommand you run:

| `show` command | Fills |
|---|---|
| `show version` | `platform`, `model`, `os` and `serial` in `devices.csv`, and the canonical hostname every neighbor's spelling is correlated onto — without it that name falls back to the prompt line, which is usually the same |
| `show cdp neighbors detail` | Links between devices (`neighbors.csv`, and the links in both the L2 and STP diagrams), plus each neighbor's role/icon, platform and management IP |
| `show lldp neighbors detail` | The same, for neighbors that don't speak CDP. Where both describe one adjacency, CDP wins |
| `show ip interface brief` | `interfaces.csv`: admin/operational state and IP per interface — including the SVI addresses the HSRP diagrams label their routers with |
| `show interfaces` | `interfaces.csv`: descriptions, precise IP/prefix, link state. Richer than `show ip interface brief` and wins where the two overlap |
| `show vlan brief` | `vlans.csv` |
| `show spanning-tree` | `stp.csv` and the STP diagrams: bridge IDs, base and effective priority, per-port role/state |
| `show standby brief` | `hsrp.csv` and the HSRP diagrams: each group's virtual IP, and each member's SVI, priority, role and preempt flag |
| `show ip bgp summary` | `bgp.csv` and the BGP diagram: each session's peer address, both AS numbers, its state and whether it is iBGP or eBGP — plus the device's own `asn` and `router_id` in `devices.csv` |
| `show etherchannel summary` (IOS/IOS-XE) · `show port-channel summary` (NX-OS) | `po_id`/`po_members` in `interfaces.csv`, and the bundles `l2 --link-mode port-channel` collapses links onto |

A capture covering everything implemented today:

```
sw1-access#show version
...
sw1-access#show cdp neighbors detail
...
sw1-access#show lldp neighbors detail
...
sw1-access#show ip interface brief
...
sw1-access#show interfaces
...
sw1-access#show vlan brief
...
sw1-access#show spanning-tree
...
sw1-access#show standby brief
...
sw1-access#show etherchannel summary
...
sw1-access#show ip bgp summary
...
```

#### Three things that trip captures up

- **Run each command with no arguments.** A prompt line has to match the command *in
  full*, so `show spanning-tree vlan 10` is not recognized as `show spanning-tree` and
  that section is skipped silently. Capture the unfiltered output and let `nettopo` do
  the per-VLAN split.
- **Abbreviations are fine.** `show ver`, `show cdp neigh det`, `show ip int br` and
  `show span` all match, so a capture taken by typing short forms works as-is.
- **One section per command per file.** Only the first matching section is read; a
  command captured twice contributes its first occurrence only.

The prompt line drives all of this, so keep it — the filename is only a fallback for
naming a device whose file has no prompt line at all. Both `hostname#` and `hostname>`
work.

See [`PROJECT_SPEC.md` §9](PROJECT_SPEC.md#9-cli-design) for the CLI design rationale.

## Documentation

- [`examples/`](examples) — runnable capture sets, including the one behind the diagrams above.
- [`PROJECT_SPEC.md`](PROJECT_SPEC.md) — scope, architecture, data model, CLI, delivery plan.
- [`docs/architecture.md`](docs/architecture.md) — components, call flow, design decisions.
- [`CLAUDE.md`](CLAUDE.md) — engineering conventions (workflow, coding principles, security review).
- [`CHANGELOG.md`](CHANGELOG.md) — release history.

## Contributing

Work is tracked as GitHub issues, one per delivery-plan phase (see `PROJECT_SPEC.md`
section 14). Each change lands via a pull request from a `feat/…`/`fix/…` branch into
`main`; direct pushes to `main` are disabled. See [`CLAUDE.md`](CLAUDE.md) for the full
workflow and coding conventions.

## Security

This tool makes **zero network connections** by design — it only reads local capture
files. See [`PROJECT_SPEC.md`](PROJECT_SPEC.md#11-security-review-owasp-adapted) for the
full OWASP-adapted security review.

## License

[MIT](LICENSE)
