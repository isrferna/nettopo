# Examples

Runnable capture sets. Unlike `tests/fixtures/`, which holds the smallest input that
exercises one parser, these are networks meant to be run end to end — they are the source
of the diagrams in the [top-level README](../README.md#example-diagrams).

`campus/` is the general-purpose one, exercising every view. `hsrp-quad/` exists for a
single shape the campus set cannot show: an HSRP group with more than two members.

## `campus/`

A six-switch campus, ten devices once the neighbor-only ones are counted:

| Device | Capture | Role in the diagrams |
|---|---|---|
| `core-sw1`, `core-sw2` | yes | C9500 core pair, joined by `Po1` (`Gi1/0/1`, `Gi1/0/2`); root bridge for VLANs 10/20/99 and 30 respectively, and the HSRP gateway pair for VLANs 10/20/30 |
| `dist-sw1`, `dist-sw2` | yes | C9300 distribution, dual-homed to both core switches — the loop that gives each VLAN a blocked port |
| `acc-sw1`, `acc-sw2` | yes | C2960X access, cross-connected to each other, which is the second loop |
| `acc-sw3` | no | Access switch seen only in `dist-sw2`'s CDP output — drawn faded in the STP view |
| `edge-rtr` | no | WAN router on a routed port, so it appears in the L2 view and not in the STP view |
| `esxi-host01`, `esxi-host02` | no | ESXi hosts on Edge/PortFast ports: dropped by `--endpoints network-only` and by the STP view |

Four VLANs (10 users, 20 voice, 30 servers, 99 mgmt) with two distinct spanning trees
between them, which is what makes `--group-mode strict` and `--group-mode topology`
produce different groupings on this set. The core pair runs HSRP on VLANs 10, 20 and 30,
aligned with those trees — each core switch is the active gateway for the VLANs it roots.
The HSRP view never groups, so it writes one diagram per VLAN whatever the priorities are.

```bash
nettopo parse -i examples/campus -o ./output
nettopo l2    -i examples/campus -o ./output
nettopo stp   -i examples/campus -o ./output --all --group-mode topology
nettopo hsrp  -i examples/campus -o ./output --all
```

`campus/diagrams/` holds the output of those commands, committed so the README can show
it: the `.drawio` files nettopo writes, plus PNG exports of the five the README embeds.
`FileDataSource` reads only regular files in the capture directory, so this subdirectory
is invisible to ingestion. Both regeneration steps are documented in the
[top-level README](../README.md#example-diagrams).

## `hsrp-quad/`

Four layer-3 switches sharing one HSRP group on VLAN 50 — a VLAN spanning two buildings,
each with a switch pair:

| Device | SVI address | Priority | State |
|---|---|---|---|
| `bldg-a-sw1` | `10.20.50.2` | 150 | Active |
| `bldg-a-sw2` | `10.20.50.3` | 140 | Standby |
| `bldg-b-sw1` | `10.20.50.4` | 110 | Listen |
| `bldg-b-sw2` | `10.20.50.5` | 100 | Listen |

The campus set has the usual two-router gateway pair, where active and standby account for
everyone. This one exists because a group can have any number of members while `show
standby brief` names only those two by address — so the two listening switches are the
case that proves the diagram's addresses come from `show ip interface brief` and not from
the HSRP output.

Deliberately narrow: these captures carry `show version`, `show ip interface brief` and
`show standby brief` and nothing else, because no other command contributes to an HSRP
diagram. `nettopo l2` and `nettopo stp` on this directory produce empty diagrams, which is
correct — there is no neighbor-discovery or spanning-tree data to draw.

```bash
nettopo hsrp -i examples/hsrp-quad -o examples/hsrp-quad/diagrams --all
```

Every value in these files is synthetic — hostnames, serials, MACs and IPs alike.
