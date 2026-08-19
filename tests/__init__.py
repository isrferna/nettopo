"""Marks `tests` as a package so `from tests.conftest import ...` resolves when CI
invokes bare `pytest`, which — unlike `python -m pytest` — does not put the working
directory on `sys.path`."""
