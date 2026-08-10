"""nettopo — generate draw.io network diagrams from saved Cisco show-command captures."""

from importlib.metadata import PackageNotFoundError, version

# Read from the installed distribution rather than hardcoded here, so this string can
# never drift from `pyproject.toml` the way it silently did through v0.2.0.
try:
    __version__ = version("nettopo")
except PackageNotFoundError:  # a source tree that was never installed
    __version__ = "0.0.0+unknown"
