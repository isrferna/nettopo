# Architecture

This document describes `nettopo`'s components, call flow, and the design decisions
behind them. It is kept in sync with the code — see the documentation-maintenance rule
in [`CLAUDE.md`](../CLAUDE.md). For scope, the full data model, and the CLI reference,
see [`PROJECT_SPEC.md`](../PROJECT_SPEC.md).

## Current state (Phase 4)

`nettopo parse -i <dir>` is real end-to-end: `ingest/files.py` reads a directory of
saved captures, the `parsing/` modules extract structured data (ntc-templates for most
commands; `parsing/spanning_tree.py` uses its own regexes -- see below),
`ingest/model_builder.py` wires that into a populated `NetworkModel`, and
`export/csv_export.py` writes `devices.csv`, `interfaces.csv`, `neighbors.csv`,
`vlans.csv`, and `stp.csv` to `output/csv/` (`hsrp.csv`/`bgp.csv` stay header-only until
Phases 5-6 add those parsers).

`nettopo l2 -i <dir>` is also real end-to-end: `views/l2.py` reads the model and
returns a `views/diagram.py` `Diagram` (nodes + links, endpoint-filtered by
`--endpoints all|network-only`), `render/drawio.py` renders it through N2G with
Cisco icons from `render/icons.py`, and `render/lucidify.py` post-processes the
result by default so per-end interface labels survive Lucidchart import. Output goes
to `output/l2/l2_full.drawio` or `output/l2/l2_network-only.drawio`.

`nettopo stp -i <dir> [--vlan N | --group-mode per-vlan|strict|topology] [--all]` is
also real end-to-end: `views/stp.py` reads `model.stp` and `model.links`, groups VLANs
by `model/grouping.py`'s fingerprint under `--group-mode` (or picks a single VLAN under
`--vlan`), and returns one `Diagram` per resulting group -- root bridge highlighted,
links colored by forwarding/blocking port state. `cli.py` requires either `--vlan` or
`--all` (there is no sensible single default among a per-vlan model with potentially
many VLANs), and writes each group to `output/stp/stp_vlan<N>.drawio` or
`output/stp/stp_vlans-<N>_<M>...drawio`.

`hsrp`, `bgp`, and `all` still report "not implemented yet". The sections below
describe the target architecture that later phases build out incrementally.

## Why `spanning_tree.py` doesn't use ntc-templates

Every other parser in this project routes through `parsing/_textfsm.py` and an
ntc-templates TextFSM template. `show spanning-tree`'s shipped template
(`cisco_ios_show_spanning-tree`) only captures the per-interface role/state/cost table --
it has no fields for the "Root ID"/"Bridge ID" blocks that carry the data
`StpBridge` needs (priority, MAC, root-election flag). Rather than mixing a TextFSM
pass for the port table with hand-written regex for the bridge blocks,
`parsing/spanning_tree.py` parses the whole command output itself: both blocks are
simple, line-anchored, stable text, so one self-contained regex-based parser is
simpler than two parsing strategies for one command. IOS and IOS-XE emit this command
identically (unlike `show version`), so the same parser serves both --
`tests/fixtures/spanning_tree/` carries one fixture per OS to prove it.

## Why the STP view cross-references `model.links`

