"""The capture directory, in both directions (PROJECT_SPEC.md section 4).

`FileDataSource` reads it; `CaptureWriter` writes it for `nettopo collect`. Both live here
because they are one format, and a reader and a writer kept apart drift.

Each file is one device's captured output: several `show` commands concatenated, each
preceded by its device prompt line (`hostname#show ...`). That prompt line is how a
device is identified as a **source device** (we have its own capture, not just a
neighbor mention).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from pathlib import Path

from nettopo.ingest.base import Capture, DataSource
from nettopo.utils.command_sections import first_prompt_hostname
from nettopo.utils.paths import safe_join

logger = logging.getLogger("nettopo")


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


class CaptureWriter:
    """Writes one file per collected device, named after the device's own hostname.

    Owns the naming, because naming needs state no single device has: two switches both
    still called `switch` would otherwise write over each other and silently destroy one
    of them. The writer keeps a hostname registry for the run and, the moment a second
    device claims a name, suffixes **both** files with their inventory target --
    `switch_10.0.0.11.txt` and `switch_10.0.0.12.txt`, leaving no bare `switch.txt`. That
    the first device arrived first is not a reason for it to keep the clean name, and the
    target is what the operator typed, so it is what lets the two be told apart.

    Files are written as each device finishes rather than at the end of the run: a
    collection stops at the first error, so a run that dies at device 40 of 50 must keep
    the 39 captures it already paid for.
    """

    def __init__(self, output_root: Path) -> None:
        # Resolved here rather than assumed: `safe_join` compares against `Path.parents`,
        # so an unresolved root (a symlinked temp directory, say) makes every write look
        # like an escape attempt.
        self.output_root = Path(output_root).expanduser().resolve()
        self._targets_by_hostname: dict[str, list[str]] = {}
        self._paths_by_target: dict[str, Path] = {}

    @property
    def paths_by_target(self) -> Mapping[str, Path]:
        """Where each device's capture ended up, after any duplicate rename."""
        return self._paths_by_target

    def duplicates_of(self, target: str) -> tuple[str, ...]:
        """The other targets that reported the same hostname as `target`, if any."""
        for targets in self._targets_by_hostname.values():
            if target in targets and len(targets) > 1:
                return tuple(other for other in targets if other != target)
        return ()

    def write(self, target: str, capture: Capture) -> Path:
        """Write `capture` and return its path, renaming an earlier file on a collision."""
        hostname = capture.device_hint
        targets = self._targets_by_hostname.setdefault(hostname, [])
        targets.append(target)

        if len(targets) == 1:
            return self._write(target, capture, f"{hostname}.txt")

        if len(targets) == 2:
            # The first device is still holding the bare name; take it away from it now
            # that the name is no longer unambiguous.
            self._rename_to_suffixed(hostname, targets[0])

        return self._write(target, capture, self._suffixed_name(hostname, target))

    def _write(self, target: str, capture: Capture, filename: str) -> Path:
        # The filename is derived from a device prompt, which is data the device controls.
        # `safe_join` is exactly the guard that case was written for.
        path = safe_join(self.output_root, filename)
        path.write_text(capture.raw_text, encoding="utf-8")
        self._paths_by_target[target] = path
        return path

    def _rename_to_suffixed(self, hostname: str, target: str) -> None:
        current = self._paths_by_target[target]
        renamed = safe_join(self.output_root, self._suffixed_name(hostname, target))
        current.rename(renamed)
        self._paths_by_target[target] = renamed

    @staticmethod
    def _suffixed_name(hostname: str, target: str) -> str:
        return f"{hostname}_{target}.txt"
