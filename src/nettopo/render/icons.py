"""DeviceRole -> Cisco draw.io icon mapping (PROJECT_SPEC.md section 8).

Shape paths are draw.io's modern flat Cisco set (`mxgraph.cisco19.*`), verified against
jgraph/drawio's `Sidebar-Cisco19.js` and then rendered through the draw.io CLI rather than
guessed: a wrong stencil path renders as an invisible/blank shape instead of falling back
to a box, so accuracy here matters more than it would for a typo elsewhere.

Every role goes through the `rect;prIcon=<name>` card shape rather than a standalone
stencil. The standalone endpoint stencils this module once used (`workstation2` and
friends) only exist in recent draw.io builds and render as empty boxes everywhere else,
while the old unsuffixed stencils are single-fill silhouettes that are only legible
through `mxShapeCisco19Rect`, which paints the glyph in `strokeColor`. The card form is
the one spelling that renders in every build.

Two properties of this shape family drive the whole module:

- **`strokeColor` is the glyph color**, not a border color -- it paints both the icon
  itself and the card outline, over a light `fillColor`. That is what makes a per-role
  palette possible, and it is also why the root-bridge highlight cannot be a stroke
  override the way it was for the old isometric stencils: recoloring the stroke turns the
  icon into an unreadable monochrome blob.
- **`aspect=fixed`**, so a node's geometry has to match its icon's native ratio or the
  drawing is stretched. Each entry therefore carries its own size, taken from the sidebar
  and scaled by `_ICON_SCALE`.
"""

from __future__ import annotations

from dataclasses import dataclass

from nettopo.model.entities import DeviceRole

# draw.io's sidebar defines these icons at 50px on their long edge, which is too small to
# read next to a full hostname label. Every native size below is multiplied by this.
_ICON_SCALE = 1.6

_STYLE_SUFFIX = (
    "sketch=0;html=1;pointerEvents=1;aspect=fixed;verticalLabelPosition=bottom;"
    "verticalAlign=top;align=center;outlineConnect=0;fillColor=#FAFAFA;"
    "fontSize=12;fontColor=#2B3440;fontStyle=1;"
)


@dataclass(frozen=True)
class _Icon:
    shape: str  # the part after `mxgraph.cisco19.`
    native_width: int
    native_height: int
    color: str  # glyph and card outline


# Hues separate the layers of a campus at a glance -- deep blue for the routed core,
# teal for switching, and desaturated slate for the endpoints that are not network gear.
_ICON_BY_ROLE: dict[DeviceRole, _Icon] = {
    DeviceRole.ROUTER: _Icon("rect;prIcon=router", 50, 50, "#6B4FBB"),
    DeviceRole.L3_SWITCH: _Icon("rect;prIcon=l3_switch", 50, 50, "#005073"),
    DeviceRole.SWITCH: _Icon("rect;prIcon=workgroup_switch", 50, 50, "#0F7B8A"),
    DeviceRole.FIREWALL: _Icon("rect;prIcon=firewall", 64, 50, "#C0392B"),
    DeviceRole.AP: _Icon("rect;prIcon=wireless_access_point", 50, 50, "#C77700"),
    DeviceRole.PHONE: _Icon("rect;prIcon=ip_phone", 50, 50, "#5A6673"),
    DeviceRole.SERVER: _Icon("rect;prIcon=server", 50, 50, "#3F6C51"),
    DeviceRole.HOST: _Icon("rect;prIcon=workstation", 50, 50, "#5A6673"),
}

# DeviceRole.UNKNOWN (and any future role without a mapping) falls back to a plain box
# rather than a Cisco icon -- there is no meaningful "unknown device" Cisco icon.
_DEFAULT_STYLE = "rounded=1;whiteSpace=wrap;html=1;fillColor=#F4F5F7;strokeColor=#98A2B3;"
_DEFAULT_SIZE = (120, 60)

_NEUTRAL_LINK_COLOR = "#98A2B3"

# Interface labels are dense and sit right where links cross, so they are set small and
# gray on an opaque background rather than in the body text color.
LINK_LABEL_STYLE = "labelBackgroundColor=#FFFFFF;fontSize=9;fontColor=#5A6673;"

# Widest node any diagram can contain, which is what `render/drawio.py` needs to keep two
# neighbors from overlapping. Derived rather than restated so the two cannot drift.
MAX_NODE_WIDTH_PX = max(
    _DEFAULT_SIZE[0],
    *(round(icon.native_width * _ICON_SCALE) for icon in _ICON_BY_ROLE.values()),
)

# Marks the STP root bridge (PROJECT_SPEC.md section 7). A gold card behind an otherwise
# untouched icon, because on this shape family `strokeColor` would repaint the glyph.
_HIGHLIGHT_SUFFIX = "fillColor=#FFF3C4;strokeWidth=3;"

# Marks a device we hold no capture for, drawn only from what its neighbors reported.
# Fading the whole node is what stops a reader from taking an inference for a
# measurement; a dashed border -- what the isometric stencils used -- was invisible,
# since these shapes draw their outline too thin for a dash pattern to register.
# `fontStyle=3` is draw.io's bold+italic: it keeps the base style's bold hostname and
# adds the italic that pairs with the fade.
_INFERRED_SUFFIX = "opacity=40;fontColor=#8A94A6;fontStyle=3;"


@dataclass(frozen=True)
class NodeStyle:
    """Everything `render/` needs to place one node: how it looks and how big it is."""

    style: str
    width: int
    height: int


def node_style(role: DeviceRole, *, highlight: bool = False, inferred: bool = False) -> NodeStyle:
    """Return the draw.io style and geometry for a node of `role`.

    `highlight` marks the node, e.g. as the STP root bridge. `inferred` fades it, marking
    a device known only through its neighbors. Suffixes are appended after the base style
    so their duplicate keys win -- draw.io's style parser takes the last occurrence.
    """
    icon = _ICON_BY_ROLE.get(role)
    if icon is None:
        style, (width, height) = _DEFAULT_STYLE, _DEFAULT_SIZE
    else:
        style = f"shape=mxgraph.cisco19.{icon.shape};strokeColor={icon.color};{_STYLE_SUFFIX}"
        width = round(icon.native_width * _ICON_SCALE)
        height = round(icon.native_height * _ICON_SCALE)

    if highlight:
        style += _HIGHLIGHT_SUFFIX
    if inferred:
        style += _INFERRED_SUFFIX
    return NodeStyle(style=style, width=width, height=height)


def link_style(color: str | None) -> str:
    """Return the draw.io style for a link, colored by `color` when there is one.

    Spells out `endArrow=none` even though it repeats N2G's own default: N2G *substitutes*
    its default for the style we pass rather than merging the two, so a colored link would
    otherwise lose it and pick up draw.io's built-in arrowhead. Links are undirected in
    every view -- the STP view orders an edge's ends by device name, so an arrow would
    point somewhere that means nothing.

    An uncolored link is drawn in a soft gray rather than draw.io's default black, so the
    links that *do* carry meaning (the STP view's port states) are the ones that draw the
    eye.
    """
    if color is None:
        return f"endArrow=none;strokeColor={_NEUTRAL_LINK_COLOR};strokeWidth=1.5;"
    return f"endArrow=none;strokeColor={color};strokeWidth=2;"
