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
(`render/icons.py`) by inferred `DeviceRole`, with per-end interface labels and
`--endpoints all|network-only` filtering. Output is post-processed by `lucidify` by
default (`--no-lucidify` to skip it) so link labels survive Lucidchart import.
`hsrp`, `bgp`, and `all` still report "not implemented". See the delivery plan in
[`PROJECT_SPEC.md`](PROJECT_SPEC.md#14-delivery-plan-sequential-github-issues) and the
open issues for the phased build-out.

> **Known gap:** MLAG/port-channel grouping in the L2 view is implemented and tested
> against the data model, but no shipped parser populates `Interface.po_id` yet (no
> phase parses `show etherchannel summary`), so it is currently a no-op against real
> captures. See [`docs/architecture.md`](docs/architecture.md).
>
> **Pending manual step:** Cisco `mxgraph.cisco.*` draw.io stencils are a confirmed
> requirement but may degrade on Lucidchart import (Lucid uses a different shape
> library). This still needs a real Lucid import to validate — Phase 4 proceeded on the
> same rendering approach without it, since that validation requires interactive Lucid
> access this project's automation doesn't have — see the checklist in
> [`docs/architecture.md`](docs/architecture.md#known-limitation-to-validate-early-cisco-icons-under-lucid-import).

## Installation

Not yet published to PyPI (publishing happens on tagging `v0.1.0` after this PR merges,
via `.github/workflows/publish.yml`). To install from source for development:

```bash
git clone https://github.com/isrferna/nettopo.git
cd nettopo
pip install -e ".[dev]"
```

Requires Python 3.11+.

## Usage

```bash
nettopo --help
nettopo parse -i ./captures
nettopo l2    -i ./captures --endpoints network-only
nettopo stp   -i ./captures --group-mode topology --all
nettopo hsrp  -i ./captures --vlan 10
nettopo bgp   -i ./captures
nettopo all   -i ./captures
```

See [`PROJECT_SPEC.md`](PROJECT_SPEC.md#9-cli-design) for the full CLI reference.

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
