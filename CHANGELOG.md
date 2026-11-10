# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Shared cases:** included submodule data nodes and typedefs (`tests/cases/modules/include`, `include-typedef`), and `augment` inside `uses` (`tests/cases/reuse/uses-augment`, `uses-augment-bad-target`). TypeScript now matches Python on these cases ([#55](https://github.com/exergy-connect/xYang/issues/55), [#62](https://github.com/exergy-connect/xYang/issues/62)).
- **One-call validate and machine-readable CLI:** `xyang.validate(schema, data, *, features=None, include_path=())` returns the `validate_detailed` dict (`schema` is a path or a parsed module). `xyang validate` accepts `--format text|json`, `--features` (`{"module": ["feature"]}` or `null`), and `-` for stdin. `--format json` prints `{"valid", "errors": [{path, code, message}]}` on stdout and warnings on stderr. Exit codes are 0 valid, 1 invalid, and 2 for usage or schema/parse errors ([#82](https://github.com/exergy-connect/xYang/issues/82)).
- **Discoverability:** `keywords` on the Python and TypeScript packages, agent notes in `AGENTS.md` (install, `parse` / `validate` / `convert`, validate examples, tests), and [`llms.txt`](llms.txt) ([#81](https://github.com/exergy-connect/xYang/issues/81)).
- **Native JSON format:** documented the intent of the native JSON form of YANG: reversible, unambiguous, and fast to load (`README.md`, `AGENTS.md`).
- **Structured validation errors (Python + TypeScript):** `YangValidator.validate_detailed` and `validateDetailed` return `{valid, errors, warnings}`. Each issue is `{code, path, message, expression?, severity}` and `path` is a JSON Pointer (list and leaf-list entries by position). `validate()` string output is unchanged. Shared case runners read codes and pointers from this API ([#79](https://github.com/exergy-connect/xYang/issues/79)).
- **Shared conformance cases:** language-neutral cases in `tests/cases/` (YANG modules, JSON instances, expected `(JSON Pointer, code)` errors) run by both `tests/test_cases.py` and `ts/test/cases.test.ts`; known Python/TypeScript divergences are recorded as per-implementation expected failures. A new CI workflow runs both runners on every change.
- **Python `YangValidator(module, enabled_features_by_module=...)`:** configure enabled features without dropping to `DocumentValidator`, matching TypeScript `enabledFeaturesByModule`.
- **QuickJS-ng executable:** `qjs/build.sh` builds the TypeScript CLI as a self-contained `xyang-ts` binary with QuickJS-ng 0.18.0 (static musl on Linux; macOS and Windows cross-compiled with Zig). A published GitHub Release builds all five binaries, smoke-tests the Linux ones against the Node CLI, and attaches them. Pull-request CI does not build the binaries.

### Changed

- **Tests:** removed per-language tests whose valid/invalid outcome is already covered by a shared case in `tests/cases/`. Bits (empty, duplicate token, non-string), bits-in-union, duplicate bit names, empty enumerations, and `if-feature` on a list moved into shared cases. TypeScript still accepts duplicate bit names; that case is an expected failure.
- **Breaking:** GitHub Action `xyang-ts` input `ref` is replaced by `version` (a release tag, default `latest`). The action downloads `xyang-ts.mjs` from GitHub Release assets instead of checking out a committed bundle. The `path` input and `xyang-root` output are removed (#89).
- CI no longer commits `artifacts/xyang-ts.mjs` or `docs/xyang.umd.min.js`. A published release builds them with `npm run build:ci` and attaches them; pull-request CI only runs that build as a check and does not push commits (#89).

### Fixed

- **XPath:** `+`, `-`, `*`, `div`, and `mod` are numeric operators (XPath 1.0). Python evaluates `*`, and both languages parse and evaluate `div` and `mod` (`mod` is a truncating remainder, the same as JavaScript `%`). `+` does not concatenate strings ([#48](https://github.com/exergy-connect/xYang/issues/48)).
- **TypeScript parse order:** uses expansion, then `augment`, then RFC 8791 extension indexing, and only when `expand_uses` is set — the same gate and order as Python ([#75](https://github.com/exergy-connect/xYang/issues/75)).
- **Python validation:** multi-part `range` and `length` restrictions keep every part. A value is accepted when it falls in at least one part, and an integer is still checked against its built-in minimum and maximum when a `range` is present (`range "1..3 | 10..max"` rejects `4` and `5`, and values above the type's maximum) ([#54](https://github.com/exergy-connect/xYang/issues/54)).
- **Validation (Python + TypeScript):** a `range`, `length`, or `pattern` on a `type` that names a typedef is applied after that typedef's own restrictions, so a derived typedef or a leaf can narrow a range ([#56](https://github.com/exergy-connect/xYang/issues/56)).
- **JSON Schema import:** `parse_json_schema` rejects a schema that has no root `x-yang` object, and a root property that has no `x-yang`, instead of returning an empty module named `unknown` ([#80](https://github.com/exergy-connect/xYang/issues/80)).
- **Python validation:** a present container must be a JSON object, a list or leaf-list must be a JSON array, and each list entry must be an object. Wrong shapes report `type` (`container must be an object`, `list must be an array`, `list item must be an object`, `leaf-list must be an array`) instead of being skipped or accepted as a one-element leaf-list ([#52](https://github.com/exergy-connect/xYang/issues/52)).
- **Python validation:** leaf type checks reject a JSON value of the wrong type instead of coercing it. A non-integral number or a boolean is not an integer (`Expected integer, got <json type>`), a boolean is not a decimal64, and a non-string is not a string (`Expected string, got <json type>`). Length and pattern are not applied to a non-string. Numeric strings for integer types are unchanged ([#51](https://github.com/exergy-connect/xYang/issues/51)).
- **XPath:** an unknown function name is a compile error (`xpath-unknown-function`) in Python and TypeScript. `contains()`, `substring-before()`, and `substring-after()` stay unimplemented (see #85).
- **TypeScript validation:** enforce `min-elements` / `max-elements` on present lists and leaf-lists, matching Python. Data that violates these bounds now fails validation.
- **TypeScript tests:** `npm test` runs the CLI from source, so a clean checkout no longer needs `npm run build` first. Node.js 24 is pinned in `.nvmrc` and `.node-version`; CI reads `.nvmrc` and also tests the latest LTS.
- **TypeScript CLI:** piped stdout is no longer truncated at Node's 64 KiB pipe buffer. `xyang-ts` flushes stdout and stderr before exiting, including large `convert` JSON Schemas.

## [0.1.11] — 2026-11-06

### Added

- **Feature inference (Python + TypeScript):** add `infer_required_features(module, instance)` and `inferRequiredFeatures(module, instance)` APIs returning a sorted, deduplicated list of module-qualified feature requirements from present instance elements, enclosing schema gates, and transitive prerequisites. Support feature atoms and positive `and` conjunctions; reject unknown members/features and unsupported expressions. Includes API documentation and tests.

## [0.1.10] — 2026-11-05

### Changed

- **TypeScript validation:** reject unknown fields at the document root and in all containers by default, matching existing list-item and Python validation. Choice/case nodes remain transparent, and `anydata`/`anyxml` payload contents remain opaque unless separately validated. Previously accepted data containing unknown fields now fails validation.

### Added

- **Browser ESM bundle:** public `@exergy-connect/xyang/browser` npm export with named exports, a source map, and an MIT license banner. The existing global IIFE bundle remains available.

## [0.1.9] — 2026-11-04

### Changed

- **TypeScript:** replace `tsup` with `tsdown` and build on TypeScript 7. No Python behavior changes; the PyPI version stays aligned with `@exergy-connect/xyang` **0.1.9**.

## [0.1.8] — 2026-11-04

### Changed

- **Packaging:** declare Python **3.15** support (PyPI classifiers, CI matrix, Black `py315` target).
- **Python:** minimum supported version is **3.11** (PyPI `requires-python`, classifiers, CI matrix 3.11–3.15, Black targets); **3.10 is no longer supported**. Binary values always use `base64.b64decode(..., validate=True)`.
- **CI:** `actions/checkout`, `actions/setup-python`, and `actions/setup-node` use major version **v7**.

## [0.1.7] — 2026-07-20

### Changed

- **Tokenizer (Python + TypeScript):** collapse single-char punctuation into a lookup map; simplify quoted-string escape advancement; TypeScript also replaces RegExp whitespace/digit/identifier checks with range helpers on the hot path.

### Fixed

- **Python tokenizer:** normalize RFC 7950 quoted-string concatenation while lexing quoted strings, including descriptions in imported modules, so individual statement parsers do not need concatenation handling.
- **TypeScript tokenizer:** same quoted-string concatenation normalization while lexing (parity with Python), including descriptions in imported modules.

## [0.1.6] — 2026-07-16

### Changed

- **Identifier-ref:** parse-time structured refs for ``identity`` ``base``, ``identityref`` ``base``, ``augment`` path segments, typedef ``type`` prefix, and ``uses`` grouping names; expanders/validators consume ``YangIdentifierRef`` / structured fields and do not re-split ``prefix:name`` strings (Python + TypeScript).

### Fixed

- **TypeScript `expandUses`:** resolve ``uses prefix:grouping`` via `import_prefixes` (Python `_resolve_uses_grouping` parity); keep groupings after expansion so importers can still reference them; nested `uses` inside an imported grouping resolve in the defining module's scope; register grouping typedefs onto the importing module; `typedef` under `grouping` is retained on the parent AST.

## [0.1.5] — 2026-07-16

### Fixed

- **TypeScript:** `TypeChecker` resolves imported `prefix:typedef` names via `import_prefixes` (e.g. `ntype:ipv4-prefix`), so non-string instance values no longer fail with `Unsupported type 'prefix:name'`.

## [0.1.4] — 2026-07-16

### Fixed

- **TypeScript:** `augment` statements are merged into target schema nodes when `expandUses` is true (parity with Python `apply_augmentations`), including same-module, cross-file `import`, choice/`case`, and list targets; `expandUses` preserves shared `import_prefixes` references so cross-module merges hit the parser cache.

## [0.1.3] — 2026-07-16

### Changed

- **Packaging:** project metadata and builds use **`pyproject.toml` only** (PEP 517/621); build requires `setuptools>=82` and `wheel>=0.47`; dev extras pin current minimums (`pytest>=9`, `black>=26.5.1`, `PyYAML>=6.0.3`); CI installs with `pip install -e ".[dev]"`.
- **Python:** minimum supported version is **3.10** (PyPI `requires-python`, classifiers, CI matrix 3.10–3.14, Black targets); **3.9 is no longer supported**.
- **Integer built-in yang.json:** use JSON Schema `minimum` / `maximum` (canonical RFC 7950 bounds) instead of `x-yang.builtin-type`; reverse mapping in `parse_json_schema` (`integer_bounds.py`, `tests/json/test_integer_builtin_bounds.py`).
- **XPath tokenizer:** normalize YANG-style `\"` / `\'` in must/when expressions before lexing; fix in-string escape handling.
- **Parser metadata:** `status` accepted on `grouping`, `uses`, `typedef`, and other nodes using `with_metadata_substatements` (consumed, not stored on AST).
- **Parser `grouping`:** nested `grouping` allowed inside `grouping` bodies.

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
- **GitHub Action `xyang-ts`:** reusable composite action under [`.github/actions/xyang-ts`](.github/actions/xyang-ts) with committed CI artifact `artifacts/xyang-ts.mjs`; documented in [README.md](README.md).
- **Examples:** OpenConfig netlink example under [`examples/`](examples/).

### Fixed

- **Integer bounds round-trip:** resolve YANG `min`/`max` range keywords when emitting JSON Schema; map `0..max` signed subranges and bare JSON integers back to the correct YANG built-in (`integer_bounds.py`); regenerate `examples/meta-model.yang.json` with per-leaf `minimum`/`maximum`.
- **Validator integer built-ins:** enforce RFC 7950 implicit `range` when the type has no explicit `range` (e.g. reject negative values for `uint32`); uses canonical bounds from `integer_bounds.py`.
- **Parser nested `typedef`:** `uses` expansion no longer treats typedefs as data nodes; `copy_yang_statement` supports `YangTypedefStmt` and RPC I/O nodes (`YangRpcStmt`, `YangInputStmt`, `YangOutputStmt`) for JSON generation / uses expansion.
- **JSON Schema generator:** leaf `default` values now use JSON literal types — `true` / `false` for `boolean`, numbers for integer built-ins (and numeric defaults on `union` typedefs such as `change-history-policy`) — instead of quoted strings. `parse_json_schema` round-trips these back to YANG default lexemes in the AST.
- **`uses` expansion:** deep-copy `YangAugmentStmt`; apply refines whose paths name a `case` (e.g. `target/stream/.../within-subscription`); merge `description` from refine onto targets.
- **`augment` expansion:** merge augmented `case` statements into `choice.cases` when the augment target is a choice.
- **Parser `identityref`:** `base` accepts prefixed QNames (`sn:foo`), not only local identifiers.

### Removed

- **`setup.py`** and **`requirements.txt`** (legacy setuptools entry point and unused requirements stub).

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

[Unreleased]: https://github.com/exergy-connect/xYang/compare/v0.1.9...HEAD
[0.1.9]: https://github.com/exergy-connect/xYang/compare/v0.1.8...v0.1.9
[0.1.8]: https://github.com/exergy-connect/xYang/compare/v0.1.7...v0.1.8
[0.1.7]: https://github.com/exergy-connect/xYang/compare/v0.1.6...v0.1.7
[0.1.6]: https://github.com/exergy-connect/xYang/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/exergy-connect/xYang/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/exergy-connect/xYang/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/exergy-connect/xYang/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/exergy-connect/xYang/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/exergy-connect/xYang/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/exergy-connect/xYang/releases/tag/v0.1.0
