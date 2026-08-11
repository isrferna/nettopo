# Examples

Runnable capture sets. Unlike `tests/fixtures/`, which holds the smallest input that
exercises one parser, these are complete networks meant to be run end to end — they are
the source of the diagrams in the [top-level README](../README.md#example-diagrams).

## `campus/`

A six-switch campus, ten devices once the neighbor-only ones are counted:

| Device | Capture | Role in the diagrams |
|---|---|---|
| `core-sw1`, `core-sw2` | yes | C9500 core pair, joined by `Po1` (`Gi1/0/1`, `Gi1/0/2`); root bridge for VLANs 10/20/99 and 30 respectively |
| `dist-sw1`, `dist-sw2` | yes | C9300 distribution, dual-homed to both core switches — the loop that gives each VLAN a blocked port |
| `acc-sw1`, `acc-sw2` | yes | C2960X access, cross-connected to each other, which is the second loop |
| `acc-sw3` | no | Access switch seen only in `dist-sw2`'s CDP output — drawn faded in the STP view |
| `edge-rtr` | no | WAN router on a routed port, so it appears in the L2 view and not in the STP view |
| `esxi-host01`, `esxi-host02` | no | ESXi hosts on Edge/PortFast ports: dropped by `--endpoints network-only` and by the STP view |

Four VLANs (10 users, 20 voice, 30 servers, 99 mgmt) with two distinct spanning trees
between them, which is what makes `--group-mode strict` and `--group-mode topology`
produce different groupings on this set.

```bash
nettopo parse -i examples/campus -o ./output
nettopo l2    -i examples/campus -o ./output
nettopo stp   -i examples/campus -o ./output --all --group-mode topology
```

`campus/diagrams/` holds the output of those commands, committed so the README can show
it: the `.drawio` files nettopo writes, plus PNG exports of the four the README embeds.
`FileDataSource` reads only regular files in the capture directory, so this subdirectory
is invisible to ingestion. Both regeneration steps are documented in the
[top-level README](../README.md#example-diagrams).

Every value in these files is synthetic — hostnames, serials, MACs and IPs alike.