A `StpPort` records a device's own port role/state for a VLAN, but not which device is
on the other end of that port -- spanning-tree data alone cannot say "this link goes to
sw2". `views/stp.py` gets that from `model.links` (built from CDP/LLDP, the only place
that records device-to-device physical adjacency) and looks up each link's two ends in
the VLAN's `StpPort` map to label and color it. A link where neither end has STP data
for that VLAN (e.g. a link outside the VLAN's spanning tree) is excluded.

## Why grouped STP diagrams render one representative VLAN

`model/grouping.py`'s fingerprints guarantee that VLANs grouped under `strict` or
`topology` produce an identical rendered diagram (that is what "grouped" means -- see
the section below on why grouping is separate from views). `views/stp.py` exploits that
guarantee: instead of re-deriving a merged diagram, it renders the lowest-numbered VLAN
in each group and labels the output file with every VLAN id the group covers
(`stp_vlans-10_20_30.drawio`).

## Why `Device.role` is inferred from neighbor capabilities, not self-reported

`render/icons.py` maps `DeviceRole` to a Cisco icon, but a device's own CDP/LLDP output
never reports its own capabilities (see PROJECT_SPEC.md section 7's endpoint-filtering
note) -- so `ingest/model_builder.py` infers `Device.role` from how *other* devices'
CDP/LLDP describe it (`Capabilities: Router` / `Switch` / `Phone` / `Host`), applied
the moment each raw link is discovered, before the two directions of a source-to-source
link are deduplicated into one `Link`. Deduplication keeps only one direction's
`remote_capabilities`; inferring role only from the deduplicated list would silently
leave whichever device ended up on the discarded side at `DeviceRole.UNKNOWN`. A device
never described by any neighbor's capabilities (e.g. an isolated source device) stays
`UNKNOWN` and renders as a plain box rather than a guessed icon.

## Components

```
ingest/   data sources (file reader now; a live SSH source can be added later)
parsing/  one TextFSM/ntc-templates parser per `show` command
model/    normalized dataclasses (entities.py) + VLAN grouping fingerprints (grouping.py)
views/    one module per diagram (l2, stp, hsrp, bgp); reads the model, never parses
          text or writes files
render/   draw.io emission via N2G, Cisco icon mapping, and the Lucidchart post-process
export/   CSV writers, one table per model entity
utils/    dependency-free shared services: the interface-name normalizer, the
          multi-command capture splitter, and path/filename safety helpers
cli.py    argument parsing and orchestration only — no business logic
```

## Layering rule (Dependency Inversion)

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
so a rendering-library change (see the N2G note below) or a new export format cannot
ripple back into parsing or modeling code.

## Why an ingestion interface

`ingest/base.py` defines a `DataSource` interface; `ingest/files.py` implements it by
reading a directory of saved captures. v1 ships file-based ingestion only (see
`PROJECT_SPEC.md` section 2, "out of scope"), but the interface exists now so that a
future live-collection source (netmiko/scrapli over SSH) can be added by implementing
the same interface, without touching `parsing/`, `model/`, or `views/`.

## Why CDP/LLDP neighbor names are resolved against known hostnames

CDP/LLDP frequently report a neighbor by its fully-qualified domain name (e.g.
`sw2-dist.example.com`) even when that same device's own capture identifies it by its
short hostname (`sw2-dist`, from `show version`). Left unresolved, every link between
two source devices would create a duplicate, non-source `Device` for the FQDN spelling,
splitting one device into two in the model. `ingest/model_builder.py` builds the model in
two passes: first every source device's canonical hostname is established from `show
version`, then neighbor names are resolved against that set (exact match, then
short-name-vs-FQDN) before links are created. A neighbor that matches no known source
hostname (e.g. `core-rtr`, seen only in CDP output) is kept as a non-source `Device`
under its reported name.

## Why interface-name normalization is centralized

The same physical port can appear as `Gi1/0/1` in one `show` command's output and
`GigabitEthernet1/0/1` in another. If parsers normalized independently, or not at all,
correlation across commands (and across devices) would silently fail. `utils/interfaces.py`
is the single source of truth for this normalization; every parser routes interface
names through it. See `PROJECT_SPEC.md` section 5 for the canonical abbreviation table.

## Why N2G is isolated to one module

`render/drawio.py` is the only module that imports N2G. If N2G is ever replaced, only
that module changes — `views/` and `model/` are unaffected because they depend on
neither N2G nor draw.io concepts.

## Why grouping is a separate concern from views

STP and HSRP views can be generated per-VLAN, or with VLANs grouped by resulting
topology fingerprint (`strict` groups on exact configured priority + topology; `topology`
groups on topology alone, ignoring priority). The fingerprint functions live in
`model/grouping.py`, not in the view modules, because the notion of "these VLANs produce
the same diagram" is a property of the model, independent of how that diagram is later
rendered.

## Why MLAG grouping is data-ready but currently a no-op

`views/l2.py` groups physical links into one rendered link per port-channel when the
*local* interface's `Interface.po_id` is set (remote interfaces are never grouped this
way, because a non-source remote device's interfaces are never populated -- we have no
capture for it). This is tested directly against hand-built `NetworkModel` objects in
`tests/test_views_l2.py`. However, no parser in the current command set
(PROJECT_SPEC.md section 4) populates `po_id`: it requires `show etherchannel summary`
or equivalent, which is not one of the commands any phase parses. Against real captures
today, every link's `po_id` is `None`, so grouping never triggers and every link renders
individually. This is intentional forward-compatibility, not a bug: the grouping
mechanism the spec requires ("MLAG shown via port-channel grouping") exists and is
correct, it is simply waiting on a data source that is out of Phase 3's scope to add.

## Known limitation to validate early: Cisco icons under Lucid import

`render/icons.py` maps device roles to `mxgraph.cisco.*` draw.io stencils, verified
against the actual shape names in jgraph/drawio's `Sidebar-Cisco.js` rather than
guessed. Lucidchart uses a different shape library, so these stencils may still degrade
to plain boxes on import even with the correct names. Cisco icons are a confirmed
requirement, so v1 keeps them and accepts this tradeoff; `render/lucidify.py`
post-processes link labels (collapsing N2G's per-end `src_label`/`trgt_label` child
cells, which Lucid mangles, into a single label on the link itself) so at least those
survive import.

**Status: implementation complete, live-import validation still pending.** Real
fidelity against an actual Lucidchart import has not yet been checked by a human with
Lucid access. Phase 4 (STP) proceeded on the same rendering approach without waiting
for this, since it requires interactive access this project's automation does not
have; whoever runs the checklist below should treat Phase 3's L2 output and Phase 4's
STP output (root-highlight and port-state link colors are new draw.io style overrides,
`render/icons.py`/`render/drawio.py`) as equally unvalidated. Checklist for whoever
runs this:

1. Generate a sample: `nettopo l2 -i tests/fixtures/captures -o /tmp/lucid-check`.
2. Import `/tmp/lucid-check/l2/l2_full.drawio` into a Lucidchart document.
3. Record, here in this section: whether the Cisco device shapes render recognizably or
   degrade to plain boxes, and whether the collapsed link labels (device names on the
   link, e.g. `Gi1/0/1 — Gi1/0/24`) survived the import.

## Security posture

`nettopo` makes zero network connections by design — it only reads local capture files
and writes local output files. `tests/test_no_network.py` enforces this by
monkeypatching `socket.socket` to fail and asserting a full `parse` run still succeeds;
Phase 3 extends the same test to cover `nettopo l2` now that it pulls in N2G/igraph,
Phase 4 extends it again to cover `nettopo stp`, and it will extend further to cover
`nettopo all` once Phase 7 adds that command.
`utils/paths.py`
sanitizes any filename derived from parsed data (hostnames, later VLAN ids) and resolves
the output root before anything is written, so a value like `../../etc` can't make a
derived filename escape the output directory. `export/csv_export.py` also neutralizes
cell values that start with a formula-triggering character (`=`, `+`, `-`, `@`) so a
hostname or description can't execute as a formula when the CSV is opened in spreadsheet
software. See `PROJECT_SPEC.md` section 11 for the full OWASP-adapted security review.
