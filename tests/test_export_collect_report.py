"""Tests for the collection run report (PROJECT_SPEC.md section 8)."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from nettopo.export.collect_report import write_collect_report
from nettopo.ingest.base import Capture
from nettopo.ingest.live import CollectionResult, DeviceOutcome, Outcome


def _capture(hostname: str) -> Capture:
    return Capture(device_hint=hostname, raw_text="", platform_hint="cisco_ios")


def _result(*outcomes: DeviceOutcome) -> CollectionResult:
    return CollectionResult(outcomes=outcomes)


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_every_inventory_entry_gets_a_row_including_the_ones_never_reached(
    tmp_path: Path,
) -> None:
    """The point of the report is seeing what was *not* collected as easily as what was."""
    result = _result(
        DeviceOutcome("10.0.0.1", Outcome.OK, _capture("sw1"), "cisco_ios", 10),
        DeviceOutcome("10.0.0.2", Outcome.FAILED, detail="NetmikoTimeoutException: unreachable"),
        DeviceOutcome("10.0.0.3", Outcome.SKIPPED, detail="not attempted"),
    )
    report = tmp_path / "report.csv"

    write_collect_report(
        result,
        path=report,
        paths_by_target={"10.0.0.1": tmp_path / "sw1.txt"},
        duplicates_by_target={},
    )

    rows = _read(report)
    assert [row["target"] for row in rows] == ["10.0.0.1", "10.0.0.2", "10.0.0.3"]
    assert [row["status"] for row in rows] == ["ok", "failed", "skipped"]
    assert rows[0]["hostname"] == "sw1"
    assert rows[0]["commands"] == "10"
    assert rows[0]["capture_file"].endswith("sw1.txt")
    assert rows[1]["capture_file"] == ""
    assert "unreachable" in rows[1]["detail"]


def test_a_duplicate_hostname_is_its_own_status_naming_the_other_device(
    tmp_path: Path,
) -> None:
    result = _result(
        DeviceOutcome("10.0.0.1", Outcome.OK, _capture("switch"), "cisco_ios", 10),
        DeviceOutcome("10.0.0.2", Outcome.OK, _capture("switch"), "cisco_ios", 10),
    )
    report = tmp_path / "report.csv"

    write_collect_report(
        result,
        path=report,
        paths_by_target={
            "10.0.0.1": tmp_path / "switch_10.0.0.1.txt",
            "10.0.0.2": tmp_path / "switch_10.0.0.2.txt",
        },
        duplicates_by_target={"10.0.0.1": ("10.0.0.2",), "10.0.0.2": ("10.0.0.1",)},
    )

    rows = _read(report)
    assert [row["status"] for row in rows] == ["duplicate-hostname", "duplicate-hostname"]
    assert rows[0]["detail"] == "same hostname as 10.0.0.2"
    assert rows[0]["capture_file"].endswith("switch_10.0.0.1.txt")


def test_a_device_reported_hostname_cannot_become_a_spreadsheet_formula(
    tmp_path: Path,
) -> None:
    """OWASP A03. The hostname comes off a device prompt, so it is untrusted input."""
    result = _result(DeviceOutcome("10.0.0.1", Outcome.OK, _capture("=cmd|'/c calc'!A1"), "", 1))
    report = tmp_path / "report.csv"

    write_collect_report(result, path=report, paths_by_target={}, duplicates_by_target={})

    assert _read(report)[0]["hostname"].startswith("'=")


def test_the_report_can_be_written_to_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = _result(DeviceOutcome("10.0.0.1", Outcome.OK, _capture("sw1"), "cisco_ios", 10))

    write_collect_report(result, path=Path("-"), paths_by_target={}, duplicates_by_target={})

    printed = capsys.readouterr().out
    assert printed.splitlines()[0].startswith("target,hostname,status")
    assert "10.0.0.1,sw1,ok,cisco_ios" in printed
    assert not (tmp_path / "-").exists()


def test_stdout_gets_the_same_formula_guard_as_a_file(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A redirected report opened in a spreadsheet is no safer than one written directly."""
    result = _result(DeviceOutcome("10.0.0.1", Outcome.OK, _capture("=HYPERLINK(1)"), "", 1))

    write_collect_report(result, path=Path("-"), paths_by_target={}, duplicates_by_target={})

    assert "'=HYPERLINK(1)" in capsys.readouterr().out


def test_an_unwritable_report_path_names_the_file(tmp_path: Path) -> None:
    result = _result(DeviceOutcome("10.0.0.1", Outcome.OK, _capture("sw1"), "cisco_ios", 1))
    unwritable = tmp_path / "missing-directory" / "report.csv"

    with pytest.raises(OSError, match="report.csv"):
        write_collect_report(result, path=unwritable, paths_by_target={}, duplicates_by_target={})
