"""Device role inferred from a platform string (PROJECT_SPEC.md section 6).

CDP/LLDP capabilities alone cannot tell a router from a multilayer switch: a Catalyst
9500 advertises `Router Switch`, exactly like an ISR does when it bridges. The platform
string a device reports -- through its own `show version`, a neighbor's CDP, or an LLDP
System Description standing in for a platform -- names the chassis, and the chassis is
what settles it.

The mapping is a heuristic over product families, so two judgement calls are worth stating
outright:

- `C9300` is classified `SWITCH` and `C9500` `L3_SWITCH`, even though both route. The
  distinction a topology drawing needs is access versus core/distribution, which is how
  the two families are positioned and deployed.
- Order matters, because the patterns overlap. `WS-C3850-24P` has to be tested against
  the Catalyst 3850 pattern before any looser Catalyst rule can claim it.

Matching is case-insensitive and unanchored: NX-OS reports `N9K-C93180YC-EX` with no
vendor prefix where IOS reports `cisco C9500-16X`, so anchoring to the start of the string
would miss every Nexus.
"""

from __future__ import annotations

import re

from nettopo.model.entities import DeviceRole

_ROLE_BY_PLATFORM: tuple[tuple[re.Pattern[str], DeviceRole], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), role)
    for pattern, role in (
        # Security appliances first: an ASA reports capabilities that would otherwise
        # read as a router.
        (r"\bASA\d|\bASA\b|\bFPR\d|firepower", DeviceRole.FIREWALL),
        # Wireless controllers and access points, before the Catalyst rules -- a C9800
        # controller would otherwise match the generic Catalyst 9000 pattern.
        (r"\bAIR-|\bC98\d\d|\bAP\d{3,}", DeviceRole.AP),
        (r"\bISR|\bASR|\bCSR\d|\bIOSv\b|\bC89\d\d|\bC81\d\d", DeviceRole.ROUTER),
        # Multilayer switches: Nexus, Catalyst 9500/9400, 6500 and 3850.
        (
            r"\bN\dK-|\bNexus\b|\bC9[45]\d\d|\bWS-C65\d\d|\bC65\d\d|\bWS-C38\d\d|\bC38\d\d",
            DeviceRole.L3_SWITCH,
        ),
        # Access switches: Catalyst 9300/9200 and the 2900 family.
        (r"\bWS-C9[23]\d\d|\bC9[23]\d\d|\bWS-C29\d\d|\bC29\d\d", DeviceRole.SWITCH),
        # Arista: CCS-720/722 are campus access switches and must be tested before the
        # generic rule; every DCS-7xxx is a data-center L3 switch, and "Arista"/"EOS"
        # catches an LLDP System Description that names no model at all.
        (r"\bCCS-7\d\d", DeviceRole.SWITCH),
        (r"\bDCS-7\d{3}|\bArista\b|\bEOS\b", DeviceRole.L3_SWITCH),
        (r"\bCP-|IP\s*Phone", DeviceRole.PHONE),
        (r"\bVMware\b|\bESXi?\b|\bUCS\b", DeviceRole.SERVER),
    )
)


def classify_platform(platform: str | None) -> DeviceRole | None:
    """Return the role `platform` implies, or None when it names nothing recognizable.

    None means "no opinion", not `DeviceRole.UNKNOWN`: the caller keeps whatever it
    already inferred from CDP/LLDP capabilities rather than having it overwritten.
    """
    if not platform:
        return None
    for pattern, role in _ROLE_BY_PLATFORM:
        if pattern.search(platform):
            return role
    return None
