"""The central interface-name normalizer.

Single source of truth for interface-name normalization (PROJECT_SPEC.md section 5).
Every parser must route interface names through `normalize()` so that the same
physical port correlates across commands regardless of which form a given `show`
command happens to print (e.g. `Gi1/0/1` vs `GigabitEthernet1/0/1`).
"""

from __future__ import annotations

_LONG_FORM_TO_CANONICAL: dict[str, str] = {
    "gigabitethernet": "Gi",
    "tengigabitethernet": "Te",
    "twentyfivegige": "Twe",
    "fortygigabitethernet": "Fo",
    "hundredgige": "Hu",
    "fastethernet": "Fa",
    "ethernet": "Eth",
    "port-channel": "Po",
    "vlan": "Vl",
    "loopback": "Lo",
    "tunnel": "Tu",
    "management": "Mgmt",
}

_CANONICAL_FORMS: tuple[str, ...] = tuple(_LONG_FORM_TO_CANONICAL.values())

# Longest-prefix-first, and long forms checked entirely before canonical forms, so a
# short alias (e.g. canonical "Te") can never shadow a longer, more specific form (e.g.
# long-form "TenGigabitEthernet") that happens to share a leading substring.
_LONG_FORMS_BY_LENGTH: tuple[str, ...] = tuple(
    sorted(_LONG_FORM_TO_CANONICAL, key=len, reverse=True)
)
_CANONICAL_BY_LENGTH: tuple[str, ...] = tuple(sorted(_CANONICAL_FORMS, key=len, reverse=True))

# Every spelling an interface type can start with, lowercased, for `looks_like_interface`.
_INTERFACE_PREFIXES: tuple[str, ...] = (
    *_LONG_FORMS_BY_LENGTH,
    *(canonical.lower() for canonical in _CANONICAL_BY_LENGTH),
)


def looks_like_interface(name: str) -> bool:
    """Whether `name` is a recognized interface type immediately followed by a number.

    Lets a parser tell an interface name from free text when a device offers both in the
    same field -- LLDP's "Port Description" carries the neighbor's configured interface
    description on NX-OS, not its port name. `normalize()` cannot answer this: it returns
    unrecognized input unchanged, which is indistinguishable from an already-canonical
    name. The trailing-digit requirement is what separates `Po1` from prose that merely
    starts the same way (`Port 1`, `long-haul uplink`).
    """
    lowered = name.lower()
    for prefix in _INTERFACE_PREFIXES:
        if lowered.startswith(prefix) and lowered[len(prefix) : len(prefix) + 1].isdigit():
            return True
    return False


def normalize(name: str) -> str:
    """Normalize an interface name to its short canonical form.

    Pure, deterministic, and idempotent: ``normalize(normalize(x)) == normalize(x)``.
    Matching on the interface-type prefix is case-insensitive; the numeric/slot suffix
    is preserved verbatim from the input. Names with an unrecognized type prefix are
    returned unchanged.
    """
    lowered = name.lower()

    for long_form in _LONG_FORMS_BY_LENGTH:
        if lowered.startswith(long_form):
            canonical = _LONG_FORM_TO_CANONICAL[long_form]
            return canonical + name[len(long_form) :]

    for canonical in _CANONICAL_BY_LENGTH:
        if lowered.startswith(canonical.lower()):
            return canonical + name[len(canonical) :]

    return name
