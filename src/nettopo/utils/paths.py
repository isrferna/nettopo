"""Path and filename safety helpers (PROJECT_SPEC.md section 11, path handling).

Some output filenames are derived from data parsed out of device captures (hostnames,
VLAN ids) rather than from trusted user input. A device whose hostname is
attacker-influenced (e.g. `../../etc`) must not be able to make a derived filename
escape the resolved output directory.
"""

from __future__ import annotations

import re
from pathlib import Path

_UNSAFE_CHARS = re.compile(r"[\\/:*?\"<>|\s]+")

# Where captures live by default: `collect` writes here and every other command reads
# here, so the two halves of the workflow line up without the user naming a path twice.
DEFAULT_CAPTURE_DIR = "~/configs"

# The collection report goes to the directory the command was run from, not to the capture
# directory: it is a record of that run, not part of the capture set.
DEFAULT_REPORT_NAME = "nettopo-collect-report.csv"


def sanitize_filename_component(value: str, *, fallback: str = "unknown") -> str:
    """Reduce `value` to characters safe for use as a single path segment.

    Strips path separators, quotes, and whitespace, then trims leading/trailing dots so
    the result can never resolve to `.` or `..`. Returns `fallback` if nothing safe
    remains.
    """
    stripped = _UNSAFE_CHARS.sub("_", value).strip("._")
    return stripped or fallback


def resolve_input_root(input_dir: str | Path) -> Path:
    """Resolve an input directory to an absolute path, without creating it.

    Only a shell expands a tilde it actually sees, and argparse hands over its default
    verbatim -- so `DEFAULT_CAPTURE_DIR` has to be expanded here or it resolves to a
    relative directory literally named `~`.
    """
    return Path(input_dir).expanduser().resolve()


def resolve_output_root(output_dir: str | Path) -> Path:
    """Resolve `output_dir` to an absolute path and ensure it exists."""
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_join(root: Path, *components: str) -> Path:
    """Join sanitized `components` onto `root`, refusing to escape it."""
    path = root
    for component in components:
        path = path / sanitize_filename_component(component)
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"refusing to write outside output root: {resolved}")
    return resolved
