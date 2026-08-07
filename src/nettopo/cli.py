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

_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

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


def _run_unimplemented(command: str) -> int:
    """Placeholder handler: no ingest/parse/view logic exists yet (Phase 0)."""
    logger.error("'%s' is not implemented yet (Phase 0 scaffolding only).", command)
    return 1


_COMMAND_HANDLERS: dict[str, Callable[[str], int]] = {
    "parse": _run_unimplemented,
    "l2": _run_unimplemented,
    "stp": _run_unimplemented,
    "hsrp": _run_unimplemented,
    "bgp": _run_unimplemented,
    "all": _run_unimplemented,
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(levelname)s: %(message)s")

    handler = _COMMAND_HANDLERS[args.command]
    return handler(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
