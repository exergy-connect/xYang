# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

### Changed

### Fixed

## [0.1.0] — 2026-04-08

First published release (`xyang` **0.1.0** on PyPI).

### Added

- Pure-Python YANG **1.1-shaped** parser and validator (subset documented in [FEATURES.md](FEATURES.md)).
- **RFC 7950** built-in types and validation rules on instance data (including `union`, `leafref`, `identityref`, `instance-identifier`, `bits`, `binary`, etc.).
- Structural support: `module` / `submodule`, `grouping` / `uses` / `refine`, `augment`, `choice` / `case`, `must`, `when`, `if-feature`, and related constraints.
- **`xyang`** CLI: `parse`, `validate`, `convert` (YANG → **YANG.json** hybrid).
- JSON Schema **2020-12** export with **`x-yang`** metadata where supported.
- **Zero** required runtime dependencies; optional **PyYAML** for `.yaml` / `.yml` instance validation.

[Unreleased]: https://github.com/exergy-connect/xYang/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/exergy-connect/xYang/releases/tag/v0.1.0
