"""The central device-name normalizer.

Single source of truth for correlating the several spellings under which the *same*
device is reported (PROJECT_SPEC.md section 5). NX-OS appends the chassis serial to the
name it advertises -- by default as its CDP device id, though the suffix turns up on
either protocol -- so one switch appears as `nxos-core1(FDO21120U5D)` here,
`nxos-core1` there, and `nxos-core1.example.com` in a third neighbor's output. Left
uncorrelated, each spelling becomes its own `Device` and the diagram draws one physical
switch as several nodes with parallel links.

The resolver never invents a name: a canonical name is always one of the observed
spellings (minus the serial suffix), so a device only ever seen by its FQDN keeps that
FQDN. It also refuses to merge two different domains under the same short label
(`sw1.site-a.com` vs `sw1.site-b.com`) unless a bare spelling or a single source device
proves they are the same box -- silently merging two sites' switches is a worse failure
than leaving a duplicate node.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable

# The advertised name proper, then a single trailing parenthesized token. Anchored at
# both ends so a name that merely contains parentheses is left alone.
_SERIAL_SUFFIX = re.compile(r"^(?P<name>.*\S)\s*\((?P<serial>[^()]+)\)$")


def split_serial_suffix(name: str) -> tuple[str, str | None]:
    """Split `name` into its bare form and the serial NX-OS appends to it, if any.

    `"nxos-core1(FDO21120U5D)"` -> `("nxos-core1", "FDO21120U5D")`;
    `"nxos-core1"` -> `("nxos-core1", None)`.
    """
    stripped = name.strip()
    match = _SERIAL_SUFFIX.match(stripped)
    if match is None:
        return stripped, None
    return match.group("name"), match.group("serial")


def identity_key(name: str) -> tuple[str, str]:
    """Return `(short_label, domain)` for `name`, case-folded and serial-stripped.

    `domain` is `""` for a name that carries none. Two spellings correlate only if their
    short labels match; the domain then decides whether they may be merged.
    """
    bare, _serial = split_serial_suffix(name)
    label, _dot, domain = bare.partition(".")
    return label.casefold(), domain.casefold()


def resolve_device_identities(
    names: Iterable[str], source_hostnames: Iterable[str]
) -> dict[str, str]:
    """Map every spelling in `names` to the canonical name its device is known by.

    A hostname in `source_hostnames` (a device we hold a capture for, so its own
    `show version` settled its identity) always wins, since the rest of the model is
    already keyed by it. Otherwise the shortest observed spelling represents the group.
    """
    sources_by_label: dict[str, set[str]] = defaultdict(set)
    for hostname in source_hostnames:
        sources_by_label[identity_key(hostname)[0]].add(hostname)

    spellings_by_label: dict[str, set[str]] = defaultdict(set)
    for name in names:
        spellings_by_label[identity_key(name)[0]].add(name)

    resolved: dict[str, str] = {}
    for label, spellings in spellings_by_label.items():
        sources = sources_by_label.get(label, set())
        if len(sources) == 1:
            canonical = next(iter(sources))
            resolved.update(dict.fromkeys(spellings, canonical))
            continue

        # Several source devices share this short label, so no single one of them can
        # claim the spelling: fall back to site-by-site grouping like any other name.
        for group in _split_by_site(spellings, ambiguous_sources=bool(sources)):
            resolved.update(dict.fromkeys(group, _display_name(group)))
    return resolved


def _split_by_site(spellings: set[str], *, ambiguous_sources: bool) -> list[set[str]]:
    """Split `spellings` (all sharing one short label) into one group per real device."""
    domains = {identity_key(spelling)[1] for spelling in spellings}
    if not ambiguous_sources and (len(domains) == 1 or "" in domains):
        return [spellings]
    return [
        {spelling for spelling in spellings if identity_key(spelling)[1] == domain}
        for domain in sorted(domains)
    ]


def _display_name(group: set[str]) -> str:
    """The shortest bare spelling in `group`, alphabetical among equals for determinism."""
    return min(
        (split_serial_suffix(spelling)[0] for spelling in group),
        key=lambda name: (len(name), name),
    )
