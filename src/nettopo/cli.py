"""CLI entry point: argument parsing and orchestration only.

Each subcommand runs the same pipeline (ingest -> parse -> model -> view ->
render/export) by calling into the layers that own each stage. The business logic
itself lives there, not here: this module builds the argument parser, dispatches to a
handler, and turns the layers' exceptions into an exit code and a log line.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from nettopo import __version__
from nettopo.export.csv_export import write_csv_tables
from nettopo.ingest.files import FileDataSource
from nettopo.ingest.model_builder import build_network_model
from nettopo.model.entities import NetworkModel
from nettopo.model.grouping import GroupMode
from nettopo.render.drawio import render_diagram
from nettopo.utils.paths import (
    DEFAULT_CAPTURE_DIR,
    DEFAULT_REPORT_NAME,
    resolve_input_root,
    resolve_output_root,
)
from nettopo.views import bgp as bgp_view
from nettopo.views import hsrp as hsrp_view
from nettopo.views import l2 as l2_view
from nettopo.views import stp as stp_view
from nettopo.views.diagram import Diagram, VlanDiagramGroup
from nettopo.views.l2 import LinkMode

if TYPE_CHECKING:
    # Annotations only. These modules reach netmiko, and `collect` is the one command
    # that may touch it -- importing them here at runtime would pull the SSH backend
    # into every other command's process for nothing.
    from nettopo.ingest.files import CaptureWriter
    from nettopo.ingest.live import CollectionResult

_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

_L2_OUTPUT_STEMS = {"all": "l2_full", "network-only": "l2_network-only"}
_L2_PORT_CHANNEL_SUFFIX = "_port-channels"

# The L2 diagrams `nettopo all` writes, and the whole of PROJECT_SPEC.md section 8's
# `output/l2/` tree. The fourth combination (network-only over port-channels) is left out
# deliberately: `network-only` already drops the endpoints that make a dense diagram hard
# to read, so collapsing its bundles too would differ from `l2_network-only.drawio` only on
# the rare uplink bundle between two network devices.
_ALL_L2_VARIANTS: tuple[tuple[str, LinkMode], ...] = (
    ("all", LinkMode.PHYSICAL),
    ("all", LinkMode.PORT_CHANNEL),
    ("network-only", LinkMode.PHYSICAL),
)

# BGP renders one diagram for the whole network and takes no view-specific options, so
# unlike the L2 and per-VLAN views its filename is fixed (PROJECT_SPEC.md section 8).
_BGP_OUTPUT_FILENAME = "bgp.drawio"

logger = logging.getLogger("nettopo")


def _add_common_arguments(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument(
        "-i",
        "--input",
        default=DEFAULT_CAPTURE_DIR,
        help="Directory containing device captures (default: %(default)s).",
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

    _add_collect_parser(subparsers)

    return parser


def _add_collect_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Define `collect`, the one command that opens a network connection.

    It shares no options with the others: they read a capture directory, this one writes
    it. `-o` therefore defaults to the same `~/configs` the others read from, so the two
    halves of the workflow line up without a path being typed twice.
    """
    collect_parser = subparsers.add_parser(
        "collect",
        help="Collect show-command captures from live devices over SSH.",
        description=(
            "Connects to every device in the inventory, runs the show commands the other "
            "subcommands parse, and writes one capture file per device named after that "
            "device's own hostname. Credentials are asked for on the terminal and are "
            "never stored. This is the only nettopo command that opens a network "
            "connection, and it only ever sends 'show' commands."
        ),
    )
    collect_parser.add_argument(
        "-I",
        "--inventory",
        required=True,
        help="File listing the devices to collect from, one device per line.",
    )
    collect_parser.add_argument(
        "-o",
        "--output",
        default=DEFAULT_CAPTURE_DIR,
        help="Directory to write capture files into (default: %(default)s).",
    )
    collect_parser.add_argument(
        "--report",
        default=DEFAULT_REPORT_NAME,
        help=(
            "Where to write the run report CSV, relative to the current directory. "
            "Use '-' for stdout (default: %(default)s)."
        ),
    )
    collect_parser.add_argument(
        "-u",
        "--user",
        help="SSH username. Prompted for if omitted; there is deliberately no password flag.",
    )
    collect_parser.add_argument(
        "--port", type=int, default=22, help="SSH port (default: %(default)s)."
    )
    collect_parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help=(
            "Seconds to wait for the connection, banner and authentication (default: %(default)s)."
        ),
    )
    collect_parser.add_argument(
        "--command-timeout",
        type=float,
        default=120.0,
        help="Seconds to wait for one command's output (default: %(default)s).",
    )
    collect_parser.add_argument(
        "--host-key-checking",
        choices=("strict", "none"),
        default="strict",
        help=(
            "Whether a device's SSH host key must already be known. 'none' accepts any "
            "key and is for labs only (default: %(default)s)."
        ),
    )


