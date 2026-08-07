# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-08-07

First usable PyPI release.

### Added

- Phase 3 L2 view: `views/l2.py` builds a render-ready `Diagram`
  (`views/diagram.py`) from the model, honoring `--endpoints all|network-only`
  (network-only keeps a device if `is_source` is true or a neighbor's CDP/LLDP
  reported it with Router/Switch capabilities) and attaching interface labels to
  both ends of every link. Links whose local interface is a port-channel member are
  grouped into one rendered link per port-channel (MLAG), though no shipped parser
  populates `Interface.po_id` yet, so this is currently a no-op against real captures
  — see `docs/architecture.md`.
- `render/drawio.py` (the only module importing N2G), `render/icons.py`
  (`DeviceRole` -> real `mxgraph.cisco.*` draw.io stencil shapes, verified against
  jgraph/drawio's `Sidebar-Cisco.js`), and `render/lucidify.py` (collapses N2G's
  per-end `src_label`/`trgt_label` child cells, which Lucidchart's importer mangles,
  into a single label on the link itself; also cleans the doubled semicolons N2G's
  XML templates leave in style strings). Applied by default; `--no-lucidify` skips it.
- `nettopo l2 -i <dir> [--endpoints all|network-only]` is now a real command, writing
  `output/l2/l2_full.drawio` or `output/l2/l2_network-only.drawio`.
- `ingest/model_builder.py` now infers `Device.role` from CDP/LLDP capabilities
  reported by neighbors (a device's own capture never reports its own capabilities),
  applied before cross-discovery link deduplication so both ends of a
  source-to-source link get a role. This is what gives `render/icons.py` real data to
  key off of.
- `.github/workflows/publish.yml`: on tag `v*`, builds sdist+wheel and publishes to
  PyPI via trusted publishing (OIDC) — no long-lived token in secrets. PyPI name
  availability for `nettopo` verified (see `PROJECT_SPEC.md` section 1).
- Security: `tests/test_no_network.py` extended to cover `nettopo l2` now that it
  pulls in N2G/igraph.
- Phase 2 L2 parsing + CSV: `ingest/base.py` (`DataSource` interface) and
  `ingest/files.py` (`FileDataSource`, reads `utf-8-sig`, identifies source devices via
  their prompt line); parsers for `show version`, `show cdp neighbors detail`,
  `show lldp neighbors detail`, `show ip interface brief`/`show interfaces`, and
  `show vlan brief` via ntc-templates; `ingest/model_builder.py` wiring ingestion and
  parsing into a populated `NetworkModel`, including CDP/LLDP FQDN-vs-short-hostname
  neighbor correlation and cross-discovery link de-duplication; `export/csv_export.py`
  writing `devices.csv`, `interfaces.csv`, `neighbors.csv`, `vlans.csv` (plus
  header-only `stp.csv`/`hsrp.csv`/`bgp.csv` pending Phases 4-6). `nettopo parse -i
  <dir>` is now a real command. Security: `utils/paths.py` (filename sanitization and
  output-root resolution against path traversal) and CSV formula-injection escaping;
  `tests/test_no_network.py` proves the full `parse` run opens no sockets.
- Phase 1 foundations: the interface-name normalizer (`utils/interfaces.py`,
  PROJECT_SPEC.md section 5), the normalized data model dataclasses and enums
  (`model/entities.py`, section 6), and the STP/HSRP grouping fingerprint functions
  for `per-vlan`/`strict`/`topology` group modes (`model/grouping.py`, section 6).
  Nothing user-visible yet — the CLI still reports "not implemented yet".
- Phase 0 scaffolding: repository layout under `src/nettopo/` matching
  `PROJECT_SPEC.md` section 3, an empty CLI skeleton (`nettopo --help` and all
  subcommands parse but report "not implemented yet"), `pyproject.toml`, and a
  GitHub Actions pipeline running `ruff check`, `ruff format --check`, `mypy`,
  and `pytest --cov` on every push and pull request.
- `CLAUDE.md` engineering conventions, `docs/architecture.md`, and this changelog.

### Known limitations (tracked for Phase 4)

- Cisco icon fidelity under a real Lucidchart import has not yet been manually
  validated — checklist in `docs/architecture.md`.
- MLAG/port-channel grouping in the L2 view has no data source yet (see the Phase 3
  L2 view entry above) and is a no-op against real captures.

## [0.0.1] - 2026-08-06

- Initial repository scaffolding. No packaged release yet.
