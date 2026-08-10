"""Render-ready diagram shape returned by every view (PROJECT_SPEC.md section 7).

Views read the model and return a `Diagram`; they never parse text or write files.
`render/` consumes it without needing to know anything about the model beyond
`DeviceRole`, which keeps the layering rule (`render` -> `views` + `model`) intact.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from nettopo.model.entities import DeviceRole

INTERFACE_SEPARATOR = ", "
TOOLTIP_LINE_BREAK = "<br>"  # draw.io renders a link tooltip as (sanitized) HTML


@dataclass
class DiagramNode:
    id: str
    label: str
    role: DeviceRole = DeviceRole.UNKNOWN
    highlight: bool = False  # e.g. the STP root bridge
    inferred: bool = False  # drawn from a neighbor's report, not from the device's own capture


@dataclass
class DiagramLink:
    source: str
    target: str
    src_label: str = ""  # interface label at the source end
    trgt_label: str = ""  # interface label at the target end
    label: str = ""  # label at the link's center
    color: str | None = None  # draw.io hex stroke color override, e.g. STP port state
    tooltip: str = ""  # hover text, e.g. a port-channel's member interfaces


@dataclass
class Diagram:
    nodes: list[DiagramNode] = field(default_factory=list)
    links: list[DiagramLink] = field(default_factory=list)


def join_interfaces(interface_names: Iterable[str]) -> str:
    """Label one end of a drawn link that stands for several physical interfaces."""
    return INTERFACE_SEPARATOR.join(dict.fromkeys(interface_names))


def members_tooltip(member_pairs: Iterable[tuple[str, str]]) -> str:
    """Hover text naming the physical adjacencies a single drawn link stands for.

    Shared by every view that collapses a bundle into one link, so a port-channel reads
    the same whichever diagram the user is looking at.
    """
    return TOOLTIP_LINE_BREAK.join(
        ["Members:", *(f"{local} — {remote}" for local, remote in member_pairs)]
    )
