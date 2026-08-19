"""End-to-end tests for `nettopo collect` (PROJECT_SPEC.md sections 4, 9).

Driven through `main()` against the scripted `fake_netmiko` connection, so these exercise
argument parsing, collection, file naming and the report together -- without a socket.
"""

from __future__ import annotations

import builtins
import csv
import sys
from pathlib import Path

import pytest
from netmiko.exceptions import NetmikoTimeoutException

from nettopo.cli import build_parser, main
from nettopo.ingest import credentials as credentials_module
from nettopo.utils.paths import DEFAULT_CAPTURE_DIR, DEFAULT_REPORT_NAME
from tests.conftest import FakeConnection, FakeNetmiko


@pytest.fixture
def answered_prompts(monkeypatch: pytest.MonkeyPatch) -> None:
    """A terminal that supplies the credentials, so `collect` can run unattended here."""
    monkeypatch.setattr(credentials_module.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(credentials_module.getpass, "getpass", lambda _prompt: "secret")
    monkeypatch.setattr(builtins, "input", lambda _prompt: "netops")


def _inventory(tmp_path: Path, *targets: str) -> Path:
    path = tmp_path / "inventario.txt"
    path.write_text("\n".join(targets) + "\n", encoding="utf-8")
    return path


def _run(tmp_path: Path, inventory: Path, *extra: str) -> int:
    return main(
        [
            "collect",
            "--inventory",
            str(inventory),
            "-o",
            str(tmp_path / "configs"),
            "--report",
            str(tmp_path / DEFAULT_REPORT_NAME),
            *extra,
        ]
    )


def _report_rows(tmp_path: Path) -> list[dict[str, str]]:
    with (tmp_path / DEFAULT_REPORT_NAME).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_collect_defaults_match_the_documented_workflow() -> None:
    args = build_parser().parse_args(["collect", "--inventory", "i.txt"])

    assert args.output == DEFAULT_CAPTURE_DIR  # the same directory every other command reads
    assert args.report == DEFAULT_REPORT_NAME
    assert args.host_key_checking == "strict"
    assert args.port == 22


def test_the_inventory_is_required() -> None:
    with pytest.raises(SystemExit) as excinfo:
        build_parser().parse_args(["collect"])
    assert excinfo.value.code == 2


def test_there_is_no_way_to_pass_a_password_on_the_command_line() -> None:
    """argv is readable by every user on the host; this is a deliberate omission."""
    help_text = build_parser().parse_args
    with pytest.raises(SystemExit):
        help_text(["collect", "--inventory", "i.txt", "--password", "hunter2"])


def test_an_ip_only_inventory_still_produces_hostname_named_files(
    tmp_path: Path, fake_netmiko: FakeNetmiko, answered_prompts: None
) -> None:
    fake_netmiko.devices["10.0.0.1"] = FakeConnection(
        host="10.0.0.1", outputs=dict(fake_netmiko.default_outputs), prompt="sw-core#"
    )

    assert _run(tmp_path, _inventory(tmp_path, "10.0.0.1")) == 0
    assert (tmp_path / "configs" / "sw-core.txt").exists()


def test_two_devices_with_one_hostname_neither_overwrite_nor_keep_the_clean_name(
    tmp_path: Path, fake_netmiko: FakeNetmiko, answered_prompts: None
) -> None:
    """The factory-default `switch` case: both files survive, and both say which is which."""
    for address in ("10.0.0.11", "10.0.0.12"):
        fake_netmiko.devices[address] = FakeConnection(
            host=address, outputs=dict(fake_netmiko.default_outputs), prompt="switch#"
        )

    exit_code = _run(tmp_path, _inventory(tmp_path, "10.0.0.11", "10.0.0.12"))

    written = sorted(path.name for path in (tmp_path / "configs").iterdir())
    assert written == ["switch_10.0.0.11.txt", "switch_10.0.0.12.txt"]
    assert exit_code == 0  # collection succeeded; the hostnames are the operator's problem
    assert [row["status"] for row in _report_rows(tmp_path)] == [
        "duplicate-hostname",
        "duplicate-hostname",
    ]


def test_a_prompt_with_path_separators_is_not_taken_as_a_hostname_at_all(
    tmp_path: Path, fake_netmiko: FakeNetmiko, answered_prompts: None
) -> None:
    """The outer of two defences: `_PROMPT_HOSTNAME` accepts only a bare hostname, so a
    prompt like this never reaches the filename layer -- it falls back to the target.

    Scripted with no `show version` so the prompt is the only name on offer; with one, the
    parsed hostname would decide the filename and this defence would not be exercised.
    """
    fake_netmiko.devices["10.0.0.1"] = FakeConnection(
        host="10.0.0.1", outputs={}, prompt="../../etc#"
    )

    _run(tmp_path, _inventory(tmp_path, "10.0.0.1"))

    assert [path.name for path in (tmp_path / "configs").iterdir()] == ["10.0.0.1.txt"]


def test_a_dot_only_hostname_is_contained_by_the_filename_guard(
    tmp_path: Path, fake_netmiko: FakeNetmiko, answered_prompts: None
) -> None:
    """The inner defence. `..` *is* a valid bare hostname as far as the prompt regex is
    concerned, so `safe_join` is what stops `...txt` resolving out of the output root."""
    fake_netmiko.devices["10.0.0.1"] = FakeConnection(host="10.0.0.1", outputs={}, prompt="..#")

    _run(tmp_path, _inventory(tmp_path, "10.0.0.1"))

    written = list((tmp_path / "configs").iterdir())
    assert len(written) == 1
    assert written[0].parent == (tmp_path / "configs").resolve()
    assert ".." not in written[0].name


def test_a_run_that_stops_early_keeps_what_it_already_collected(
    tmp_path: Path, fake_netmiko: FakeNetmiko, answered_prompts: None
) -> None:
    fake_netmiko.connect_errors["10.0.0.3"] = NetmikoTimeoutException("unreachable")
    for address in ("10.0.0.1", "10.0.0.2"):
        fake_netmiko.devices[address] = FakeConnection(
            host=address, outputs=dict(fake_netmiko.default_outputs), prompt=f"sw{address[-1]}#"
        )
    inventory = _inventory(tmp_path, "10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.4")

    exit_code = _run(tmp_path, inventory)

    assert exit_code == 1
    assert sorted(path.name for path in (tmp_path / "configs").iterdir()) == [
        "sw1.txt",
        "sw2.txt",
    ]
    assert [row["status"] for row in _report_rows(tmp_path)] == [
        "ok",
        "ok",
        "failed",
        "skipped",
    ]


def test_the_report_is_written_even_when_every_device_failed(
    tmp_path: Path, fake_netmiko: FakeNetmiko, answered_prompts: None
) -> None:
    """The run where nothing worked is precisely when the report is most useful."""
    fake_netmiko.connect_errors["10.0.0.1"] = NetmikoTimeoutException("unreachable")

    assert _run(tmp_path, _inventory(tmp_path, "10.0.0.1", "10.0.0.2")) == 1

    rows = _report_rows(tmp_path)
    assert [row["status"] for row in rows] == ["failed", "skipped"]
    assert "unreachable" in rows[0]["detail"]


def test_the_report_defaults_to_the_current_directory_not_the_capture_directory(
    tmp_path: Path,
    fake_netmiko: FakeNetmiko,
    answered_prompts: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It is a record of the run, not part of the capture set."""
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    monkeypatch.chdir(workdir)

    exit_code = main(
        [
            "collect",
            "--inventory",
            str(_inventory(tmp_path, "10.0.0.1")),
            "-o",
            str(tmp_path / "configs"),
        ]
    )

    assert exit_code == 0
    assert (workdir / DEFAULT_REPORT_NAME).exists()
    assert not (tmp_path / "configs" / DEFAULT_REPORT_NAME).exists()


def test_a_bad_inventory_is_reported_without_a_traceback(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    assert _run(tmp_path, tmp_path / "nowhere.txt") == 1
    assert "cannot read inventory" in caplog.text


def test_a_missing_extra_asks_for_the_install_rather_than_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A core install must fail helpfully here, not with an ImportError traceback."""
    monkeypatch.setitem(sys.modules, "netmiko", None)
    for module in [name for name in sys.modules if name.startswith("nettopo.ingest.live")]:
        monkeypatch.delitem(sys.modules, module)

    assert _run(tmp_path, _inventory(tmp_path, "10.0.0.1")) == 1
    assert "pip install 'nettopo[collect]'" in caplog.text
