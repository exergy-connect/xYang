# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **String `pattern` (RFC 7950):** multiple `pattern` substatements, `modifier invert-match`, and per-pattern `error-message` / `error-app-tag` in the Python and TypeScript parsers and validators. JSON Schema emission uses `allOf` / `not` when needed and adds **`x-yang.string-patterns`** for full round-trip via `parse_json_schema` / TS equivalent.
- **TypeScript** implementation in [`ts/`](ts/): publishable npm package **`@xyang/ts`** (parser, validator, RFC 7951 encoding helpers, XPath, CLI `xyang-ts`), Vitest suite, and GitHub Actions workflows for tests and npm publish.

### Changed

- Documentation: removed the top-level "Working with types" usage example from [README.md](README.md) to reflect the current package surface.
- Parser: moved YANG keyword definitions to [`src/xyang/parser/keywords.py`](src/xyang/parser/keywords.py) and now treat keyword lexemes as `IDENTIFIER` tokens, with statement parsing driven by keyword-value matching.

### Fixed

- Parser: preserve prefixed QName steps in `refine` target paths (for example `refine rd:flag`) by parsing targets as `PathNode` with `XPathParser.parse_path()`.

### Removed

- Public API: stopped re-exporting `resolve_qualified_top_level` from `xyang` package root; import it from `xyang.encoding` instead.
- Public API: stopped re-exporting `TypeConstraint` and `TypeSystem` from `xyang` package root.

## [0.1.1] — 2026-04-19

### Added

- Optional **anydata subtree validation** (draft [yang-anydata-validation](https://datatracker.ietf.org/doc/html/draft-ietf-netmod-yang-anydata-validation)): validator extension, CLI flags, and [`examples/anydata_validation_usage.py`](examples/anydata_validation_usage.py). Details in [FEATURES.md](FEATURES.md).
- ``xyang.ext`` hooks for extension definitions and prefixed invocations (see [FEATURES.md](FEATURES.md)).

### Changed

- **Parser:** Reorganized for clearer **extension** support (prefixed extension bodies and related statements); statement logic split across smaller modules. **Breaking:** ``YangParser.registry`` was removed—use ``YangParser.parsers`` if you need the statement parser facade. Syntax errors for invalid statements **inside extension blocks** may use different messages or context than before.

### Fixed

- Parser and `uses` expansion: **`default` inside `refine`** (RFC 7950 §7.13.2) for **`leaf`** and **`leaf-list`** targets — fixes [#7](https://github.com/exergy-connect/xYang/issues/7). Refined defaults flow into JSON Schema **`default`** (array for leaf-list) and round-trip via `parse_json_schema`.

## [0.1.0] — 2026-04-08

First published release (`xyang` **0.1.0** on PyPI).

### Added

- Pure-Python YANG **1.1-shaped** parser and validator (subset documented in [FEATURES.md](FEATURES.md)).
- **RFC 7950** built-in types and validation rules on instance data (including `union`, `leafref`, `identityref`, `instance-identifier`, `bits`, `binary`, etc.).
- Structural support: `module` / `submodule`, `grouping` / `uses` / `refine`, `augment`, `choice` / `case`, `must`, `when`, `if-feature`, and related constraints.
- **`xyang`** CLI: `parse`, `validate`, `convert` (YANG → **YANG.json** hybrid).
- JSON Schema **2020-12** export with **`x-yang`** metadata where supported.
- **Zero** required runtime dependencies; optional **PyYAML** for `.yaml` / `.yml` instance validation.

[Unreleased]: https://github.com/exergy-connect/xYang/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/exergy-connect/xYang/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/exergy-connect/xYang/releases/tag/v0.1.0
