"""Reads and writes the multi-command capture file format.

Each capture file concatenates several `show` command outputs, each preceded by its
device prompt line (`hostname#show ...`, PROJECT_SPEC.md section 4). Parsers need just
the output belonging to *their* command, not the whole file, so this module finds the
prompt line whose command matches a given pattern and returns everything up to the next
prompt line (or end of file).

`format_command_section` is the inverse, for a live collector that has to synthesize the
format rather than read it. Both directions live here on purpose: they are one format,
and a reader and writer kept in separate modules drift.
"""

from __future__ import annotations

import re

_PROMPT_LINE = re.compile(r"^(?P<hostname>\S+)[#>]\s*(?P<command>.+?)\s*$", re.MULTILINE)

# Privileged mode, which is what a collector's session is in and what the fixtures use.
_PROMPT_TERMINATOR = "#"
_WHITESPACE = re.compile(r"\s")


def extract_command_output(raw_text: str, command_pattern: re.Pattern[str]) -> str | None:
    """Return the output following the first prompt line whose command matches.

    `command_pattern` is matched (via `.match`, not `.search`) against the command text
    of each prompt line. Returns None if no prompt line matches.
    """
    matches = list(_PROMPT_LINE.finditer(raw_text))
    for index, match in enumerate(matches):
        if command_pattern.match(match.group("command")):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(raw_text)
            return raw_text[start:end].strip("\n")
    return None


def first_prompt_hostname(raw_text: str) -> str | None:
    """Return the hostname from the first device prompt line, if any."""
    match = _PROMPT_LINE.search(raw_text)
    return match.group("hostname") if match else None


def format_command_section(hostname: str, command: str, output: str) -> str:
    """Render one command's output in the shape `extract_command_output` reads back.

    A live collector has to synthesize the device prompt line itself: netmiko's
    `send_command` strips the echoed command and the trailing prompt from its output by
    default, so neither survives to be reused.

    A hostname containing whitespace would not match `_PROMPT_LINE`'s `\\S+`, which would
    silently make this section and every one after it unreadable. That is refused here
    rather than discovered later as an unexplained empty diagram.
    """
    if not hostname or _WHITESPACE.search(hostname):
        raise ValueError(f"prompt hostname must be a single non-empty token: {hostname!r}")

    body = output.replace("\r\n", "\n").strip("\n")
    return f"{hostname}{_PROMPT_TERMINATOR}{command}\n{body}\n\n"
