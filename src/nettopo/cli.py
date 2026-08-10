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
from pathlib import Path

from nettopo import __version__
from nettopo.export.csv_export import write_csv_tables
from nettopo.ingest.files import FileDataSource
from nettopo.ingest.model_builder import build_network_model
from nettopo.model.grouping import GroupMode
from nettopo.render.drawio import render_diagram
from nettopo.utils.paths import resolve_output_root
from nettopo.views import l2 as l2_view
from nettopo.views import stp as stp_view
from nettopo.views.l2 import LinkMode

_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

_L2_OUTPUT_STEMS = {"all": "l2_full", "network-only": "l2_network-only"}
_L2_PORT_CHANNEL_SUFFIX = "_port-channels"

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
        help="Skip the Lucidchart-friendliness post-process on generated draw.io files.",
    )


def _add_group_mode_arguments(subparser: argparse.ArgumentParser) -> None:
    group = subparser.add_mutually_exclusive_group()
    group.add_argument("--vlan", type=int, help="Restrict output to a single VLAN.")
    group.add_argument(
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
    _add_group_mode_arguments(stp_parser)

    hsrp_parser = subparsers.add_parser("hsrp", help="Generate per-VLAN HSRP diagrams.")
    _add_common_arguments(hsrp_parser)
    _add_group_mode_arguments(hsrp_parser)

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


def _run_stp(args: argparse.Namespace) -> int:
    """Ingest captures, populate the model, and render per-VLAN/grouped STP diagrams."""
    if args.vlan is None and not args.all:
        logger.error("'stp' requires either --vlan <N> or --all.")
        return 1

    try:
        source = FileDataSource(args.input)
        model = build_network_model(source, default_platform=args.platform)
    except OSError as exc:
        logger.error("Failed to read captures from '%s': %s", args.input, exc)
        return 1

    group_mode = GroupMode(args.group_mode)
    groups = stp_view.build_groups(model, group_mode=group_mode, vlan=args.vlan)

    try:
        output_root = resolve_output_root(args.output)
        for group in groups:
            output_path = output_root / "stp" / stp_view.stp_output_filename(group.vlan_ids)
            render_diagram(group.diagram, output_path, apply_lucidify=not args.no_lucidify)
            _log_stp_group(group, output_path)
    except OSError as exc:
        logger.error("Failed to write output to '%s': %s", args.output, exc)
        return 1

    logger.info("Rendered %d STP diagram(s) to %s", len(groups), output_root / "stp")
    return 0


def _log_stp_group(group: stp_view.StpDiagramGroup, output_path: Path) -> None:
    """Report a diagram's size, and warn about the one shape that is always a mistake.

    A diagram with several switches and no links between them is what a silently dropped
    link looks like from the outside -- most often a port-channel the captures never
    described, since `show spanning-tree` names the bundle and CDP/LLDP name its members.
    """
    diagram = group.diagram
    logger.info(
        "Rendered STP diagram for VLAN(s) %s (%d node(s), %d link(s)) to %s",
        ", ".join(str(vlan_id) for vlan_id in group.vlan_ids),
        len(diagram.nodes),
        len(diagram.links),
        output_path,
    )
    if len(diagram.nodes) > 1 and not diagram.links:
        logger.warning(
            "VLAN(s) %s: %d node(s) but no links. Re-run as 'nettopo --log-level DEBUG stp "
            "...' to see why each link was dropped; if the switches are joined by "
            "port-channels, check that the captures include 'show etherchannel summary'.",
            ", ".join(str(vlan_id) for vlan_id in group.vlan_ids),
            len(diagram.nodes),
        )


def _run_unimplemented(args: argparse.Namespace) -> int:
    """Placeholder handler: no view/render logic exists yet (Phase 5+)."""
    logger.error("'%s' is not implemented yet.", args.command)
    return 1


_COMMAND_HANDLERS: dict[str, Callable[[argparse.Namespace], int]] = {
    "parse": _run_parse,
    "l2": _run_l2,
    "stp": _run_stp,
    "hsrp": _run_unimplemented,
    "bgp": _run_unimplemented,
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