def _load_model(args: argparse.Namespace) -> NetworkModel | None:
    """Ingest `args.input` into a populated model, or log why it could not be read.

    Every command starts here, and `all` calls it once for all five views: ingestion and
    parsing are the expensive stages, and nothing downstream of the model mutates it.
    """
    input_root = resolve_input_root(args.input)
    try:
        source = FileDataSource(input_root)
        return build_network_model(source, default_platform=args.platform)
    except OSError as exc:
        # The resolved path, not `args.input`: a user who never passed `-i` would
        # otherwise be told that '~/configs' is missing, which no shell would show them.
        logger.error("Failed to read captures from '%s': %s", input_root, exc)
        return None


def _write_diagram(
    diagram: Diagram,
    output_path: Path,
    *,
    label: str,
    link_noun: str = "link",
) -> None:
    """Render one built diagram and report what it contained."""
    render_diagram(diagram, output_path)
    logger.info(
        "Rendered %s diagram (%d node(s), %d %s(s)) to %s",
        label,
        len(diagram.nodes),
        len(diagram.links),
        link_noun,
        output_path,
    )


def _warn_empty_view(label: str, target: str) -> None:
    """Report a view the captures held no data for.

    Only `all` runs views the user did not name, so only `all` calls this: a capture set
    that covers part of the network -- access switches that speak no BGP, say -- is
    ordinary input, and skipping the view it cannot fill is not a failed run. A user who
    types `nettopo bgp` asked for that diagram specifically and still gets it, empty.
    """
    logger.warning("No %s data in the captures; skipped %s.", label, target)


def _run_parse(args: argparse.Namespace) -> int:
    """Ingest captures, populate the model, and write every CSV table."""
    model = _load_model(args)
    if model is None:
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
    model = _load_model(args)
    if model is None:
        return 1

    link_mode = LinkMode(args.link_mode)
    diagram = l2_view.build(model, endpoints=args.endpoints, link_mode=link_mode)

    try:
        output_root = resolve_output_root(args.output)
        output_path = output_root / "l2" / _l2_output_filename(args.endpoints, link_mode)
        _write_diagram(diagram, output_path, label="L2")
    except OSError as exc:
        logger.error("Failed to write output to '%s': %s", args.output, exc)
        return 1

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

    model = _load_model(args)
    if model is None:
        return 1

    groups = view.build_groups(model, args)

    try:
        output_root = resolve_output_root(args.output)
        _render_vlan_groups(view, groups, output_root)
    except OSError as exc:
        logger.error("Failed to write output to '%s': %s", args.output, exc)
        return 1

    return 0


def _render_vlan_groups(
    view: _VlanDiagramView,
    groups: list[VlanDiagramGroup],
    output_root: Path,
) -> None:
    """Write one diagram per group into `output/<view>/`."""
    for group in groups:
        output_path = output_root / view.name / view.output_filename(group.vlan_ids)
        render_diagram(group.diagram, output_path)
        _log_vlan_diagram(view, group, output_path)
        if view.warn_about is not None:
            view.warn_about(group)

    logger.info("Rendered %d %s diagram(s) to %s", len(groups), view.label, output_root / view.name)


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
    model = _load_model(args)
    if model is None:
        return 1

    diagram = bgp_view.build(model)

    try:
        output_root = resolve_output_root(args.output)
        output_path = output_root / "bgp" / _BGP_OUTPUT_FILENAME
        _write_diagram(
            diagram,
            output_path,
            label="BGP",
            link_noun="session",
        )
    except OSError as exc:
        logger.error("Failed to write output to '%s': %s", args.output, exc)
        return 1

    return 0


def _run_all(args: argparse.Namespace) -> int:
    """Write every CSV table and every view's diagrams from one ingested model.

    The views take no options here: `all` is the "give me everything this capture set
    supports" command, so it draws every VLAN of the per-VLAN views (`--group-mode
    per-vlan`, which never collapses two VLANs into one drawing) and every L2 variant
    PROJECT_SPEC.md section 8's output tree lists. A view the captures hold no data for is
    skipped with a warning rather than failing the run -- see `_warn_empty_view`.
    """
    model = _load_model(args)
    if model is None:
        return 1

    try:
        output_root = resolve_output_root(args.output)
        csv_dir = write_csv_tables(model, output_root)
        logger.info("Parsed %d device(s); wrote CSV tables to %s", len(model.devices), csv_dir)

        _render_all_l2_diagrams(model, output_root)

        for view, groups in (
            (_STP_VIEW, stp_view.build_groups(model, group_mode=GroupMode.PER_VLAN)),
            (_HSRP_VIEW, hsrp_view.build_groups(model)),
        ):
            if not groups:
                _warn_empty_view(view.label, f"output/{view.name}/")
                continue
            _render_vlan_groups(view, groups, output_root)

        bgp_diagram = bgp_view.build(model)
        if bgp_diagram.nodes:
            _write_diagram(
                bgp_diagram,
                output_root / "bgp" / _BGP_OUTPUT_FILENAME,
                label="BGP",
                link_noun="session",
            )
        else:
            _warn_empty_view("BGP", f"output/bgp/{_BGP_OUTPUT_FILENAME}")
    except OSError as exc:
        logger.error("Failed to write output to '%s': %s", args.output, exc)
        return 1

    logger.info("Finished 'all': output written to %s", output_root)
    return 0


