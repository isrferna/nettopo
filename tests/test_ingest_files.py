"""Tests for `FileDataSource` (PROJECT_SPEC.md section 4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nettopo.ingest.files import FileDataSource


def test_discover_yields_one_capture_per_file(tmp_path: Path) -> None:
    (tmp_path / "sw1.txt").write_text("sw1#show version\nCisco IOS Software\n")
    (tmp_path / "sw2.txt").write_text("sw2#show version\nCisco IOS Software\n")

    captures = list(FileDataSource(tmp_path).discover())

    assert {capture.device_hint for capture in captures} == {"sw1", "sw2"}


def test_discover_strips_a_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "sw1.txt"
    path.write_bytes("sw1#show version\nCisco IOS Software\n".encode("utf-8-sig"))

    (capture,) = list(FileDataSource(tmp_path).discover())

    assert not capture.raw_text.startswith("﻿")
    assert capture.raw_text.startswith("sw1#show version")


def test_discover_falls_back_to_filename_when_no_prompt_line_found(tmp_path: Path) -> None:
    (tmp_path / "unrecognized.txt").write_text("no prompt lines in this file at all\n")

    (capture,) = list(FileDataSource(tmp_path).discover())

    assert capture.device_hint == "unrecognized"


def test_discover_ignores_subdirectories(tmp_path: Path) -> None:
    (tmp_path / "sw1.txt").write_text("sw1#show version\nCisco IOS Software\n")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "nested.txt").write_text("nested#show version\nCisco IOS Software\n")

    captures = list(FileDataSource(tmp_path).discover())

    assert {capture.device_hint for capture in captures} == {"sw1"}


def test_discover_raises_for_a_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(NotADirectoryError):
        list(FileDataSource(tmp_path / "does-not-exist").discover())
