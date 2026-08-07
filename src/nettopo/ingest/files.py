"""FileDataSource: read a directory of saved device captures (PROJECT_SPEC.md section 4).

Each file is one device's captured output: several `show` commands concatenated, each
preceded by its device prompt line (`hostname#show ...`). That prompt line is how a
device is identified as a **source device** (we have its own capture, not just a
neighbor mention).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from nettopo.ingest.base import Capture, DataSource
from nettopo.utils.command_sections import first_prompt_hostname


class FileDataSource(DataSource):
    """Reads every regular file in `directory` as one device's capture."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)

    def discover(self) -> Iterator[Capture]:
        if not self.directory.is_dir():
            raise NotADirectoryError(f"input directory not found: {self.directory}")

        for path in sorted(self.directory.iterdir()):
            if not path.is_file():
                continue
            raw_text = path.read_text(encoding="utf-8-sig")
            device_hint = first_prompt_hostname(raw_text) or path.stem
            yield Capture(device_hint=device_hint, raw_text=raw_text, platform_hint=None)
