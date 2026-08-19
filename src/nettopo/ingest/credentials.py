"""Asks for the credentials one collection run uses (PROJECT_SPEC.md section 11).

Credentials are prompted for on the terminal, held in memory for the run, and never
written anywhere: no vault, no credential file, no cache. That is a deliberate scope
decision, and it is why an inventory needs no encryption.

They are also never accepted on the command line. There is no `--password` and no
`--enable-password` flag, because argv is readable by every user on the host through
`ps`.
"""

from __future__ import annotations

import getpass
import sys
from dataclasses import dataclass, field


class CredentialError(Exception):
    """Credentials could not be obtained -- there is no terminal to ask on."""


@dataclass(frozen=True)
class Credentials:
    """One run's credentials.

    The secrets are `repr=False` so that logging a `Credentials` -- or any object holding
    one -- at DEBUG cannot spill them. Zeroization is deliberately *not* claimed: a Python
    `str` cannot be reliably wiped, and saying otherwise would be worse than saying so.
    Keeping secrets out of `repr`, out of logs, out of argv and out of netmiko's
    `session_log` is the mitigation that is actually true.
    """

    username: str
    password: str = field(repr=False)
    enable_password: str | None = field(repr=False)


def prompt_credentials(*, username: str | None = None) -> Credentials:
    """Ask for the username, password and enable password this run will use.

    An empty enable password means the network does not use enable; devices that turn out
    to require it are then skipped rather than collected half-privileged (see
    `ingest/live.py`).
    """
    if not sys.stdin.isatty():
        raise CredentialError(
            "'collect' needs a terminal to ask for credentials, and stdin is not one. "
            "Run it interactively; nettopo deliberately accepts no password on the "
            "command line, because argv is readable by every user on the host."
        )

    resolved_username = username or _prompt_username()
    password = getpass.getpass(f"SSH password for {resolved_username}: ")
    enable_password = getpass.getpass("Enable password (leave empty if not used): ")

    return Credentials(
        username=resolved_username,
        password=password,
        enable_password=enable_password or None,
    )


def _prompt_username() -> str:
    """Ask for the username, offering the OS login as the default."""
    default_username = getpass.getuser()
    entered = input(f"SSH username [{default_username}]: ").strip()
    return entered or default_username
