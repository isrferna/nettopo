# nettopo

A Python CLI that reads **saved Cisco `show` command outputs** — or collects them itself
over SSH — and generates **network diagrams** in **draw.io format with Cisco icons**,
plus the intermediate data as **CSV tables**.

Four diagram views are produced from the same parsed data model:

- **L2** — physical/link-layer topology from CDP/LLDP, with interface labels and MLAG.
- **STP** — per-VLAN Rapid-PVST spanning-tree state (root, bridge IDs, priorities, port roles/states).
- **HSRP** — first-hop redundancy per SVI (virtual IP, priority, active/standby/listen).
- **BGP** — BGP neighbor (session) graph (AS numbers, session state, iBGP vs eBGP).

> `nettopo` is a working title — see [`PROJECT_SPEC.md`](PROJECT_SPEC.md) section 1.

## Status

All eight phases of the
[delivery plan](PROJECT_SPEC.md#14-delivery-plan-sequential-github-issues) are delivered:
the four diagram views, the CSV export, [`all`](https://github.com/netcraftworks/nettopo/wiki/nettopo-all)
(everything in one pass over a single ingest), and
[`collect`](https://github.com/netcraftworks/nettopo/wiki/nettopo-collect) (read-only live
collection over SSH). See [`CHANGELOG.md`](CHANGELOG.md) for the release history.

> **draw.io only.** The Cisco `mxgraph.cisco19.*` icons are drawn by draw.io's own code
> and no other tool implements them, so these files are meant to be opened in draw.io.
> Lucidchart export was tried and dropped —
> [`docs/architecture.md`](docs/architecture.md#why-there-is-no-lucidchart-export) records why.

## Installation

```bash
pip install nettopo
```

That is everything except live collection. To also collect captures from devices over SSH:

```bash
pip install 'nettopo[collect]'
```

The extra pulls in netmiko and PyYAML. Keeping them optional is deliberate rather than
tidy-mindedness: without the extra there is no networking library present in the
environment at all, which is what makes the zero-network guarantee below true by
construction rather than by discipline.

Pre-releases exist too; `pip` skips them unless asked (`pip install --pre nettopo`).
To install from source for development:

```bash
git clone https://github.com/netcraftworks/nettopo.git
cd nettopo
pip install -e ".[dev,collect]"
```

Requires Python 3.11+.

## Quickstart

```bash
nettopo collect --inventory devices.txt   # devices -> ~/configs, over SSH
nettopo all                               # ~/configs -> ./output
```

`collect` asks for the credentials on the terminal, sends nothing but `show` commands,
and writes one capture file per device into `~/configs` — the directory every other
command reads by default, so `-i` can be dropped entirely. If you already have captures
saved by hand, skip `collect` and point `-i` at them (see
[Preparing Captures](https://github.com/netcraftworks/nettopo/wiki/Preparing-Captures)
for the file format). `all` then writes the complete output tree:

```
output/
├── csv/          devices, interfaces, neighbors, vlans, stp, hsrp, bgp
├── l2/           l2_full.drawio, l2_full_port-channels.drawio, l2_network-only.drawio
├── stp/          one diagram per VLAN
├── hsrp/         one diagram per VLAN
└── bgp/          bgp.drawio
```

## Commands

```
nettopo [--version] [--log-level LEVEL] <command> [options]
```

Every command reads a directory of capture files (`-i`, default `~/configs`) and writes
into an output directory (`-o`, default `./output`). Each links to its full reference in
the [wiki](https://github.com/netcraftworks/nettopo/wiki):

| Command | What it does |
|---|---|
| [`collect`](https://github.com/netcraftworks/nettopo/wiki/nettopo-collect) | Gathers the captures from the devices over SSH — read-only, serial, stops at the first error |
| [`parse`](https://github.com/netcraftworks/nettopo/wiki/nettopo-parse) | CSV tables only, no diagrams — the primary debugging aid |
| [`l2`](https://github.com/netcraftworks/nettopo/wiki/nettopo-l2) | Physical topology from CDP/LLDP, with `--endpoints` and `--link-mode` filtering |
| [`stp`](https://github.com/netcraftworks/nettopo/wiki/nettopo-stp) | Per-VLAN spanning-tree diagrams, with `--group-mode` to collapse identical trees |
| [`hsrp`](https://github.com/netcraftworks/nettopo/wiki/nettopo-hsrp) | Per-VLAN first-hop-redundancy diagrams |
| [`bgp`](https://github.com/netcraftworks/nettopo/wiki/nettopo-bgp) | The BGP session graph for the whole network |
| [`all`](https://github.com/netcraftworks/nettopo/wiki/nettopo-all) | Every view and every CSV in one run over a single ingest |

## Example diagrams

Every image is nettopo's own output, generated from the runnable capture sets in
[`examples/`](examples); the `.drawio` files are committed next to the captures. The full
six-diagram walkthrough is in the
[Example Gallery](https://github.com/netcraftworks/nettopo/wiki/Example-Gallery) — here
are three of them.

**`nettopo l2`** — the campus example: ten devices, thirteen links, each end labeled with
its physical interface, each node drawn with the Cisco icon for its inferred role.

![L2 topology of the campus example: ten devices, thirteen links, each end labeled with
its physical interface](examples/campus/diagrams/l2/l2_full.png)

**`nettopo stp --vlan 10`** — the same network's spanning tree: `core-sw1` highlighted as
root, green links forwarding, red links with a blocked end, and the uncaptured `acc-sw3`
drawn faded.

![Spanning tree for VLAN 10: core-sw1 with a gold card as root bridge, green forwarding
links, three red links with a blocked end, acc-sw3 drawn
faded](examples/campus/diagrams/stp/stp_vlan10.png)

**`nettopo hsrp --vlan 50`** — a four-member HSRP group: the virtual gateway in the
middle, the active router on a green link, the standby on amber, and two listeners on
neutral gray.

![HSRP for VLAN 50 with four members: the virtual gateway 10.20.50.1 in the middle, the
active bldg-a-sw1 on a green link, the standby bldg-a-sw2 on an amber link, and two
listening switches on neutral gray links](examples/hsrp-quad/diagrams/hsrp/hsrp_vlan50.png)

## Documentation

- [Wiki](https://github.com/netcraftworks/nettopo/wiki) — full command reference,
  [capture preparation](https://github.com/netcraftworks/nettopo/wiki/Preparing-Captures),
  and the [example gallery](https://github.com/netcraftworks/nettopo/wiki/Example-Gallery).
- [`examples/`](examples) — runnable capture sets, including the ones behind the diagrams above.
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

Every command except `collect` makes **zero network connections** by design — they only
read local capture files. That boundary is enforced rather than asserted:
`tests/test_no_network.py` monkeypatches `socket.socket` to fail and runs every other
command end to end, and a dedicated CI job proves the whole diagram pipeline runs with no
networking library installed.

`collect`, the one command that opens a socket, sends nothing but `show` commands
(checked at the moment of sending), accepts no password on the command line, stores no
credential anywhere, requires known SSH host keys unless you opt out, and stops at the
first error so a mistyped password costs one failed authentication attempt, not a
fleet-wide lockout. Details in
[its wiki page](https://github.com/netcraftworks/nettopo/wiki/nettopo-collect); the full
OWASP-adapted review is
[`PROJECT_SPEC.md` §11](PROJECT_SPEC.md#11-security-review-owasp-adapted).

## License

[MIT](LICENSE)
