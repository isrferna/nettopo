"""Shared fixtures.

The `fake_netmiko` fixture is what lets the collector be tested at all: it replaces
netmiko's `ConnectHandler` with a scripted stand-in, so `tests/test_ingest_live*.py` run
without the optional extra installed and, more importantly, **without opening a socket**.
A collector test that needed a real device would never run in CI, which is the same as
not having one.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest

from nettopo.ingest import live

_PROMPT_HOSTNAME = re.compile(r"^(?P<hostname>[\w.\-]+)[#>]\s*$")


def ios_version(hostname: str = "sw1") -> str:
    """A `show version` that names the device, the way a real one does."""
    return f"""Cisco IOS Software, C2960X Software, Version 15.2(7)E3
{hostname} uptime is 1 week
cisco WS-C2960X-24TS-L (PowerPC405) processor
Processor board ID FOC2134X0DEF
"""


IOS_VERSION = ios_version()

NXOS_VERSION = """Cisco Nexus Operating System (NX-OS) Software
  system:    version 9.3(8)
  Device name: core-sw1
"""


@dataclass
class FakeConnection:
    """One scripted device.

    `outputs` maps a command to what the device answers; anything not listed answers
    `% Invalid input detected`, which is how a real device declines a command it does not
    support and what the collector must treat as a skipped section rather than a failure.
    """

    host: str
    outputs: dict[str, str]
    prompt: str = "sw1#"
    privileged: bool = True
    enable_error: Exception | None = None
    fail_with: Exception | None = None
    commands_sent: list[str] = field(default_factory=list)
    disconnected: bool = False

    def __post_init__(self) -> None:
        """Make `show version` agree with the prompt, as it does on a real device.

        Both come from the same configured hostname, so a fake whose prompt says one thing
        and whose `show version` says another would not be testing anything real -- and
        would quietly hide which of the two the collector actually keys identity on.
        """
        match = _PROMPT_HOSTNAME.match(self.prompt)
        # Only the generic default is rewritten; a test that scripted its own `show
        # version` (an NX-OS banner, say) means it.
        if match and self.outputs.get("show version") == IOS_VERSION:
            self.outputs["show version"] = ios_version(match.group("hostname"))

    def check_enable_mode(self) -> bool:
        return self.privileged

    def enable(self) -> None:
        if self.enable_error is not None:
            raise self.enable_error
        self.privileged = True

    def find_prompt(self) -> str:
        return self.prompt

    def send_command(self, command_string: str, *, read_timeout: float) -> str:
        self.commands_sent.append(command_string)
        if self.fail_with is not None:
            raise self.fail_with
        return self.outputs.get(command_string, "% Invalid input detected at '^' marker.")

    def disconnect(self) -> None:
        self.disconnected = True


@dataclass
class FakeNetmiko:
    """Stands in for `ConnectHandler`, handing out one `FakeConnection` per host.

    Records every connection attempt, so a test can assert on how many devices were
    *contacted* -- which is the only way to check that a run stopped early instead of
    ploughing on through the inventory.
    """

    devices: dict[str, FakeConnection] = field(default_factory=dict)
    connect_errors: dict[str, Exception] = field(default_factory=dict)
    attempts: list[str] = field(default_factory=list)
    default_outputs: dict[str, str] = field(default_factory=dict)

    def __call__(self, **params: Any) -> FakeConnection:
        host = str(params["host"])
        self.attempts.append(host)
        if host in self.connect_errors:
            raise self.connect_errors[host]
        return self.devices.setdefault(
            host, FakeConnection(host=host, outputs=dict(self.default_outputs))
        )


@pytest.fixture
def fake_netmiko(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeNetmiko]:
    handler = FakeNetmiko(default_outputs={"show version": IOS_VERSION})
    monkeypatch.setattr(live, "ConnectHandler", handler)
    yield handler
