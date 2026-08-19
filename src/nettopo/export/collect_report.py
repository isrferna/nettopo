"""The `nettopo collect` run report (PROJECT_SPEC.md section 8).

One row per inventory entry, so a device that was never reached is as visible as one that
was collected. A collection run is the part of the workflow with no diagram to inspect
afterwards, so the report is the only record of what happened -- which devices answered,
which did not and why, and where each capture landed.
"""

from __future__ import annotations

import csv
import logging
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from nettopo.export.csv_export import csv_safe, write_table
from nettopo.ingest.live import CollectionResult, Outcome
from nettopo.utils.paths import DEFAULT_REPORT_NAME

logger = logging.getLogger("nettopo")

__all__ = ["DEFAULT_REPORT_NAME", "write_collect_report"]

_REPORT_HEADER = (
    "target",
    "hostname",
    "status",
    "platform",
    "commands",
    "capture_file",
    "detail",
)

# Not a failure of collection: the device answered everything asked of it. It is a
# configuration observation, reported because the model keys devices by hostname and will
# merge these two into one node.
_DUPLICATE_HOSTNAME = "duplicate-hostname"


def write_collect_report(
    result: CollectionResult,
    *,
    path: Path,
    paths_by_target: Mapping[str, Path],
    duplicates_by_target: Mapping[str, tuple[str, ...]],
) -> None:
    """Write the report for one run to `path`, or to stdout when `path` is `-`.

    `paths_by_target` and `duplicates_by_target` come from the `CaptureWriter`, which is
    the authority on where a capture finally landed: a duplicate hostname renames a file
    that was already written, so the collector's own record of it would be stale.
    """
    rows = _rows(result, paths_by_target, duplicates_by_target)

    if str(path) == "-":
        _write_to_stdout(rows)
        return

    write_table(path, _REPORT_HEADER, rows)
    logger.info("Wrote the collection report to %s", path)


def _rows(
    result: CollectionResult,
    paths_by_target: Mapping[str, Path],
    duplicates_by_target: Mapping[str, tuple[str, ...]],
) -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = []
    for outcome in result.outcomes:
        duplicates = duplicates_by_target.get(outcome.target, ())
        status: str = outcome.outcome.value
        detail = outcome.detail
        if outcome.outcome is Outcome.OK and duplicates:
            status = _DUPLICATE_HOSTNAME
            detail = "same hostname as " + ", ".join(duplicates)

        capture_path = paths_by_target.get(outcome.target)
        rows.append(
            (
                outcome.target,
                outcome.capture.device_hint if outcome.capture else "",
                status,
                outcome.platform,
                outcome.commands,
                str(capture_path) if capture_path else "",
                detail,
            )
        )
    return rows


def _write_to_stdout(rows: Sequence[tuple[object, ...]]) -> None:
    """`--report -`: the same table, for a pipeline that would rather not touch disk.

    Sanitized exactly as the file path is -- a report redirected into a file and opened
    in a spreadsheet is no safer than one written there directly.
    """
    writer = csv.writer(sys.stdout)
    writer.writerow(_REPORT_HEADER)
    for row in rows:
        writer.writerow(csv_safe(value) for value in row)
