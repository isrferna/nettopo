# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0rc1] - 2026-08-10

Release candidate: neighbor identity resolution. Pre-releases are not installed by
`pip` unless asked for — `pip install --pre nettopo` or `pip install nettopo==0.3.0rc1`.

### Fixed

- A device reported under different names by CDP and LLDP is no longer split into
  several nodes. NX-OS advertises its name with the chassis serial appended
  (`nxos-core1(FDO21120U5D)`, by default as its CDP device id) where the other protocol
  reports it plain, and either protocol may use an FQDN where the other uses the short
  name; each spelling used to become its own `Device`, so one switch was drawn several
  times with parallel links. The new
  `utils/hostnames.py` correlates every reported spelling before the model is built, and
  `ingest/model_builder.py` (now a three-phase build, since correlation needs to see all
  spellings at once) rewrites each discovered link onto the canonical name. Two
  same-labeled devices in different domains (`sw1.site-a.com`, `sw1.site-b.com`) are
  deliberately *not* merged.
- `parsing/lldp.py` no longer reports a neighbor's configured interface description as
  its interface name. NX-OS puts free text in LLDP's "Port Description" field, which
  correlated with nothing and left a second, mislabeled edge for every link that CDP had
  already described. The field that actually looks like an interface name now wins, via
  the new `looks_like_interface()` in `utils/interfaces.py`.
- `ingest/model_builder.py` keeps a single link per local port and neighbor, preferring
  the CDP report over the LLDP one, so a link described by both protocols renders once.
- `nettopo.__version__` is read from the installed distribution metadata instead of being
  hardcoded. It had been left at the Phase 0 scaffolding's `0.0.1` through v0.1.0 and
  v0.2.0, disagreeing with `pyproject.toml` and therefore with what was on PyPI.

### Added

- `Device.serial`, populated from a source device's own `show version` or recovered from
  the serial an NX-OS neighbor advertises inside its name, and exported as a new column
  in `devices.csv`.

## [0.2.0] - 2026-08-07

Phase 4: STP.

### Added

- `parsing/spanning_tree.py`: parses `show spanning-tree` (per-VLAN Rapid-PVST) with
  its own regexes rather than ntc-templates -- the shipped template only captures the
  port role/state/cost table, not the "Root ID"/"Bridge ID" blocks the data model
  needs (bridge priority, MAC, root-election flag). One parser serves both IOS and
  IOS-XE, which emit this command identically; `tests/fixtures/spanning_tree/` carries
  a fixture for each. `ingest/model_builder.py` wires per-device captures into
  `model.stp`, keyed by VLAN.
- Phase 4 STP view: `views/stp.py` builds one render-ready `Diagram` per VLAN, or per
  topology group under `--group-mode strict|topology` (grouped VLANs are guaranteed by
  `model/grouping.py`'s fingerprints to render identically, so the view renders one
  representative VLAN per group and names the output file with every VLAN id it
  covers, e.g. `stp_vlans-10_20_30.drawio`). The root bridge is highlighted; links are
  colored by forwarding/blocking port state and labeled with role/state at each end,
  cross-referencing `model.links` for physical adjacency since `StpPort` alone doesn't
  record which device is on the other end of a port.
- `views/diagram.py`: `DiagramNode.highlight` and `DiagramLink.color` let a view drive
  root-bridge and port-state styling without `render/` knowing about STP concepts.
  `render/icons.py` and `render/drawio.py` apply them as draw.io style overrides.
- `nettopo stp -i <dir> [--vlan N | --group-mode per-vlan|strict|topology] [--all]` is
  now a real command, requiring either `--vlan` or `--all` (there is no single sensible
  default among a potentially many-VLAN model), writing to `output/stp/`.
- `export/csv_export.py` now writes real `stp.csv` rows (one per device/interface),
  including both base and effective bridge priority.
- Security: `tests/test_no_network.py` extended to cover `nettopo stp`.

### Known limitations (carried forward)

- Cisco icon fidelity under a real Lucidchart import still has not been manually
  validated (see the Phase 3 entry below) -- Phase 4 proceeded on the same rendering
  approach without it, since that validation needs interactive Lucid access this
  project's automation doesn't have. Checklist in `docs/architecture.md`.
- MLAG/port-channel grouping in the L2 view still has no data source (unchanged from
  Phase 3).

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
