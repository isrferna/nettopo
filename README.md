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

**Phase 2 — L2 parsing + CSV.** `nettopo parse -i <dir>` is real: it reads a directory of
saved captures, parses `show version`/`show cdp neighbors detail`/`show lldp neighbors
detail`/`show ip interface brief`/`show interfaces`/`show vlan brief` via
ntc-templates, populates the normalized data model, and writes `devices.csv`,
`interfaces.csv`, `neighbors.csv`, and `vlans.csv` to `output/csv/` (`stp.csv`,
`hsrp.csv`, `bgp.csv` are header-only until Phases 4-6). No diagram rendering yet — `l2`,
`stp`, `hsrp`, `bgp`, and `all` still report "not implemented". See the delivery plan in
[`PROJECT_SPEC.md`](PROJECT_SPEC.md#14-delivery-plan-sequential-github-issues) and the
open issues for the phased build-out.

## Installation

Not yet published to PyPI. To install from source for development:

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
