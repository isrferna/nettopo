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
nettopo [--log-level LEVEL] <command> [options]
```

Every command reads a **directory** of saved capture files (see
[Preparing captures](#preparing-captures) below) and writes into an output directory,
creating it if needed. `parse`, `l2`, and `stp` are implemented; `hsrp`, `bgp`, and `all`
are scaffolded but not yet implemented (running them prints `'<command>' is not
implemented yet.` and exits with status 1 — see [Status](#status)).

### Global option

| Option | Values | Default | Meaning |
|---|---|---|---|
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
`show version` or from the name a Nexus neighbor advertises), `interfaces.csv`,
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
labels.

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
into per-command sections. Which commands each view needs is listed in
[PROJECT_SPEC.md §4](PROJECT_SPEC.md#4-ingestion-v1-files-only); `tests/fixtures/captures/`
has worked examples. Files are read as `utf-8-sig`, so a leading UTF-8 BOM is handled
transparently.

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
