# Code audit, November 2026

This audit of `main` covers three things: duplicate code inside a single implementation, unused code, and deprecated APIs. It checks Python (`src/xyang`), TypeScript (`ts/src`) and Zig (`zig/src`). Logic that Python, TypeScript and Zig each implement once is intended parity, so it is not reported as duplication. This document reports findings only. It changes no production code.

## Counts

| Category | Python | TypeScript | Zig | Total |
|---|---:|---:|---:|---:|
| Duplicate code | 8 | 9 | 11 | 28 |
| Unused code | 36 | 36 | 6 | 78 |
| Deprecated APIs | 31 | 6 | 12 | 49 |
| **Total** | **75** | **51** | **29** | **155** |

Each row in the tables below counts as one finding. A deprecated-API row covers one import line (Python) or one deprecated std symbol together with all of its call sites (Zig).

## Method

| Tool | Version | Command |
|---|---|---|
| vulture | 2.16 | `vulture src/xyang --min-confidence 60` |
| ruff | 0.17.5 | `ruff check src/xyang --target-version py311 --select F401,F811,F841,UP,ARG,B` (`requires-python = ">=3.11"`) |
| tsc | 7.0 | `npx tsc --noEmit --noUnusedLocals --noUnusedParameters -p ts` |
| knip | 5.x | `npx knip` in `ts/` |
| zig | 0.17.1 (`minimum_zig_version`) | `zig build`, `zig build test`, `zig build wasm`: all clean, no warnings |
| jscpd | 4.3.0 | `jscpd <dir> --min-lines 5 --min-tokens 50`, run once per implementation directory |
| rg | | Reference counts for every Zig `fn` and top-level `const`. Every `/// Deprecated` declaration in the 0.17.1 `lib/std` was matched against `zig/` |

