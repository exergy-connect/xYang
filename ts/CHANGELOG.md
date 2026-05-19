# Changelog — `@xyang/ts`

All notable changes to the TypeScript implementation in [`ts/`](.) are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this package adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

For the Python `xyang` package, see the repository root [CHANGELOG.md](../CHANGELOG.md).

## [Unreleased]

### Added

- **CLI `--anydata-validation` / `--anydata-module`:** `xyang-ts validate` supports `off` | `complete` | `candidate` and repeatable `--anydata-module` paths (parity with Python `xyang validate`); loads the host import closure plus extra modules, enables `ValidatorExtension.ANYDATA_VALIDATION`, and unwraps a single RFC 7951 qualified top-level key (`module:node` → `{ node: … }`). See `src/cli/args.ts`, `src/cli/load-anydata-modules.ts`, `test/cli-validate-args.test.ts`, `test/cli-validate-anydata.test.ts`.
- **`notification` parsing:** RFC 7950 §7.16 at module level and under `container`, `list`, `grouping`, and `augment` (`YangNotificationStmt`, `notification.ts`); removed from unsupported-skip.
- **CLI `--include-path`:** repeatable directory search for imported modules on `parse`, `validate`, and `convert` (same semantics as `parseYangFile(..., { includePath })` / `YangParser({ include_path })`).
- **Parser `reference`:** `reference` substatement on schema nodes (`YangStatement.reference`, `parse_reference`); revision bodies already stored `reference` on `module.revisions[]`.
- **Parser typedef `default`:** RFC 7950 §7.3 default values on typedefs (`YangTypedefStmt.default`, dedicated typedef body dispatch).
- **String concatenation:** `+` between quoted strings for `pattern`, `length`, `range`, and leafref `path` (`parse_string_concatenation`, `parse_string_argument`).
- **Implicit `choice` cases:** data nodes placed directly under `choice` become implicit `case` nodes (RFC 7950 §7.9.2).
- **XPath `parseXPathPath()`:** leafref paths parsed as paths only; multiple predicates on one step merge with `and` (leafref-style paths).
- **`metadata-substatements` helpers:** `withMetadataSubstatements` / `withDataNodeSubstatements` for shared `description`, `reference`, `config`, and `status` handlers.
- **Tests:** `test/parser_parity.test.ts` covering the above (typedef default, pattern concat, implicit choice, config storage, syntax error format, multi-predicate paths, include-path imports, leaf `reference`); `test/config.test.ts` for JSON Schema `x-yang.config`.

### Changed

- **`augment` body parsing:** uses the same data-node substatement dispatch as Python (`choice` / `case`, `uses`, `notification`, `must`, `when`, prefixed extensions, etc.) instead of generic `parseStatement` (which rejected `case` under `augment`).
- **`config` substatement (RFC 7950 §7.21.1):** stored on data definition AST nodes and in JSON Schema `x-yang.config`; refine `config` applied on uses expansion.
- **JSON Schema defaults:** leaf `default` values emit as JSON literals (boolean/integer) and round-trip back to YANG string form (`default-values.ts`, Python parity).
- **Leafref / JSON:** `type` `path` and JSON-schema leafref validation use `parseXPathPath()` instead of the full XPath expression parser.
- **Module `typedefs` map:** includes `default` and `reference` when present on parsed typedefs.

### Fixed

- **`status` substatement (RFC 7950 §7.21.2):** consumed without storing on the AST in typedef and other metadata contexts (e.g. `ietf-interfaces` `interface-state-ref`); avoids parse failures on standard IETF modules.
- **`YangUsesStmt.augmentations`:** augment statements under `uses` attach to the uses node (parity with Python).
- **`parse_config`:** narrow `current_parent` with `typeof … === "object"` before `"config" in parent` (TypeScript TS2638).
- **RFC 7950 quoted strings:** tokenizer decodes `\\`, `\"`, `\'`, `\n`, `\t`, and line continuation so double-quoted patterns (e.g. `ietf-yang-types` `date-and-time`) match RFC 3339 timestamps (`yang-strings.ts`, `test/yang-string-unescape.test.ts`).
- **`YangSyntaxError`:** `String(error)` / `toString()` returns `filename:line: message` when location is known (parity with Python).
- **Choice parsing:** inline `leaf` / `container` / … under `choice` no longer fall through to generic (invalid) statement handling.

## [0.1.0] — 2026-05-17

Initial publishable **`@xyang/ts`** package (`xyang-ts` CLI).

### Added

- YANG **1.1-shaped** parser and validator (subset; see root [FEATURES.md](../FEATURES.md)).
- **RFC 7950** built-in types and instance validation (including `union`, `leafref`, `identityref`, `instance-identifier`, `bits`, `binary`, etc.).
- Structural support: `module`, `grouping` / `uses` / `refine`, `augment`, `choice` / `case`, `must`, `when`, `if-feature`, and related constraints.
- **`xyang-ts`** CLI: `parse`, `validate`, `convert` (YANG → JSON Schema hybrid).
- JSON Schema export and **`parseJsonSchema`** round-trip where supported.
- XPath tokenizer, parser, and evaluator used by `must`, `when`, and leafref paths.
- Browser bundle (`dist/index.umd.min.global.js`) and Vitest suite under `test/`.

[Unreleased]: https://github.com/exergy-connect/xYang/compare/v0.1.1...HEAD
[0.1.0]: https://github.com/exergy-connect/xYang/tree/v0.1.1/ts
