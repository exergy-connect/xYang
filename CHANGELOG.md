# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Integer built-in yang.json:** use JSON Schema `minimum` / `maximum` (canonical RFC 7950 bounds) instead of `x-yang.builtin-type`; reverse mapping in `parse_json_schema` (`integer_bounds.py`, `tests/json/test_integer_builtin_bounds.py`).

### Added

- **Parser `units`:** RFC 7950 `units` on `typedef` and `type` (stored on the AST, emitted in JSON Schema `x-yang.units`, round-trip via `parse_json_schema`).
- **Parser `notification`:** `YangNotificationStmt` at module/submodule level and under `container`, `list`, `grouping`, and `augment` (RFC 7950 YANG 1.1); `tests/test_notification_under_list.py`.
- **Parser `rpc` / `input` / `output`:** module-level `rpc` with `input` and `output` blocks parsed into `YangRpcStmt`, `YangInputStmt`, and `YangOutputStmt` (data definitions inside I/O blocks).
- **JSON Schema `rpc`:** module-level RPCs emitted under root `x-yang.rpcs` (per-RPC `input` / `output` as JSON Schema objects); round-trip via `parse_json_schema` (`tests/json/test_rpc_json.py`). Integer built-ins round-trip via JSON Schema `minimum` / `maximum` (canonical bounds per type).
- **`augment` on `uses`:** RFC 7950 §7.17 — `augment` substatements under `uses` are parsed and merged when groupings expand.
- **CLI `validate`:** `--anydata-validation complete|candidate` auto-loads `*.yang` from `--include-path` and the host module directory (no mandatory `--anydata-module` list); RFC 8791 `structure` roots supported for anydata instance checks.
- **Tests:** units, anydata CLI, uses+augment, XPath escaped quotes in must/when, refine on choice/case paths, grouping `status`/nested grouping, prefixed `identityref` base, augment `case` into choice, `rpc` input/output parse (`tests/test_rpc_input_output.py`), `rpc` yang.json round-trip (`tests/json/test_rpc_json.py`).
- **TypeScript `rpc` / `input` / `output`:** parser parity with Python (`ts/src/parser/statements/rpc.ts`, `ts/test/rpc_input_output.test.ts`); JSON Schema `x-yang.rpcs` round-trip (`ts/test/json/rpc_json.test.ts`); `rpc` removed from unsupported-skip; container bodies reject `rpc` via explicit substatement dispatch.
- **Parser nested `typedef`:** RFC 7950 / YANG 1.1 `typedef` inside `container`, `list`, `choice`, `case`, `grouping`, `notification`, and `rpc` `input`/`output` (e.g. `ietf-notification-capabilities`); registered on `module.typedefs` for leaf type resolution.
- **Tests:** nested typedef parse and validation (`tests/test_typedef_in_container.py`).
- **Parser `config`:** RFC 7950 §7.21.1 `config true` / `config false` stored on data nodes (`config: Optional[bool]` on `YangStatementWithWhen`, `refined_config` on `refine`); echoed in JSON Schema `x-yang.config`; tests in `tests/test_config.py`.
- **Cross-module `augment` + RFC 7951:** CLI anydata module map uses one `YangParser` cache and import closure registration so augments merge into shared targets; augmented nodes carry `defining_module` and validate under `module:identifier` JSON keys (`tests/test_anydata_augment_merge.py`).
- **RFC 7950 quoted strings:** decode `\\`, `\"`, `\'`, `\\n`, `\\t`, and line continuation in the tokenizer so double-quoted patterns (e.g. `ietf-yang-types` `date-and-time`) compile as intended (`tests/test_yang_string_unescape.py`).

### Changed

- **XPath tokenizer:** normalize YANG-style `\"` / `\'` in must/when expressions before lexing; fix in-string escape handling.
- **Parser metadata:** `status` accepted on `grouping`, `uses`, `typedef`, and other nodes using `with_metadata_substatements` (consumed, not stored on AST).
- **Parser `grouping`:** nested `grouping` allowed inside `grouping` bodies.

### Fixed

