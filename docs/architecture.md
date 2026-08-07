# Architecture

This document describes `nettopo`'s components, call flow, and the design decisions
behind them. It is kept in sync with the code — see the documentation-maintenance rule
in [`CLAUDE.md`](../CLAUDE.md). For scope, the full data model, and the CLI reference,
see [`PROJECT_SPEC.md`](../PROJECT_SPEC.md).

## Current state (Phase 0)

Only the repository layout and the CLI skeleton exist. `nettopo <command> -i <dir>`
parses its arguments successfully and reports "not implemented yet" — no ingestion,
parsing, modeling, view, or rendering logic has been written. The sections below
describe the target architecture that later phases build out incrementally.

## Components

```
ingest/   data sources (file reader now; a live SSH source can be added later)
parsing/  one TextFSM/ntc-templates parser per `show` command
model/    normalized dataclasses (entities.py) + VLAN grouping fingerprints (grouping.py)
views/    one module per diagram (l2, stp, hsrp, bgp); reads the model, never parses
          text or writes files
render/   draw.io emission via N2G, Cisco icon mapping, and the Lucidchart post-process
export/   CSV writers, one table per model entity
utils/    dependency-free shared services (currently: the interface-name normalizer)
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

## Known limitation to validate early: Cisco icons under Lucid import

`render/icons.py` maps device roles to `mxgraph.cisco.*` draw.io stencils. Lucidchart
uses a different shape library, so these stencils may degrade to plain boxes on import.
Cisco icons are a confirmed requirement, so v1 keeps them and accepts this tradeoff;
`render/lucidify.py` post-processes link labels so at least those survive import. Real
fidelity must be validated with a live Lucid import during Phase 3, before the remaining
views (STP, HSRP, BGP) are built on the same rendering approach.

## Security posture

`nettopo` makes zero network connections by design — it only reads local capture files
and writes local output files. `tests/test_no_network.py` (added when the `all` command
is implemented) enforces this by monkeypatching `socket.socket` to fail and asserting a
full run still succeeds. See `PROJECT_SPEC.md` section 11 for the full OWASP-adapted
security review.
