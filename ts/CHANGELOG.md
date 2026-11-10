# Changelog — `@exergy-connect/xyang`

All notable changes to the TypeScript implementation in [`ts/`](.) are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this package adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

For the Python `xyang` package, see the repository root [CHANGELOG.md](../CHANGELOG.md).

## [Unreleased]

### Fixed

- **XPath:** `+`, `-`, `*`, `div`, and `mod` are numeric operators (XPath 1.0). `div` and `mod` parse and evaluate, matching Python (`mod` is a truncating remainder). `+` does not concatenate strings ([#48](https://github.com/exergy-connect/xYang/issues/48)).
- **Include:** `include` loads the submodule and merges its data nodes, typedefs, identities, groupings, and features into the parent module. `belongs-to`, duplicate names, and circular includes are rejected ([#55](https://github.com/exergy-connect/xYang/issues/55)).
- **`augment` inside `uses`:** augment substatements are kept on the `uses` node and applied to the expanded grouping before `refine`, so a refine can target a node the augment added. `uses` of the module's own prefix resolves locally. Notification bodies validate like containers, and augmented nodes accept their RFC 7951 `module:name` member ([#62](https://github.com/exergy-connect/xYang/issues/62)).
- **Post-parse order:** uses expansion, then `augment`, then RFC 8791 extension indexing, and only when `expand_uses` is set. `sx:structure` indexing sees the expanded tree; with `expand_uses: false` the structure index is absent ([#75](https://github.com/exergy-connect/xYang/issues/75)).
- **Validation:** a `range`, `length`, or `pattern` on a `type` that names a typedef is applied after that typedef's own restrictions, so a derived typedef or a leaf can narrow a range. Multi-part `range` and `length` values were already enforced ([#54](https://github.com/exergy-connect/xYang/issues/54), [#56](https://github.com/exergy-connect/xYang/issues/56)).
- **JSON Schema import:** `parseJsonSchema` rejects a schema that has no root `x-yang` object, and a root property that has no `x-yang`, instead of returning a module with an empty name and no statements ([#80](https://github.com/exergy-connect/xYang/issues/80)).
- **XPath:** an unknown function name is a compile error (`xpath-unknown-function`), matching Python. `contains()`, `substring-before()`, and `substring-after()` stay unimplemented (see #85).
- **Validation:** enforce `min-elements` / `max-elements` on present lists and leaf-lists, matching Python (same error wording). Data that violates these bounds now fails validation.
- **Tests:** `npm test` runs the CLI from source, so a clean checkout no longer needs `npm run build` first.
- **CLI:** piped stdout and stderr are flushed before exit. `process.exit()` immediately after a large `write` was dropping everything past Node's 64 KiB pipe buffer, so `convert` of a realistic module was truncated when stdout was a pipe.

### Added

- **One-call validate and machine-readable CLI:** `validate(schema, data, { features, includePath })` returns the `validateDetailed` object (`schema` is a path or a parsed module). `xyang-ts validate` accepts `--format text|json`, `--features` (`{"module": ["feature"]}` or `null`), and `-` for stdin. `--format json` prints `{"valid", "errors": [{path, code, message}]}` on stdout and warnings on stderr. Exit codes are 0 valid, 1 invalid, and 2 for usage or schema/parse errors ([#82](https://github.com/exergy-connect/xYang/issues/82)).
- **Package metadata:** `keywords` on `@exergy-connect/xyang` ([#81](https://github.com/exergy-connect/xYang/issues/81)).
- **Structured validation errors:** `YangValidator.validateDetailed` returns `{valid, errors, warnings}`. Each issue is `{code, path, message, expression?, severity}` and `path` is a JSON Pointer. `validate()` string output is unchanged ([#79](https://github.com/exergy-connect/xYang/issues/79)).
- **Shared conformance cases:** `test/cases.test.ts` runs the language-neutral cases in [`tests/cases/`](../tests/cases/README.md).

### Changed

- **Breaking:** GitHub Action `xyang-ts` input `ref` is replaced by `version` (a release tag, default `latest`). The action downloads the `xyang-ts.mjs` release asset instead of a committed bundle. The `path` input and `xyang-root` output are removed (#89).
- `artifacts/xyang-ts.mjs` and `docs/xyang.umd.min.js` are no longer committed. `npm run build:ci` still writes them locally; a published release attaches them (#89).

## [0.1.11] — 2026-11-06

### Added

- Export `inferRequiredFeatures(module, instance)` to infer a sorted, deduplicated list of module-qualified feature requirements from present instance elements, enclosing schema gates, and transitive prerequisites. Supports feature atoms and positive `and` conjunctions; rejects unknown members/features and unsupported expressions. Includes API documentation and tests.

## [0.1.10] — 2026-11-05

### Changed

- TypeScript validation rejects unknown fields at the document root and in all containers by default, matching the existing list-item and Python behavior. Choice/case nodes remain transparent; anydata/anyxml payload contents remain opaque unless separately validated.

### Added

- Public `@exergy-connect/xyang/browser` export: a self-contained browser ESM bundle with named exports, source map, and MIT license banner. The existing global IIFE remains available.

## [0.1.9] — 2026-11-04

### Changed

- **Build:** replace `tsup` with `tsdown` for the library, CLI, and declaration bundles (`tsdown.config.ts`). The browser IIFE is still built with esbuild.
- **TypeScript 7:** move the dev dependency from 6.x to 7.x and drop `ignoreDeprecations`. Declaration emit now goes through tsdown, which works with TypeScript 7.

## [0.1.8] — 2026-11-04

### Changed

- Version aligned with Python `xyang` **0.1.8**. No TypeScript behavior changes.

## [0.1.7] — 2026-07-20

### Changed

- **Tokenizer:** replace RegExp whitespace/digit/identifier checks with range helpers; emit single-char punctuation via a `Map` lookup instead of an if/else chain (`tokenizer.ts`).

### Fixed

- **Tokenizer:** normalize RFC 7950 quoted-string concatenation while lexing quoted strings, including descriptions in imported modules (`tokenizer.ts`, `imported_string_concatenation.test.ts`).

## [0.1.6] — 2026-07-16

### Changed

- **Identifier-refs at parse time:** `type`, `identity`/`base`, `identityref`/`base`, `uses`, and absolute `augment` paths store structured `{ prefix?, name }` refs (and `augment_path_segments`) instead of opaque `prefix:name` strings. Expanders and validators resolve those fields directly; `parseIdentifierRefAtom` is reserved for opaque boundaries (JSON Schema, RFC 7951 instance values, if-feature tokens). JSON Schema `x-yang.bases` still emits formatted strings for round-trip compatibility (`identifier-ref.ts`, parsers, `identity-graph.ts`, `augment-expand.ts`, `if-feature-eval.ts`, `json/*`).

### Added

- **Imported grouping expansion:** `expandUses` resolves `prefix:grouping` via `import_prefixes` (parity with Python); groupings retained after expand (`uses-expand.ts`, `imported_grouping.test.ts`).

## [0.1.5] — 2026-07-16

### Fixed

- **Imported typedef validation:** `TypeChecker` resolves `prefix:typedef` names via `import_prefixes` (e.g. `ntype:ipv4-prefix`), so non-string values no longer fail with `Unsupported type 'prefix:name'` (`type-checker.ts`, `imported_typedef.test.ts`).

## [0.1.4] — 2026-07-16

### Fixed

- **`augment` expansion:** when `expandUses` is true, merge `augment` children into target schema nodes (parity with Python `apply_augmentations`), including same-module, cross-file `import`, choice/`case`, and list targets; preserve shared `import_prefixes` across `expandUses` cloning so cross-module merges hit the parser cache (`augment-expand.ts`, `augment.test.ts`).

## [0.1.3] — 2026-07-16

### Changed

- **Dev dependencies:** bump `@types/node`, `esbuild`, and `vitest` to current releases; keep `typescript` on `^6.0.3` because `tsup` 8.5.1's bundled `rollup-plugin-dts` breaks `.d.ts` generation on TypeScript 7 ([tsup#1405](https://github.com/egoist/tsup/issues/1405)).
- **Integer built-in yang.json:** emit canonical JSON Schema `minimum` / `maximum` instead of `x-yang.builtin-type`; `parseJsonSchema` infers the YANG type from bounds (`integer-bounds.ts`, `tests/json/integer_builtin_bounds.test.ts`).
- **Unsupported-skip:** `rpc` and nested `input` / `output` under `rpc` are parsed; only top-level stray `input` / `output` and `action` remain skipped (`test/unsupported_skip.test.ts` updated).

### Fixed

- **Validator integer built-ins:** `TypeSystem` enforces RFC 7950 bounds for all int/uint built-ins (e.g. reject negative `uint32`); union members no longer accept arbitrary numbers via unknown-type fallback (`types.ts`).
- **Integer bounds round-trip:** resolve `min`/`max` when emitting bounds; infer `int32 { range "0..max"; }` and unconstrained `integer` correctly when parsing (`integer-bounds.ts`).
- **JSON default values:** coerce numeric leaf defaults on `$ref` typedefs to YANG string lexemes (`default-values.ts`).

### Added

- **Parser `rpc` / `input` / `output`:** module-level `rpc` with I/O blocks (`YangRpcStmt`, `YangInputStmt`, `YangOutputStmt` in `src/core/ast.ts`; `src/parser/statements/rpc.ts`); tests in `test/rpc_input_output.test.ts`.
- **Container substatement dispatch:** explicit data-node dispatch (parity with Python); `rpc` inside `container` is rejected.
- **JSON Schema `rpc`:** module-level RPCs under `x-yang.rpcs` with `input` / `output` blocks; round-trip via `parseJsonSchema` (`test/json/rpc_json.test.ts`). Integer built-ins round-trip via JSON Schema `minimum` / `maximum`.
- **GitHub Action `xyang-ts`:** reusable composite action and committed single-file CI artifact (`artifacts/xyang-ts.mjs`) for workflow consumers.

## [0.1.2] — 2026-05-19

First npm publish as **`@exergy-connect/xyang`** (renamed from `@xyang/ts`).

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

- **npm package name:** `@xyang/ts` → **`@exergy-connect/xyang`** (scope matches the GitHub org; install with `npm install @exergy-connect/xyang`).
- **`augment` body parsing:** uses the same data-node substatement dispatch as Python (`choice` / `case`, `uses`, `notification`, `must`, `when`, prefixed extensions, etc.) instead of generic `parseStatement` (which rejected `case` under `augment`).
- **`config` substatement (RFC 7950 §7.21.1):** stored on data definition AST nodes and in JSON Schema `x-yang.config`; refine `config` applied on uses expansion.
- **JSON Schema defaults:** leaf `default` values emit as JSON literals (boolean/integer) and round-trip back to YANG string form (`default-values.ts`, Python parity).
- **Leafref / JSON:** `type` `path` and JSON-schema leafref validation use `parseXPathPath()` instead of the full XPath expression parser.
- **Module `typedefs` map:** includes `default` and `reference` when present on parsed typedefs.

### Fixed

- **`status` substatement (RFC 7950 §7.21.2):** consumed without storing on the AST in typedef and other metadata contexts (e.g. `ietf-interfaces` `interface-state-ref`); avoids parse failures on standard IETF modules.
- **`YangUsesStmt.augmentations`:** augment statements under `uses` attach to the uses node (parity with Python).
- **`uses` expansion:** apply `refine` `description` onto expanded targets (parity with Python).
- **`parse_config`:** narrow `current_parent` with `typeof … === "object"` before `"config" in parent` (TypeScript TS2638).
- **RFC 7950 quoted strings:** tokenizer decodes `\\`, `\"`, `\'`, `\n`, `\t`, and line continuation so double-quoted patterns (e.g. `ietf-yang-types` `date-and-time`) match RFC 3339 timestamps (`yang-strings.ts`, `test/yang-string-unescape.test.ts`).
- **`YangSyntaxError`:** `String(error)` / `toString()` returns `filename:line: message` when location is known (parity with Python).
- **Choice parsing:** inline `leaf` / `container` / … under `choice` no longer fall through to generic (invalid) statement handling.

## [0.1.0] — 2026-05-17

Initial TypeScript implementation (`xyang-ts` CLI); not published to npm under this version.

### Added

- YANG **1.1-shaped** parser and validator (subset; see root [FEATURES.md](../FEATURES.md)).
- **RFC 7950** built-in types and instance validation (including `union`, `leafref`, `identityref`, `instance-identifier`, `bits`, `binary`, etc.).
- Structural support: `module`, `grouping` / `uses` / `refine`, `augment`, `choice` / `case`, `must`, `when`, `if-feature`, and related constraints.
- **`xyang-ts`** CLI: `parse`, `validate`, `convert` (YANG → JSON Schema hybrid).
- JSON Schema export and **`parseJsonSchema`** round-trip where supported.
- XPath tokenizer, parser, and evaluator used by `must`, `when`, and leafref paths.
- Browser bundle (`dist/index.umd.min.global.js`) and Vitest suite under `test/`.

[Unreleased]: https://github.com/exergy-connect/xYang/compare/v0.1.9...HEAD
[0.1.9]: https://github.com/exergy-connect/xYang/compare/v0.1.8...v0.1.9
[0.1.8]: https://github.com/exergy-connect/xYang/compare/v0.1.7...v0.1.8
[0.1.7]: https://github.com/exergy-connect/xYang/compare/v0.1.6...v0.1.7
[0.1.6]: https://github.com/exergy-connect/xYang/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/exergy-connect/xYang/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/exergy-connect/xYang/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/exergy-connect/xYang/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/exergy-connect/xYang/compare/v0.1.1...v0.1.2
[0.1.0]: https://github.com/exergy-connect/xYang/tree/v0.1.0/ts