- **Validator integer built-ins:** enforce RFC 7950 implicit `range` when the type has no explicit `range` (e.g. reject negative values for `uint32`); uses canonical bounds from `integer_bounds.py`.
- **Parser nested `typedef`:** `uses` expansion no longer treats typedefs as data nodes; `copy_yang_statement` supports `YangTypedefStmt` and RPC I/O nodes (`YangRpcStmt`, `YangInputStmt`, `YangOutputStmt`) for JSON generation / uses expansion.
- **JSON Schema generator:** leaf `default` values now use JSON literal types — `true` / `false` for `boolean`, numbers for integer built-ins (and numeric defaults on `union` typedefs such as `change-history-policy`) — instead of quoted strings. `parse_json_schema` round-trips these back to YANG default lexemes in the AST.
- **`uses` expansion:** deep-copy `YangAugmentStmt`; apply refines whose paths name a `case` (e.g. `target/stream/.../within-subscription`); merge `description` from refine onto targets.
- **`augment` expansion:** merge augmented `case` statements into `choice.cases` when the augment target is a choice.
- **Parser `identityref`:** `base` accepts prefixed QNames (`sn:foo`), not only local identifiers.

## [0.1.2] — 2026-05-17

### Added

- **CLI `--include-path`:** repeatable directory search path for imported modules on `parse`, `validate`, and `convert` (same semantics as `parse_yang_file(..., include_path=...)` / `YangParser(include_path=...)`).
- **Parser `revision`:** `reference` substatement in braced revision bodies (RFC 7950); value stored on `module.revisions[]` alongside `date` and `description`.
- **`TokenStream.make_error()`:** public helper for syntax errors at the current token (replaces direct use of `_make_error` in statement parsers).
- **Examples:** IETF alarm model under [`examples/ietf/`](examples/ietf/) (`ietf-alarms@2019-09-11`, dependency `ietf-yang-types`).
- **Tests:** CLI include-path coverage (`tests/test_cli_include_path.py`) and revision `reference` parsing (`tests/test_revision_reference.py`).
- **Parser:** `reference` on typedefs and other schema nodes; `default` in typedef bodies; `+` string concatenation for `pattern`, `length`, `range`, and leafref `path`; implicit `case` for data nodes placed directly under `choice` (RFC 7950 §7.9.2).
- **XPath:** leafref paths use `parse_path()` with step predicates (including multiple `[...]` on one step); `current()` and related expressions in predicates.
- **String `pattern` (RFC 7950):** multiple `pattern` substatements, `modifier invert-match`, and per-pattern `error-message` / `error-app-tag` in the Python and TypeScript parsers and validators. JSON Schema emission uses `allOf` / `not` when needed and adds **`x-yang.string-patterns`** for full round-trip via `parse_json_schema` / TS equivalent.
- **TypeScript** implementation in [`ts/`](ts/): publishable npm package **`@exergy-connect/xyang`** (parser, validator, RFC 7951 encoding helpers, XPath, CLI `xyang-ts`), Vitest suite, and GitHub Actions workflows for tests and npm publish.

### Changed

- **Packaging:** declare Python **3.14** support (PyPI classifiers, CI matrix, Black `py314` target); bump dev optional dependency `black` to `>=26.5.0`.
- **CLI:** `validate` / `convert` / `parse` share include-path handling; `validate` applies the same paths when loading `--anydata-module` files. Exception handling uses explicit expected error types instead of bare `Exception`.
- **TypeScript:** revision parser accepts `reference` in braced revision bodies (parity with Python).
- Documentation: removed the top-level "Working with types" usage example from [README.md](README.md) to reflect the current package surface.
- Parser: moved YANG keyword definitions to [`src/xyang/parser/keywords.py`](src/xyang/parser/keywords.py) and now treat keyword lexemes as `IDENTIFIER` tokens, with statement parsing driven by keyword-value matching.
- Tests: `test_enum_validation` asserts invalid enum values are rejected (removed obsolete skip and duplicate `pytest` import); `test_choice_case_invalid_primitive_value` now requires a validation failure for invalid typedef enumeration values.

### Fixed

- **`YangSyntaxError`:** `str(error)` includes `filename:line:` when location is known (CLI and tests).
- Validator (`type_checker`): `enumeration` validation fails closed when the resolved type has no enum labels in the AST, instead of accepting arbitrary values.
- Validator (`type_checker`): `instance-identifier` path parsing catches `XPathSyntaxError` only (not bare `Exception`), and uses an explicit `PathNode` binding after parse so type checkers recognize `is_absolute` safely.
- Parser: preserve prefixed QName steps in `refine` target paths (for example `refine rd:flag`) by parsing targets as `PathNode` with `XPathParser.parse_path()`.
- Parser: reject list keys that reference missing child leaves, or key leaves with `when` / `if-feature` substatements (RFC 7950).

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

[Unreleased]: https://github.com/exergy-connect/xYang/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/exergy-connect/xYang/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/exergy-connect/xYang/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/exergy-connect/xYang/releases/tag/v0.1.0
