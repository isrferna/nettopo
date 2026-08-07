# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Phase 1 foundations: the interface-name normalizer (`utils/interfaces.py`,
  PROJECT_SPEC.md section 5), the normalized data model dataclasses and enums
  (`model/entities.py`, section 6), and the STP/HSRP grouping fingerprint functions
  for `per-vlan`/`strict`/`topology` group modes (`model/grouping.py`, section 6).
  Nothing user-visible yet — the CLI still reports "not implemented yet".
- Phase 0 scaffolding: repository layout under `src/nettopo/` matching
  `PROJECT_SPEC.md` section 3, an empty CLI skeleton (`nettopo --help` and all
  subcommands parse but report "not implemented yet"), `pyproject.toml`, and a
  GitHub Actions pipeline running `ruff check`, `ruff format --check`, `mypy`,
  and `pytest --cov` on every push and pull request.
- `CLAUDE.md` engineering conventions, `docs/architecture.md`, and this changelog.

## [0.0.1] - 2026-08-06

- Initial repository scaffolding. No packaged release yet.
