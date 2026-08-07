"""Extracts one `show` command's output from a multi-command capture file.

Each capture file concatenates several `show` command outputs, each preceded by its
device prompt line (`hostname#show ...`, PROJECT_SPEC.md section 4). Parsers need just
the output belonging to *their* command, not the whole file, so this module finds the
prompt line whose command matches a given pattern and returns everything up to the next
prompt line (or end of file).
"""

from __future__ import annotations

import re

_PROMPT_LINE = re.compile(r"^(?P<hostname>\S+)[#>]\s*(?P<command>.+?)\s*$", re.MULTILINE)


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
