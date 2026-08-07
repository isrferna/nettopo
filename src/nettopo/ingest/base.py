"""DataSource interface (PROJECT_SPEC.md section 4).

`FileDataSource` (`ingest/files.py`) implements this over a directory of saved captures
in v1. A future live-collection source (netmiko/scrapli over SSH) can implement the same
interface without touching `parsing/`, `model/`, or `views/`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class Capture:
    device_hint: str  # best-effort device identity before `show version` is parsed
    raw_text: str  # the full, unparsed capture content
    platform_hint: str | None  # ntc-templates platform key, if the source already knows it


class DataSource(ABC):
    @abstractmethod
    def discover(self) -> Iterator[Capture]:
        """Yield one `Capture` per source device."""
