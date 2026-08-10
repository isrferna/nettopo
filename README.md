# nettopo

A Python CLI that reads **saved Cisco `show` command outputs** (files only — no live
device connections in v1) and generates **network diagrams** in **draw.io format with
Cisco icons**, plus the intermediate data as **CSV tables**.

Four diagram views are produced from the same parsed data model:

- **L2** — physical/link-layer topology from CDP/LLDP, with interface labels and MLAG.
- **STP** — per-VLAN Rapid-PVST spanning-tree state (root, bridge IDs, priorities, port roles/states).
- **HSRP** — first-hop redundancy per SVI (virtual IP, priority, active/standby/listen).
- **BGP** — BGP neighbor (session) graph.

> `nettopo` is a working title — see [`PROJECT_SPEC.md`](PROJECT_SPEC.md) section 1.

## Status

**Phase 4 — STP.** `nettopo stp -i <dir>` now renders real per-VLAN spanning-tree
draw.io diagrams: the root bridge is highlighted, links are colored by forwarding vs
blocking port state and labeled with role/state at each end, and `--vlan N` or
`--group-mode per-vlan|strict|topology` (with `--all` to write every resulting diagram)
select which VLANs are rendered. `stp.csv` now includes both base and effective bridge
priority. `nettopo l2 -i <dir>` (Phase 3) renders devices styled with Cisco icons
(`render/icons.py`) by inferred `DeviceRole`, with per-end interface labels,
`--endpoints all|network-only` filtering and `--link-mode physical|port-channel`
(MLAG links drawn once per bundle). Output is post-processed by `lucidify` by
default (`--no-lucidify` to skip it) so link labels survive Lucidchart import.
`hsrp`, `bgp`, and `all` still report "not implemented". See the delivery plan in
[`PROJECT_SPEC.md`](PROJECT_SPEC.md#14-delivery-plan-sequential-github-issues) and the
open issues for the phased build-out.

> **Pending manual step:** Cisco `mxgraph.cisco.*` draw.io stencils are a confirmed
> requirement but may degrade on Lucidchart import (Lucid uses a different shape
> library). This still needs a real Lucid import to validate — Phase 4 proceeded on the
> same rendering approach without it, since that validation requires interactive Lucid
> access this project's automation doesn't have — see the checklist in
> [`docs/architecture.md`](docs/architecture.md#known-limitation-to-validate-early-cisco-icons-under-lucid-import).

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

## Usage

```
nettopo [--version] [--log-level LEVEL] <command> [options]
```

Every command reads a **directory** of saved capture files (see
[Preparing captures](#preparing-captures) below) and writes into an output directory,
creating it if needed. `parse`, `l2`, and `stp` are implemented; `hsrp`, `bgp`, and `all`
are scaffolded but not yet implemented (running them prints `'<command>' is not
implemented yet.` and exits with status 1 — see [Status](#status)).

### Global options

| Option | Values | Default | Meaning |
|---|---|---|---|
| `--version` | flag | — | Print the installed version and exit, without a subcommand: `nettopo --version`. Read from the installed distribution's metadata, so after bumping `pyproject.toml` re-run `pip install -e .` for it to catch up. |
| `--log-level` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | `INFO` | Logging verbosity. Goes before the subcommand: `nettopo --log-level DEBUG l2 -i ./captures`. |

### Options common to every command

| Option | Values | Default | Meaning |
|---|---|---|---|
| `-i`, `--input` | directory path | *(required)* | Directory of saved device captures to read. See [Preparing captures](#preparing-captures). |
| `-o`, `--output` | directory path | `./output` | Directory to write generated output into (created if it doesn't exist). |
| `--platform` | an [ntc-templates](https://github.com/networktocode/ntc-templates) platform name | `cisco_ios` | Fallback platform used to pick the right parsing template when a device's own platform can't be detected from its `show version` output. IOS and IOS-XE both use `cisco_ios`. |
| `--no-lucidify` | flag | off | Skip the Lucidchart-import-friendliness post-process (`render/lucidify.py`) on generated `.drawio` files. Only affects commands that render diagrams (`l2`, `stp`; later `hsrp`, `bgp`, `all`) — `parse` ignores it. |

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
[PROJECT_SPEC.md §6](PROJECT_SPEC.md#6-data-model)), and header-only `hsrp.csv`/`bgp.csv`
until Phases 5–6 add those parsers.

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
included with a **dashed border** and labeled with their name alone, since there is no
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

### `nettopo hsrp`, `nettopo bgp`, `nettopo all` — not yet implemented

These subcommands parse their arguments (`hsrp` already accepts the same
`--vlan`/`--group-mode`/`--all` options as `stp`) but every run currently exits with
status 1 and logs `'<command>' is not implemented yet.`. They land in Phases 5–7 — see
[`PROJECT_SPEC.md` §14](PROJECT_SPEC.md#14-delivery-plan-sequential-github-issues).

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
| `hsrp` | `show standby brief` — *not yet implemented (Phase 5)* | |
| `bgp` | `show ip bgp summary` — *not yet implemented (Phase 6)* | |

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
| `show ip interface brief` | `interfaces.csv`: admin/operational state and IP per interface |
| `show interfaces` | `interfaces.csv`: descriptions, precise IP/prefix, link state. Richer than `show ip interface brief` and wins where the two overlap |
| `show vlan brief` | `vlans.csv` |
| `show spanning-tree` | `stp.csv` and the STP diagrams: bridge IDs, base and effective priority, per-port role/state |
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
sw1-access#show etherchannel summary
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