def _render_all_l2_diagrams(model: NetworkModel, output_root: Path) -> None:
    """Write each of `all`'s L2 variants the captures hold adjacencies for.

    Emptiness is judged on links, not nodes: an L2 diagram is a drawing of adjacencies,
    and captures with no CDP/LLDP output still yield one node per device, so a node count
    alone would write a page of unconnected boxes. The `network-only` variant is judged
    separately -- it can come out empty while the full one is not, when every discovered
    neighbor is an endpoint.
    """
    for endpoints, link_mode in _ALL_L2_VARIANTS:
        diagram = l2_view.build(model, endpoints=endpoints, link_mode=link_mode)
        filename = _l2_output_filename(endpoints, link_mode)
        if not diagram.links:
            _warn_empty_view("L2 neighbor", f"output/l2/{filename}")
            continue
        _write_diagram(diagram, output_root / "l2" / filename, label="L2")


def _run_collect(args: argparse.Namespace) -> int:
    """Collect captures from live devices and write the run report.

    The SSH backend is imported here rather than at module scope: `import nettopo.cli` --
    and therefore every other command -- must never reach netmiko, which
    `tests/test_no_network.py` asserts in a fresh interpreter.
    """
    from nettopo.export.collect_report import write_collect_report
    from nettopo.ingest.credentials import CredentialError, prompt_credentials
    from nettopo.ingest.files import CaptureWriter
    from nettopo.ingest.inventory import InventoryError, load_inventory
    from nettopo.ingest.live import LiveDataSource

    try:
        targets = load_inventory(args.inventory)
        credentials = prompt_credentials(username=args.user)
    except (InventoryError, CredentialError) as exc:
        logger.error("%s", exc)
        return 1

    if args.host_key_checking == "none":
        logger.warning(
            "Host key checking is off: an unknown key will be accepted, so a machine "
            "impersonating a device would receive these credentials. Labs only."
        )

    logger.info("Collecting from %d device(s): %s", len(targets), ", ".join(targets))

    try:
        output_root = resolve_output_root(args.output)
    except OSError as exc:
        logger.error("Failed to prepare output directory '%s': %s", args.output, exc)
        return 1

    writer = CaptureWriter(output_root)
    source = LiveDataSource(
        targets,
        credentials,
        port=args.port,
        timeout=args.timeout,
        command_timeout=args.command_timeout,
        strict_host_keys=args.host_key_checking == "strict",
    )

    try:
        result = source.collect(on_capture=writer.write)
    except OSError as exc:
        logger.error("Failed to write captures to '%s': %s", output_root, exc)
        return 1

    _warn_about_duplicate_hostnames(result, writer)

    try:
        write_collect_report(
            result,
            path=Path(args.report),
            paths_by_target=writer.paths_by_target,
            duplicates_by_target={
                outcome.target: writer.duplicates_of(outcome.target) for outcome in result.outcomes
            },
        )
    except OSError as exc:
        logger.error("Failed to write the collection report to '%s': %s", args.report, exc)
        return 1

    return _report_collection_summary(result, output_root)


def _warn_about_duplicate_hostnames(result: CollectionResult, writer: CaptureWriter) -> None:
    """Say so, loudly, when two devices answer to the same name.

    Worth a warning of its own because the consequence lands somewhere else entirely:
    `model.devices` is keyed by hostname, so a later `nettopo all` will merge these two
    boxes into a single node with both of their links. Distinct filenames do not prevent
    that -- only fixing the hostnames does -- and at collection time nettopo knows what
    the model never will: that these are two different devices at two different addresses.
    """
    for outcome in result.outcomes:
        duplicates = writer.duplicates_of(outcome.target)
        if not outcome.is_ok or not duplicates:
            continue
        logger.warning(
            "%s reports the hostname '%s', which %s also reports. Their captures are kept "
            "apart, but a diagram built from them will merge these devices into one node "
            "until the hostnames differ.",
            outcome.target,
            outcome.capture.device_hint if outcome.capture else "?",
            ", ".join(duplicates),
        )


def _report_collection_summary(result: CollectionResult, output_root: Path) -> int:
    """Log what the run achieved and turn it into an exit code.

    Anything short of every device collected is a failure: `nettopo collect && nettopo all`
    is the obvious composition, and a partial capture set quietly producing a partial
    diagram is the failure mode this tool exists to prevent.
    """
    counts = result.counts_by_status()
    collected = counts["ok"]

    if result.succeeded:
        logger.info("Collected %d device(s) into %s", collected, output_root)
        return 0

    logger.error(
        "Collected %d of %d device(s); %d failed, %d skipped for enable, %d not attempted.",
        collected,
        len(result.outcomes),
        counts["failed"],
        counts["no-enable"],
        counts["skipped"],
    )
    return 1


_COMMAND_HANDLERS: dict[str, Callable[[argparse.Namespace], int]] = {
    "parse": _run_parse,
    "l2": _run_l2,
    "stp": _run_stp,
    "hsrp": _run_hsrp,
    "bgp": _run_bgp,
    "all": _run_all,
    "collect": _run_collect,
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(levelname)s: %(message)s")

    handler = _COMMAND_HANDLERS[args.command]
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
