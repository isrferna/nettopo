"""CLI entry point: argument parsing and orchestration only.

Business logic for each subcommand (ingest -> parse -> model -> view ->
render/export) is added in later phases per PROJECT_SPEC.md section 14.
This module must stay free of that logic — it only builds the argument
parser and dispatches to handlers.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from nettopo import __version__
from nettopo.export.csv_export import write_csv_tables
from nettopo.ingest.files import FileDataSource
from nettopo.ingest.model_builder import build_network_model
from nettopo.model.entities import NetworkModel
from nettopo.model.grouping import GroupMode
from nettopo.render.drawio import render_diagram
from nettopo.utils.paths import resolve_output_root
from nettopo.views import bgp as bgp_view
from nettopo.views import hsrp as hsrp_view
from nettopo.views import l2 as l2_view
from nettopo.views import stp as stp_view
from nettopo.views.diagram import VlanDiagramGroup
from nettopo.views.l2 import LinkMode

_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

_L2_OUTPUT_STEMS = {"all": "l2_full", "network-only": "l2_network-only"}
_L2_PORT_CHANNEL_SUFFIX = "_port-channels"

# BGP renders one diagram for the whole network and takes no view-specific options, so
# unlike the L2 and per-VLAN views its filename is fixed (PROJECT_SPEC.md section 8).
_BGP_OUTPUT_FILENAME = "bgp.drawio"

logger = logging.getLogger("nettopo")


def _add_common_arguments(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument(
        "-i", "--input", required=True, help="Directory containing device captures."
    )
    subparser.add_argument(
        "-o",
        "--output",
        default="./output",
        help="Directory to write generated output (default: %(default)s).",
    )
    subparser.add_argument(
        "--platform",
        default="cisco_ios",
        help=(
            "Default ntc-templates platform used when a device's own platform "
            "cannot be detected from its capture (default: %(default)s)."
        ),
    )
    subparser.add_argument(
        "--no-lucidify",
        action="store_true",
        help="Skip the link-label post-process on generated draw.io files.",
    )


def _add_vlan_selection_arguments(
    subparser: argparse.ArgumentParser, *, with_group_mode: bool
) -> None:
    """Add the VLAN selection options a per-VLAN view takes.

    `--group-mode` belongs to `stp` alone, so it is opt-in: the HSRP view draws one
    diagram per VLAN and has nothing to group (see `views/hsrp.py`). Where it does apply
    it joins `--vlan` in the mutually exclusive group -- naming one VLAN and asking how to
    group VLANs are contradictory requests.
    """
    selection = subparser.add_mutually_exclusive_group()
    selection.add_argument("--vlan", type=int, help="Restrict output to a single VLAN.")
    if with_group_mode:
        selection.add_argument(
            "--group-mode",
            choices=("per-vlan", "strict", "topology"),
            default="per-vlan",
            help="How to group VLAN diagrams (default: %(default)s).",
        )
    subparser.add_argument(
        "--all",
        action="store_true",
        help="Write every resulting diagram into output/<view>/.",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the nettopo argument parser.

    Only argument definitions live here; no business logic is invoked.
    """
    parser = argparse.ArgumentParser(
        prog="nettopo",
        description=(
            "Generate draw.io network diagrams and CSV tables from saved "
            "Cisco show-command captures."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show the installed nettopo version and exit.",
    )
    parser.add_argument(
        "--log-level",
        choices=_LOG_LEVELS,
        default="INFO",
        help="Logging verbosity (default: %(default)s).",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_parser = subparsers.add_parser("parse", help="Parse captures and write all CSV tables.")
    _add_common_arguments(parse_parser)

    l2_parser = subparsers.add_parser("l2", help="Generate the L2 topology diagram.")
    _add_common_arguments(l2_parser)
    l2_parser.add_argument(
        "--endpoints",
        choices=("all", "network-only"),
        default="all",
        help="Which neighbor endpoints to include (default: %(default)s).",
    )
    l2_parser.add_argument(
        "--link-mode",
        choices=tuple(mode.value for mode in LinkMode),
        default=LinkMode.PHYSICAL.value,
        help=(
            "What a drawn link represents: one link per physical interface, or one "
            "link per port-channel with its members in the link's tooltip "
            "(default: %(default)s)."
        ),
    )

    stp_parser = subparsers.add_parser("stp", help="Generate per-VLAN spanning-tree diagrams.")
    _add_common_arguments(stp_parser)
    _add_vlan_selection_arguments(stp_parser, with_group_mode=True)

    hsrp_parser = subparsers.add_parser("hsrp", help="Generate per-VLAN HSRP diagrams.")
    _add_common_arguments(hsrp_parser)
    _add_vlan_selection_arguments(hsrp_parser, with_group_mode=False)

    bgp_parser = subparsers.add_parser("bgp", help="Generate the BGP session graph.")
    _add_common_arguments(bgp_parser)

    all_parser = subparsers.add_parser("all", help="Generate every view and every CSV table.")
    _add_common_arguments(all_parser)

    return parser


def _run_parse(args: argparse.Namespace) -> int:
    """Ingest captures, populate the model, and write every CSV table."""
    try:
        source = FileDataSource(args.input)
        model = build_network_model(source, default_platform=args.platform)
    except OSError as exc:
        logger.error("Failed to read captures from '%s': %s", args.input, exc)
        return 1

    try:
        output_root = resolve_output_root(args.output)
        csv_dir = write_csv_tables(model, output_root)
    except OSError as exc:
        logger.error("Failed to write output to '%s': %s", args.output, exc)
        return 1

    logger.info("Parsed %d device(s); wrote CSV tables to %s", len(model.devices), csv_dir)
    return 0


def _run_l2(args: argparse.Namespace) -> int:
    """Ingest captures, populate the model, and render the L2 draw.io diagram."""
    try:
        source = FileDataSource(args.input)
        model = build_network_model(source, default_platform=args.platform)
    except OSError as exc:
        logger.error("Failed to read captures from '%s': %s", args.input, exc)
        return 1

    link_mode = LinkMode(args.link_mode)
    diagram = l2_view.build(model, endpoints=args.endpoints, link_mode=link_mode)

    try:
        output_root = resolve_output_root(args.output)
        output_path = output_root / "l2" / _l2_output_filename(args.endpoints, link_mode)
        render_diagram(diagram, output_path, apply_lucidify=not args.no_lucidify)
    except OSError as exc:
        logger.error("Failed to write output to '%s': %s", args.output, exc)
        return 1

    logger.info(
        "Rendered L2 diagram (%d node(s), %d link(s)) to %s",
        len(diagram.nodes),
        len(diagram.links),
        output_path,
    )
    return 0


def _l2_output_filename(endpoints: str, link_mode: LinkMode) -> str:
    """Name the L2 diagram after both of its options, so neither view overwrites the other."""
    suffix = _L2_PORT_CHANNEL_SUFFIX if link_mode is LinkMode.PORT_CHANNEL else ""
    return f"{_L2_OUTPUT_STEMS[endpoints]}{suffix}.drawio"


class _BuildVlanGroups(Protocol):
    """How this module asks a per-VLAN view for its diagrams.

    The views' own `build_groups` signatures differ -- only `views/stp.py` takes a
    `group_mode` -- so each view reads its options off `args` in a small adapter below,
    and `_run_vlan_view` stays free of per-view option handling.
    """

    def __call__(self, model: NetworkModel, args: argparse.Namespace) -> list[VlanDiagramGroup]: ...


@dataclass(frozen=True)
class _VlanDiagramView:
    """One of the two per-VLAN views (`stp`, `hsrp`), as this module needs to drive it.

    Both select VLANs with `--vlan`/`--all` and both return a `VlanDiagramGroup` per
    diagram, so they share one handler; only the names, the two functions, and any
    view-specific sanity check differ.
    """

    name: str  # the subcommand, and the `output/<name>/` subdirectory
    label: str  # how the view is named in log messages
    build_groups: _BuildVlanGroups
    output_filename: Callable[[tuple[int, ...]], str]
    warn_about: Callable[[VlanDiagramGroup], None] | None = None


def _run_vlan_view(args: argparse.Namespace, view: _VlanDiagramView) -> int:
    """Ingest captures, populate the model, and render `view`'s per-VLAN/grouped diagrams."""
    if args.vlan is None and not args.all:
        logger.error("'%s' requires either --vlan <N> or --all.", view.name)
        return 1

    try:
        source = FileDataSource(args.input)
        model = build_network_model(source, default_platform=args.platform)
    except OSError as exc:
        logger.error("Failed to read captures from '%s': %s", args.input, exc)
        return 1

    groups = view.build_groups(model, args)

    try:
        output_root = resolve_output_root(args.output)
        for group in groups:
            output_path = output_root / view.name / view.output_filename(group.vlan_ids)
            render_diagram(group.diagram, output_path, apply_lucidify=not args.no_lucidify)
            _log_vlan_diagram(view, group, output_path)
            if view.warn_about is not None:
                view.warn_about(group)
    except OSError as exc:
        logger.error("Failed to write output to '%s': %s", args.output, exc)
        return 1

    logger.info("Rendered %d %s diagram(s) to %s", len(groups), view.label, output_root / view.name)
    return 0


def _log_vlan_diagram(view: _VlanDiagramView, group: VlanDiagramGroup, output_path: Path) -> None:
    logger.info(
        "Rendered %s diagram for VLAN(s) %s (%d node(s), %d link(s)) to %s",
        view.label,
        _vlan_list(group),
        len(group.diagram.nodes),
        len(group.diagram.links),
        output_path,
    )


def _warn_about_stp_islands(group: VlanDiagramGroup) -> None:
    """Warn about the one diagram shape that is always a mistake.

    A diagram with several switches and no links between them is what a silently dropped
    link looks like from the outside -- most often a port-channel the captures never
    described, since `show spanning-tree` names the bundle and CDP/LLDP name its members.
    The HSRP view cannot produce this shape: it draws its own links, from each member to
    its virtual gateway, rather than joining spanning-tree state to a discovered topology.
    """
    if len(group.diagram.nodes) > 1 and not group.diagram.links:
        logger.warning(
            "VLAN(s) %s: %d node(s) but no links. Re-run as 'nettopo --log-level DEBUG stp "
            "...' to see why each link was dropped; if the switches are joined by "
            "port-channels, check that the captures include 'show etherchannel summary'.",
            _vlan_list(group),
            len(group.diagram.nodes),
        )


def _vlan_list(group: VlanDiagramGroup) -> str:
    return ", ".join(str(vlan_id) for vlan_id in group.vlan_ids)


def _build_stp_groups(model: NetworkModel, args: argparse.Namespace) -> list[VlanDiagramGroup]:
    return stp_view.build_groups(model, group_mode=GroupMode(args.group_mode), vlan=args.vlan)


def _build_hsrp_groups(model: NetworkModel, args: argparse.Namespace) -> list[VlanDiagramGroup]:
    return hsrp_view.build_groups(model, vlan=args.vlan)


_STP_VIEW = _VlanDiagramView(
    name="stp",
    label="STP",
    build_groups=_build_stp_groups,
    output_filename=stp_view.stp_output_filename,
    warn_about=_warn_about_stp_islands,
)
_HSRP_VIEW = _VlanDiagramView(
    name="hsrp",
    label="HSRP",
    build_groups=_build_hsrp_groups,
    output_filename=hsrp_view.hsrp_output_filename,
)


def _run_stp(args: argparse.Namespace) -> int:
    return _run_vlan_view(args, _STP_VIEW)


def _run_hsrp(args: argparse.Namespace) -> int:
    return _run_vlan_view(args, _HSRP_VIEW)


def _run_bgp(args: argparse.Namespace) -> int:
    """Ingest captures, populate the model, and render the BGP session graph."""
    try:
        source = FileDataSource(args.input)
        model = build_network_model(source, default_platform=args.platform)
    except OSError as exc:
        logger.error("Failed to read captures from '%s': %s", args.input, exc)
        return 1

    diagram = bgp_view.build(model)

    try:
        output_root = resolve_output_root(args.output)
        output_path = output_root / "bgp" / _BGP_OUTPUT_FILENAME
        render_diagram(diagram, output_path, apply_lucidify=not args.no_lucidify)
    except OSError as exc:
        logger.error("Failed to write output to '%s': %s", args.output, exc)
        return 1

    logger.info(
        "Rendered BGP diagram (%d node(s), %d session(s)) to %s",
        len(diagram.nodes),
        len(diagram.links),
        output_path,
    )
    return 0


def _run_unimplemented(args: argparse.Namespace) -> int:
    """Placeholder handler: no view/render logic exists yet (Phase 5+)."""
    logger.error("'%s' is not implemented yet.", args.command)
    return 1


_COMMAND_HANDLERS: dict[str, Callable[[argparse.Namespace], int]] = {
    "parse": _run_parse,
    "l2": _run_l2,
    "stp": _run_stp,
    "hsrp": _run_hsrp,
    "bgp": _run_bgp,
    "all": _run_unimplemented,
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(levelname)s: %(message)s")

    handler = _COMMAND_HANDLERS[args.command]
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