Every tool hit was checked by hand: references were searched across `src/`, `tests/`, `benchmarks/`, `ts/{src,test,scripts,bench}` and `zig/`. Hits that turned out to be used are listed under [Excluded false positives](#excluded-false-positives). Code reached only from tests is treated as used.

---

## 1. Duplicate code

### Python (`src/xyang`): 8

| Location | Description | Action |
|---|---|---|
| `src/xyang/xpath/functions.py:192-215` and `:223-246` | `derived-from()` and `derived-from-or-self()` share the same 24-line body. Only the final predicate differs (`is_derived_from_strict_qnames` vs `is_derived_from_or_self_qnames`). | Merge into one `_derived_from(ev, ast, ctx, node, predicate)` helper. |
| `src/xyang/validator/type_checker.py:165-178` and `:201-214` | The `resolve_typedef` → `_check_typedef_reference(...)` call, with ten arguments, appears twice: once on the prefixed path and once on the local path. | Hoist into one `_check_resolved_typedef(...)` helper. |
| `src/xyang/validator/type_checker.py:527-537` and `:554-564` | The range check (`_numeric_range_issue` with `range_error_message`/`range_error_app_tag`) is copied between `_check_integer` and `_check_decimal`. | Extract `_type_range_issue(n, type_stmt)`. |
| `src/xyang/validator/type_checker.py:487-495` and `:619-627` | The pattern / `invert-match` loop is copied for string and binary values. Only the message prefix differs. | Merge into `_pattern_issues(s, patterns, label)`. |
| `src/xyang/validator/type_checker.py:686-694` and `:708-716` | `_numeric_range_issue` and `_length_issue` both open with the same `_range_miss(_parse_ranges(...))` and unpacking. | Have `_length_issue` call a shared `_range_bound_miss(n, text)`, or fold both into one method. |
| `src/xyang/parser/statement_parsers.py:634-641` and `src/xyang/parser/statements/deviation.py:125-132` | `unique` argument parsing (strip prefixes, split paths, raise "unique requires at least one descendant path") is written twice. | Extract a `parse_unique_paths(tokens)` helper on `StatementParsers` and call it from `deviation.py`. |
| `src/xyang/xpath/functions.py:85-91` and `:96-102` | `substring-before()` and `substring-after()` share the arity check, argument coercion and `find`. | Optional: shared `_split_on_needle(...)` helper. |
| `src/xyang/parser/keywords.py:58-75` | 17 type-name constants (`BINARY`…`UNION`) redefine the values already in `src/xyang/types/registry.py:28-43`. `INT64` on line 55 is already imported from there. | Import them from `types.registry`, as `INT64` is. |

### TypeScript (`ts/src`): 9

| Location | Description | Action |
|---|---|---|
| `ts/src/types.ts:8-25` and `:27-45` | The `TypeConstraintInput` field list is copied field-for-field into `class TypeConstraint`. | Declare `interface TypeConstraint extends TypeConstraintInput {}` (declaration merging) and drop the duplicated fields. |
| `ts/src/types.ts:344-358` and `:359-374` | The decimal `range` and `fraction-digits` checks are written twice: once for string input and once for numeric input. | Extract `decimalIssues(n, text, c)`. |
| `ts/src/encoding/instance.ts:254-260` and `:264-271` | `resolveName` filters on a `module:name` key in two places: native and RFC 7951 at the root. | Extract `byQualifiedName(key, children, parent)`. |
| `ts/src/xpath/parser.ts:22-30` and `:330-338` | The trailing-`eof` check and its `XPathSyntaxError` are copied. | Extract `expectEof()`. |
| `ts/src/xpath/evaluator.ts:119-124` and `:137-142` | `compareLt` and `compareGt` are identical except for the operator (`compareLe`/`compareGe` follow the same pattern). | Merge into `compareOrdered(left, right, op)`. |
| `ts/src/xpath/evaluator.ts:185-192` and `:284-291` | `stepWildcard` and `stepNode` both expand list/leaf-list arrays into entry nodes. | Extract `expandEntries(node)`. |
| `ts/src/xpath/evaluator.ts:530-560` | `contains`, `starts-with`, `substring-before` and `substring-after` each repeat the arity check and the two `asXPathString` calls. | Optional: `stringPair(fn, args, context, node)` helper. |
| `ts/src/transform/augment-expand.ts:548-553` and `ts/src/transform/uses-expand.ts:171-176` | The code that pushes a `when` onto expanded children is copied. The augment copy deep-clones with `JSON.parse(JSON.stringify(...))`, the uses copy with `deepClone`. | Move into one shared helper that uses `deepClone`. |
| `ts/src/parser/keywords.ts:13-33` | 17 type-name constants redefine `ts/src/types/registry.ts:15-30`. `INT64` on line 25 is already re-exported from there. | Re-export them from `../types/registry`, as `INT64` is. |

### Zig (`zig/src`): 11

| Location | Description | Action |
|---|---|---|
| `zig/src/encoding/instance.zig:231-239` and `:247-256` | The `module:name` child lookup is written twice in one resolver (same as the TS `resolveName` finding). | Extract `byQualifiedName`. |
| `zig/src/validator/type_checker.zig:269-276` and `:344-351` | The pattern / `invert_match` loop is copied for string and binary values. | Merge into `patternIssues(s, patterns, label)`. |
| `zig/src/parser/statement_parsers.zig:85-91` and `:94-100` | The mapping from `xpath.Failure` to a parser error is copied between `compile` and `compilePath`. | Extract `xpathFailure(p, &failure, err)`. |
| `zig/src/schema_dump.zig:35-38`, `zig/src/parser/dispatch_registry.zig:190-193`, `zig/src/conformance.zig:182-185`, `zig/src/conformance.zig:232-235` | The anonymous `struct { fn lt(...) }` string comparator for `std.mem.sort` is defined four times. | Add one `sortStrings(items)` helper (or a shared `stringLessThan`). |
| `zig/src/json_value.zig:367-373` and `:418-424` | `writeJsonToken` and `dumpAt` repeat the same scalar cases (`null`, `bool`, `int`, `float` with NaN/Infinity). | Extract `writeScalar(w, v)`. |
| `zig/src/validator/document_validator.zig:149-154` and `:160-165` | `validate` and `validateStructure` share the same state reset and root setup. Only the root ref differs. | Extract `reset()` / `run(root_ref)`. |
| `zig/src/validator/document_validator.zig:206-211` and `zig/src/validator/yang_validator.zig:111-115` | The loop that turns `instance.encodingErrors` into `ValidationError`s is copied. | Add `instance.appendEncodingErrors(out, nodes)` or a validator helper. |
| `zig/src/xpath/functions.zig:129-158` | `fContains`, `fStartsWith`, `fSubstringBefore` and `fSubstringAfter` each repeat the arity check and the two `asString` calls. | Optional: `stringPair(ev, call, ctx, node)` helper. |
| `zig/src/encoding/instance.zig:369-374` and `:386-391` | The `boolean` text coercion is copied in two branches. | Extract `boolFromText`. |
| `zig/src/types/registry.zig:369-374` and `:387-393` | The `x-yang` `range` emission block is copied between the integer and decimal64 emitters. | Optional: small `putRange(xy, t)` helper. |
| `zig/src/parser/keywords.zig:49-52` | `BITS`, `ENUMERATION`, `IDENTITYREF` and `UNION` redefine `zig/src/types/registry.zig:33-38`. | Alias them from `types/registry.zig`. |

---

## 2. Unused code

### Python (`src/xyang`): 36

**Files (1)**

| Location | Description | Action |
|---|---|---|
| `src/xyang/parser/metadata_substatements.py` | Nothing imports the module. `with_metadata_substatements` is called only by `with_data_node_substatements`, which is itself never called. The TS twin `ts/src/parser/metadata-substatements.ts` is unused too. | Remove. |

**Functions, methods and classes (17)**

| Location | Description | Action |
|---|---|---|
| `src/xyang/ast.py:70`, `:113`, `:549`, `:579`, `:607` | Five `child_names` overrides. Nothing calls `child_names` in Python. TS calls it from `ast.ts:100`. | Remove, or wire into `validate_case_unique_child_names` for parity with TS. |
| `src/xyang/ast.py:202-203`, `:211-212` | The `range_description`, `range_reference`, `length_description` and `length_reference` properties are never read or written. Callers use `range_restriction.description` and similar. | Remove. |
| `src/xyang/ast.py:467` | `YangLeafrefStmt` dataclass is never instantiated. The TS twin `ts/src/core/ast.ts:549` is unused too. | Remove. |
| `src/xyang/identity_graph.py:70` | `resolve_identity_qname` has no caller. Callers use `resolve_identity_qname_pair`. | Remove. |
| `src/xyang/identity_graph.py:208` | `is_derived_from_or_self` has no caller. XPath uses `is_derived_from_or_self_qnames`. | Remove. |
| `src/xyang/module.py:115` | `YangModule.get_identity` has no caller. | Remove. |
| `src/xyang/parser/parser_context.py:124` | `TokenStream.consume_if` has no caller. | Remove. |
| `src/xyang/parser/parser_context.py:173` | `TokenStream.consume_oneof` has no caller. | Remove. |
| `src/xyang/parser/statement_parsers.py:140` | `substatement_handler` has no caller. | Remove. |
| `src/xyang/parser/statement_parsers.py:405` | `consume_qname_from_identifier` has no caller. | Remove. |
| `src/xyang/parser/statement_parsers.py:497` | `parse_reference_string_only` has no caller. | Remove. |
| `src/xyang/parser/statement_parsers.py:896` | `_apply_refine` has no caller. It wraps `refine_expand.apply_refine_to_node`. | Remove. |
| `src/xyang/parser/statements/uses.py:89` | `_expand_uses_with_statements` has no caller. Its `module` argument is also unused (ruff ARG002, line 93). | Remove. |
| `src/xyang/refine_expand.py:103` | `apply_refines_list_cardinality` has no caller. | Remove. |
| `src/xyang/types/registry.py:930` | `integer_bounds_for` has no caller. Callers read `YANG_INTEGER_BOUNDS` directly. | Remove. |
| `src/xyang/validator/document_validator.py:1148` | `_entry_key` has no caller. Callers use `_entry_key_from_names`. | Remove. |
| `src/xyang/xpath/ast.py:106` | `ast_is_const_false` has no caller. | Remove. |

**Constants, attributes and locals (5)**

| Location | Description | Action |
|---|---|---|
| `src/xyang/json/schema_keys.py:41` | `JsonSchemaKey.DATA_MODEL` is never read. | Remove. |
| `src/xyang/parser/keywords.py:70` | `STRING_KW` is never read. Python uses `registry.STRING`. | Remove (see the keywords duplicate finding). |
| `src/xyang/xpath/tokenizer.py:49` | `XPathTokenizer.KEYWORDS` is never read. | Remove. |
| `src/xyang/types/__init__.py:29` | `TypeSystem._pattern_cache` is assigned and never read. | Remove. |
| `src/xyang/types/__init__.py:198` | Local `float_val` in `_validate_decimal64` is assigned and never used (ruff F841). | Remove, or replace with a bare `float(value)` if the call is meant only as a check. |

**Imports (11)**: ruff F401, each checked by hand

| Location | Description | Action |
|---|---|---|
| `src/xyang/__main__.py:409` | `YangModule` | Remove. |
| `src/xyang/identity_graph.py:11` | `format_identifier_ref` | Remove. |
| `src/xyang/json/generator.py:36` | `YangRefineStmt` | Remove. |
| `src/xyang/parser/keywords.py:55` | `INT64` is imported and not re-exported or used by anything that imports `keywords`. | Remove, or keep it as the pattern for the keywords dedup. |
| `src/xyang/parser/parser_context.py:17` | `YangStatement` (`TYPE_CHECKING`) | Remove. |
| `src/xyang/parser/statement_parsers.py:71` | `YangModule` (`TYPE_CHECKING`) | Remove. |
| `src/xyang/parser/statements/bits.py:9` | `typing.Optional` | Remove. |
| `src/xyang/parser/statements/refine.py:17` | `PathNode` | Remove. |
| `src/xyang/uses_expand.py:7` | `typing.cast` | Remove. |
| `src/xyang/xpath/functions.py:10` | `typing.Optional` | Remove. |
| `src/xyang/xpath/functions.py:17` | `YangModule` (`TYPE_CHECKING`) | Remove. |

**Parameters (2)**

| Location | Description | Action |
|---|---|---|
| `src/xyang/validator/document_validator.py:512` | The `data` parameter of `_mandatory_choice_violation` is unused. | Remove the parameter. |
| `src/xyang/validator/document_validator.py:527` | The `data` parameter of `_leaf_mandatory_must_exist` is unused. | Remove the parameter. |

### TypeScript (`ts/src`, `ts/test`): 36

**Files (2)**

| Location | Description | Action |
|---|---|---|
| `ts/src/parser/metadata-substatements.ts` | Nothing imports it (knip). | Remove. |
| `ts/src/transform/refine-expand.ts` | Nothing imports it. `applyRefines` is a no-op that returns its argument. | Remove. |

**Dead declarations (10)**: no reference anywhere

| Location | Description | Action |
|---|---|---|
| `ts/src/ext/capabilities.ts:10` | `registerCapability` | Remove, along with the `capabilities` map if nothing else uses it. |
| `ts/src/ext/capabilities.ts:14` | `getCapability` | Remove. |
| `ts/src/parser/tokenizer.ts:199` | `tokenizeYang` | Remove. |
| `ts/src/parser/unsupported-skip.ts:62` | `skip_config_substatement` | Remove. |
| `ts/src/xpath/evaluator.ts:656` | `evaluateXPath` | Remove. |
| `ts/src/core/ast.ts:549` | `class YangLeafrefStmt` | Remove (the Python twin is unused too). |
| `ts/src/parser/parser-context.ts:160` | `LITERAL_TYPES` (tsc TS6133) | Remove. |
| `ts/src/validator/document-validator.ts:95` | `codeForMessage` (TS6133), with `MESSAGE_CODES` above it | Remove both. |
| `ts/src/validator/document-validator.ts:236` | Private `validateWithContext` (TS6133) | Remove. |
| `ts/src/parser/statements/submodule.ts:24` | Constructor property `module_parser` is never read (TS6138). | Remove the property and its constructor argument. |

**Imports and parameters in `src` (4)**

| Location | Description | Action |
|---|---|---|
| `ts/src/parser/statement-parsers.ts:9` | `YangNotificationStmt` import (TS6133) | Remove. |
| `ts/src/validator/yang-validator.ts:4` | `remapPointer` import (TS6133) | Remove. |
| `ts/src/xpath/parser.ts:2` | `XPathBinaryNode` and `XPathLiteralNode` imports (TS6133) | Remove. |
| `ts/src/validator/document-validator.ts:1261` | The `stmt` parameter of `runAnydataSubtreeValidation` is unused (TS6133). | Remove the parameter. |

**Test helpers and imports (3)**

| Location | Description | Action |
|---|---|---|
| `ts/test/if_feature.test.ts:13` | `YangValidator` import | Remove. |
| `ts/test/notification-under-list.test.ts:1` | `readFileSync` import | Remove. |
| `ts/test/parser_parity.test.ts:1` | `vi` import | Remove. |

**Exports used only inside their own file (16)**: knip unused exports, each confirmed by rg

| Location | Description | Action |
|---|---|---|
| `ts/src/core/ast.ts:104` | `YangStatementWithMust` | Drop `export`. |
| `ts/src/core/ast.ts:500` | `YangParsedXPathBase` | Drop `export`. |
| `ts/src/core/errors.ts:1` | `YangError` is the base of the four public error classes but is not exported from `src/index.ts`. | Export from `src/index.ts` so that `instanceof YangError` works for consumers, or drop `export`. |
| `ts/src/identity-graph.ts:26` | `resolvePrefixedModuleData` | Drop `export`. |
| `ts/src/identity-graph.ts:35` | `resolveIdentityQnamePair` | Drop `export`. |
| `ts/src/json/type-constants.ts:9` | `JSON_TYPE_NULL` | Drop `export`. |
| `ts/src/parser/dispatch-registry.ts:11` | `DATA_DEF_SUBSTATEMENTS`. `METADATA_SUBSTATEMENTS` and `DATA_NODE_SUBSTATEMENTS` (`:9-10`) join this group once `metadata-substatements.ts` is removed. | Drop `export`. |
| `ts/src/parser/keywords.ts:85-87` | `ADD`, `DELETE`, `REPLACE` | Drop `export`. |
| `ts/src/parser/unsupported-skip.ts:4` | `UNSUPPORTED_CONSTRUCT_TYPES` | Drop `export`. |
| `ts/src/parser/unsupported-skip.ts:6` | `_consume_balanced_braces` | Drop `export`. |
| `ts/src/transform/augment-expand.ts:104` | `resolveAugmentTarget` | Drop `export`. |
| `ts/src/transform/augment-expand.ts:175` | `resolveAbsoluteSchemaPath` | Drop `export`. |
| `ts/src/types.ts:106` | `integerLike` | Drop `export`. |
| `ts/src/validator/if-feature-eval.ts:91` | `featureIsSupported` | Drop `export`. |
| `ts/src/validator/operation.ts:17` | `DIRECTIONS` | Drop `export`. |
| `ts/test/meta-model/fixtures.ts:9` | `metaModelYangPath` | Drop `export`. |

**Redundant re-exports (1)**

| Location | Description | Action |
|---|---|---|
| `ts/src/ext/index.ts` | The re-exports of `AnydataValidationMode` and `parseAnydataExtensionConfig` are never imported. Callers import from `./ext/anydata_validation` directly. | Remove the re-exports. |

knip found no unused `dependencies` or `devDependencies` in `ts/package.json`.

### Zig (`zig/src`): 6

`zig build` analyzes only reachable code, so it cannot flag unused functions. Every `fn` (900) and top-level `const` was counted with rg. These six have a definition and no other reference in `zig/` or `build.zig`:

| Location | Description | Action |
|---|---|---|
| `zig/src/parser/token_stream.zig:69` | `TokenStream.consumeIf` | Remove (the Python twin is unused too). |
| `zig/src/parser/token_stream.zig:97` | `TokenStream.consumeOneOf` | Remove (the Python twin is unused too). |
| `zig/src/parser/statement_parsers.zig:223` | `Parser.consumeQName` | Remove. |
| `zig/src/json/generator.zig:602` | Private `isContainerLike` | Remove. |
| `zig/src/xpath/utils.zig:148` | `isNodeset` | Remove. |
| `zig/src/json_value.zig:121` | `Val.isNull` | Remove. |

---

## 3. Deprecated APIs

### Python: 31

`typing` aliases were deprecated by PEP 585 (since 3.9), and `requires-python` is `>=3.11` (ruff UP035). Every hit is one import line:

| Location | Deprecated imports | Action |
|---|---|---|
| `src/xyang/__main__.py:11` | `Dict`, `typing.Iterable` | Replace with `dict` / `collections.abc.Iterable`. |
| `src/xyang/ast.py:7` | `Dict`, `List`, `typing.Callable` | Replace with `dict`, `list` / `collections.abc.Callable`. |
| `src/xyang/augment_expand.py:12` | `Dict`, `List`, `typing.Callable` | Same. |
| `src/xyang/encoding/instance.py:12` | `typing.Iterator` | `collections.abc.Iterator`. |
| `src/xyang/encoding/rfc7951.py:10` | `Dict`, `Tuple`, `typing.Mapping` | `dict`, `tuple` / `collections.abc.Mapping`. |
| `src/xyang/ext/anydata_validation/__init__.py:12` | `Dict`, `Tuple` | `dict`, `tuple`. |
| `src/xyang/ext/capabilities.py:6` | `Dict` | `dict`. |
| `src/xyang/identity_graph.py:7` | `List`, `Set`, `Tuple` | `list`, `set`, `tuple`. |
| `src/xyang/module.py:7` | `Dict`, `List`, `Set` | `dict`, `list`, `set`. |
| `src/xyang/parser/dispatch_registry.py:18` | `typing.Mapping` | `collections.abc.Mapping`. |
| `src/xyang/parser/metadata_substatements.py:10` | `typing.Callable` | Moot once the file is removed. |
| `src/xyang/parser/parser_context.py:10` | `List`, `Tuple` | `list`, `tuple`. |
| `src/xyang/parser/statement_parsers.py:13` | `typing.Callable` | `collections.abc.Callable`. |
| `src/xyang/parser/tokenizer.py:10` | `List` | `list`. |
| `src/xyang/parser/yang_parser.py:11` | `Tuple` | `tuple`. |
| `src/xyang/refine_expand.py:7` | `typing.Callable` | `collections.abc.Callable`. |
| `src/xyang/types/__init__.py:6` | `Dict`, `List`, `typing.Callable` | `dict`, `list` / `collections.abc.Callable`. |
| `src/xyang/types/registry.py:15` | `typing.Callable`, `typing.Mapping` | `collections.abc`. |
| `src/xyang/validator/document_validator.py:30` | `AbstractSet`, `Dict`, `List`, `Tuple` | `collections.abc.Set`, `dict`, `list`, `tuple`. |
| `src/xyang/validator/if_feature_eval.py:9` | `AbstractSet`, `Dict`, `List`, `Set`, `typing.Mapping` | `collections.abc.Set`/`Mapping`, builtins. |
| `src/xyang/validator/path_builder.py:5` | `List` | `list`. |
| `src/xyang/validator/type_checker.py:13` | `List` | `list`. |
| `src/xyang/validator/yang_validator.py:5` | `AbstractSet`, `Dict`, `List`, `Tuple` | `collections.abc.Set`, builtins. |
| `src/xyang/xpath/ast.py:9` | `List` | `list`. |
| `src/xyang/xpath/evaluator.py:13` | `List`, `typing.Callable` | `list` / `collections.abc.Callable`. |
| `src/xyang/xpath/functions.py:10` | `List` | `list`. |
| `src/xyang/xpath/parser.py:8` | `List`, `Tuple`, `typing.Callable` | `list`, `tuple` / `collections.abc.Callable`. |
| `src/xyang/xpath/schema_nav.py:9` | `List` | `list`. |
| `src/xyang/xpath/tokenizer.py:5` | `List`, `Set` | `list`, `set`. |
| `src/xyang/xpath/utils.py:5` | `List` | `list`. |
| `src/xyang/xsd_regex.py:20` | `Dict`, `List`, `Tuple` | `dict`, `list`, `tuple`. |

`ruff check --select UP035,UP006 --fix` handles all of these mechanically. No deprecated stdlib calls were found: rg found no `utcnow`, `pkg_resources`, `distutils`, `get_event_loop`, `imp`, `locale.getdefaultlocale`, or `ast.Str`/`ast.Num`. Nothing in Python is marked deprecated by the repo itself.

### TypeScript: 6

rg found no deprecated Node or JS APIs (`new Buffer`, `url.parse`, `fs.exists`, `util.is*`, `substr`, `__proto__`, `escape`/`unescape`, `trimLeft`/`trimRight`). The `escape()` hits in `ts/src/xsd-regex.ts` are a private method name. All six findings are APIs the repo marks deprecated itself (`/** @deprecated */` plus `warnDeprecatedOnce`). These aliases shipped in 1.0.0. The warning says they "will be removed in the next release", and 1.0.1 and 1.0.2 have shipped since.

| Location | Description | Action |
|---|---|---|
| `ts/src/core/ast.ts:27-30` | `YangStatementList.find_statement` | Remove the alias, replaced by `findStatement`, and remove its cases in `ts/test/deprecated_aliases.test.ts`. |
| `ts/src/core/ast.ts:37-40` | `YangStatementList.get_all_leaves` | Remove the alias, replaced by `getAllLeaves`. |
| `ts/src/validator/yang-validator.ts:78-80` | `YangValidator.enable_extension` | Remove the alias, replaced by `enableExtension`. |
| `ts/src/parser/yang-parser.ts:19`, `:113` | `YangParser` option `expand_uses` | Remove the option, replaced by `expandUses`. |
| `ts/src/parser/yang-parser.ts:21`, `:116` | `YangParser` option `include_path` | Remove the option, replaced by `includePath`. |
| `ts/test/cases.test.ts:37`, `:54` | The shared conformance case runner still passes the deprecated `include_path` / `expand_uses` options, so every run prints the deprecation warning. | Replace with `includePath` / `expandUses`. |

### Zig: 12

All twelve are deprecated in Zig 0.17.1, which is the `minimum_zig_version`. They compile today because the std aliases are still present, and each replacement exists in 0.17.1.

| Symbol (std comment) | Uses | Locations | Action |
|---|---:|---|---|
| `std.fmt.allocPrint` ("Deprecated in favor of `Allocator.print`") | 220 in 25 files | First use `zig/src/xpath/utils.zig:179`. Heaviest in `conformance.zig` (29), `validator/document_validator.zig` (36), `json/parser.zig` (30) | Replace with `allocator.print(fmt, args)`. |
| `std.fmt.bufPrint` ("in favor of `mem.print`") | 16 in 5 files | `xsd_regex.zig:284`, `pyfmt.zig:78-82`, `parser/yang_parser.zig:489`, `errors.zig:58,61`, `json_value.zig:82,492-503` | Replace with `std.mem.print`. |
| `std.AutoArrayHashMapUnmanaged` ("use `array_hash_map.Auto`") | 3 in 2 files | `json/generator.zig:579,1467`, `augment_expand.zig:257` | Replace with `std.array_hash_map.Auto`. |
| `std.StringArrayHashMapUnmanaged` ("use `array_hash_map.String`") | 35 in 11 files | First use `conformance.zig:138`. Most in `module.zig:23-48` | Replace with `std.array_hash_map.String`. |
| `std.mem.indexOf` ("in favor of `find`") | 22 in 8 files | `build.zig:14`, `xpath/functions.zig:133,148,157`, `cli/commands.zig:371-378`, … | Replace with `std.mem.find`. |
| `std.mem.indexOfAny` ("in favor of `findAny`") | 2 | `encoding/instance.zig:42`, `json_value.zig:31` | Replace with `std.mem.findAny`. |
| `std.mem.indexOfPos` ("in favor of `findPos`") | 1 | `parser/tokenizer.zig:105` | Replace with `std.mem.findPos`. |
| `std.mem.indexOfScalar` ("in favor of `findScalar`") | 49 in 25 files | First use `build.zig:16` | Replace with `std.mem.findScalar`. |
| `std.mem.indexOfScalarPos` ("in favor of `findScalarPos`") | 5 in 4 files | `xsd_regex.zig:184,246`, `cli/args.zig:82`, `parser/tokenizer.zig:112`, `parser/yang_strings.zig:16` | Replace with `std.mem.findScalarPos`. |
| `std.mem.lastIndexOfScalar` ("in favor of `findScalarLast`") | 3 | `validator/operation.zig:153`, `json/parser.zig:984`, `cli/commands.zig:626` | Replace with `std.mem.findScalarLast`. |
| `std.unicode.utf8Decode` ("awkward API that is too easy to use incorrectly") | 6 in 5 files | `xpath/pychars.zig:70,78`, `xpath/tokenizer.zig:61`, `validator/operation.zig:129`, `pyfmt.zig:41`, `parser/yang_parser.zig:448` | Replace with `std.unicode.Utf8View` / `Utf8Iterator`, or the decode functions for a known length. |
| `std.fs.path` ("use `std.Io.Dir.path`") | 24 in 4 files | `conformance.zig:176-366`, `json/generator.zig:1712`, `cli/commands.zig:561-666`, `parser/yang_parser.zig:100-562` | Replace with `std.Io.Dir.path`. |

Every location in this table is relative to `zig/src/`, except `build.zig`, which is relative to `zig/`.

---

## Excluded false positives

Each of these was reported by a tool and turned out to be used:

- **Python, vulture**:
  - `__main__.py:160 _split_lines` overrides `argparse.HelpFormatter`.
  - `ext/capabilities.py:24 extension_name` is a dataclass field set by keyword.
  - `ast.py:217,227,269,270` and `parser/statements/type.py:141,154` (`range_restriction` / `length_restriction`) are read via `getattr` in `_restriction_attribute`.
  - `parser/parser_context.py:43 EQUALS` is an Enum member reached by iteration in `parser/tokenizer.py:30`.
  - `encoding/instance.py:529` "unreachable" `yield` is the empty-generator idiom.
  - `command_parsers`, `get_all_leaves`, `TypeSystem`, `get_cache_stats`, `YangValidator._doc_validator`, `dispatch_registry_parity_snapshot` and `registry_parity_snapshot` are reached from tests, benchmarks or the parity scripts.
- **Python, ruff ARG**: 22 of the 25 hits are signatures fixed by a dispatch table: XPath function registry `xpath/functions.py`, `xpath/ast.py:35`, statement-parser handlers in `statement_parsers.py` and `statements/type.py`, `TypeSystem` validator table, `types/registry.py:406` builtin emitter table.
- **Python, ruff B010/B905/UP006/UP007/UP033/UP037/UP042/UP045**: these are style or modernization rules, not deprecations, and are not counted.
- **Python, jscpd**: `validator/yang_validator.py:67-77`/`:107-117` are the parallel public `validate`/`validate_detailed` signatures. `augment_expand.py:111-119`/`:175-183` is a signature where one function delegates to the other.
- **TypeScript, knip**:
  - `bench/parse.bench.ts`, `bench/worker.ts`, `scripts/build-bench-worker.mjs`, `scripts/dump-builtin-registry.mjs`, `scripts/dump-dispatch-registry.mjs` and `src/shims/node-{fs,path}-browser.ts` are used by `run-bench.mjs`, `.github/workflows/benchmark.yml`, the Python parity tests and the browser build scripts.
  - `registryParitySnapshot` and `dispatchRegistryParitySnapshot` are imported by the dump scripts.
  - The `keywords.ts` type-name exports are covered by the duplicate finding above.
  - The 15 "unused exported types" (for example `ValidationResult`, `CommonCliArgs`, `Builtin`) appear in exported signatures and are left as they are.
- **TypeScript, tsc**: `src/parser/statement-parsers.ts:258 context` is a dispatch-table handler signature.
- **Zig, rg**: `root.zig:18 type_registry` and the other `root.zig` re-exports are the library API. `unicode_categories.zig:7 UNICODE_VERSION` is generated metadata.
- **Zig, jscpd**: import headers (`statement_parsers.zig`/`yang_parser.zig:9-15`, `augment_expand.zig`/`uses_expand.zig:4-11`) and test setup (`augment_expand.zig:484/504`, `identity_graph.zig:148`/`if_feature_eval.zig:176`).
- **Zig, std deprecation scan**: `b.path` (`std.Build.path`), `allocator.dupe`, `ArrayList.pop` and `resolver.resolve` share names with deprecated std declarations but are not the deprecated ones.

## Other observations (not counted)

- `benchmarks/benchmark.py:194` does `from xyang import TypeSystem`. `xyang` does not export `TypeSystem`, so this benchmark raises `ImportError`. It should be `from xyang.types import TypeSystem`.
- jscpd measures duplication inside each implementation as 0.69 % (Python), 0.60 % (TypeScript) and 0.65 % (Zig) at the 5-line / 50-token threshold.
