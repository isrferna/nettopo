"""Render-ready diagram shape returned by every view (PROJECT_SPEC.md section 7).

Views read the model and return a `Diagram`; they never parse text or write files.
`render/` consumes it without needing to know anything about the model beyond
`DeviceRole`, which keeps the layering rule (`render` -> `views` + `model`) intact.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nettopo.model.entities import DeviceRole


@dataclass
class DiagramNode:
    id: str
    label: str
    role: DeviceRole = DeviceRole.UNKNOWN
    highlight: bool = False  # e.g. the STP root bridge


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
