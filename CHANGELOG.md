# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Zig port, phase 6: native JSON** ([#165](https://github.com/exergy-connect/xYang/issues/165)): `xyang-zig convert [--include-path DIR] [-o PATH] yang_file` writes the native JSON form byte for byte as `xyang convert` does (`json.dumps(indent=2, ensure_ascii=False)` member order and escapes, `<stem>.yang.json` beside the input or `-o` with the suffix added, `Wrote PATH`, exit 2 for an export error and 1 for a module error). `zig/src/json/generator.zig` ports `src/xyang/json/generator.py` (uses-expanded copy, own augments merged and a foreign augment refused, hoisted choices, actions and rpcs, Python's default coercion, leafref targets) including `x-yang.imports` for imported identity bases (#158), extension definitions and invocations on their stubs, the placement checks, and the refusal of RFC 8791 `sx:structure` and `sx:augment-structure`, which are applied at parse and would not be re-applied on load (#161, #164). `zig/src/json/parser.zig` ports `parse_json_schema`: import stubs become import prefixes, `xpath-prefixes` bind `must`, `when` and leafref paths, patterns are compiled, and invocations are rebuilt without being re-applied; a typedef or leaf-list default keeps the JSON value it was written with. The type registry gains its `to_schema` and `from_schema` columns, so each built-in's export, import and value check live in one entry. Like Python, a module with a `notification` or a top-level `deviation` fails the conversion (`Unsupported statement type for copy: ...`). Conformance: all 163 cases pass and `zig/conformance-pending.txt` is empty; the runner checks `export_error`, each `expected.yang.json` (as JSON and byte for byte), `generate(parse(json)) == json`, and every instance against the reloaded form. `zig/tests/cross_check.py` adds `convert` on every case module and the meta-model (written file byte for byte), output-path and usage scenarios, and for every converted and committed `.yang.json` the reloaded tree, the regenerated text byte for byte, and every case instance validated against the reloaded form.
- **Zig port, phase 5: operations and extensions** ([#165](https://github.com/exergy-connect/xYang/issues/165)): `zig/src/validator/operation.zig` ports `src/xyang/validator/operation.py`: option checks, `find_rpc`, RFC 8040 §3.5.3 action paths (percent-decoded keys, choice and case on the way, Python's usage messages), the operation node and the accessible module of RFC 7950 §6.4.1 (a copy; the loaded module is never changed). `YangValidator` takes `rpc`, `action`, `direction` and `context` like Python: the context is validated first (errors carry `document: "context"`, #155), the RFC 8040 §3.6 `module:input` / `module:output` wrapper is checked (`operation-wrapper`), and the document validator's `validateOperation` walks the parameters with the parent instance found by its keys (`action-parent` when it is missing), so `must`, `when`, defaults and leafref reach the server data (#149). A rejected call is `error.Usage` with Python's `ValueError` text. `xyang-zig validate --rpc/--action/--output/--context` replaces the phase-5 refusal. RFC 8791: `sx:structure` registers each structure on its module, structure instances (`msg` or `module:msg`) validate against the structure with Python's non-module-root behavior, and `sx:augment-structure` is applied through the extension registry (path resolved from registered structures, `if-feature` and `when` merged onto the copies), which removes the phase-2 refusal. Conformance: 158 of 163 cases pass; the 8 phase-5 cases are off `zig/conformance-pending.txt`, and only the 5 phase-6 native JSON cases remain. `zig/tests/cross_check.py` now runs every rpc and action case instance through both CLIs and adds structure, augment-structure (load errors, instances, the merged tree) and rpc/action scenarios, compared byte for byte with `xyang`.
- **Zig port, phase 4: XPath** ([#165](https://github.com/exergy-connect/xYang/issues/165)): `zig/src/xpath/` ports `src/xyang/xpath` file for file: the tokenizer (code point positions, YANG `\"` quotes, `*` as a name test or an operator), the parser (Python's grammar and its `XPathSyntaxError` text, value lists, `div`/`mod`, `not()`, `current()`), prefix binding, the stateless evaluator over `Node(data, schema, parent)` with schema-aware steps through `choice` and `case`, defaults, RFC 7951 member names, module-prefixed steps (#152) and wildcards `*` / `prefix:*` (#147), and Python's coercions for comparisons and arithmetic. The function library (`current`, `not`, `true`, `false`, `count`, `string`, `number`, `boolean`, `string-length`, `concat`, `contains`, `starts-with`, `substring-before`, `substring-after`, `translate`, `deref`, `derived-from`, `derived-from-or-self`) and the binary operators are one registry each. `must` and `when` are parsed and bound to the writing module's prefixes when the module loads, so an unknown function (`xpath-unknown-function`), an unbound prefix, a syntax error, or a wildcard in a leafref path fails the load with Python's message; a `when` merged from `uses` keeps both bound operands. `xyang-zig validate` evaluates `when` (node, `choice`, `case`, parent context for `uses`/`augment`), `must` (per list entry and leaf-list item, with `must` and `xpath-error` codes and the expression in text output) and leafref and instance-identifier `require-instance` (absolute, relative and on leaf-list items) where Python does, with identical paths, codes and messages. `refine` and `uses`-`augment` targets are parsed as XPath schema paths like Python, which removes the last phase-4 refusal. Conformance: 150 of 163 cases pass, 13 are pending (phase 5: 8, phase 6: 5); all 44 phase-4 cases pass, and `structure/structured-errors` (listed as phase 5) passes because it only needed `must`. `zig/tests/cross_check.py` adds XPath load errors and validate scenarios over the function library, operators, predicates, evaluation errors and references, compared byte for byte with `xyang`.
- **Zig port, phase 3: types and instance validation** ([#165](https://github.com/exergy-connect/xYang/issues/165)): `xyang-zig validate` checks RFC 7951 JSON (or native JSON with `--native-json`) against a module with the flags, exit codes (0 valid, 1 invalid, 2 usage or module error) and output of `xyang validate`, in `--format text` and `--format json`. The port follows `src/xyang`: one built-in type table (`zig/src/types/registry.zig`) with each type's JSON encoding, bounds and value check; the type checker (range, length, pattern, enumeration, bits, binary, union, decimal64 and fraction-digits, boolean, empty, identityref through `identity_graph.zig`, typedef chains with restrictions at each level); the instance encoder (`encoding/instance.zig`: 64-bit integers and decimal64 as strings, `[null]` for empty, `module:name` qualified members, native dict-keyed lists with key conversion, `key-mismatch`, `list-encoding` and `ambiguous-name`) and the document validator (if-feature pruning, mandatory, defaults, min/max-elements, list keys and `unique`, choice and case rules, unknown members), with JSON Pointer paths into the input as written. YANG `pattern` uses a port of `xsd_regex.py`: the same translation to Python `re` text, `\p{X}` / `\P{X}` from a general-category table generated from Python's `unicodedata` (`zig/tools/gen_unicode_categories.py`), and the same unsupported-construct and `re.error` messages, so an unsupported pattern now fails the load as in Python. `xyang-zig` command options are declared once per command and parsed with argparse's behavior and messages. `must`, `when`, `leafref` and `instance-identifier` with `require-instance`, rpc and action validation, RFC 8791 structure instances, `--anydata-validation` and YAML input fail loudly as not yet supported. Conformance: 105 of 163 shared cases pass; every phase-3 case is off `zig/conformance-pending.txt`, along with twelve later-phase cases that instance validation alone now passes. `zig/tests/cross_check.py` also runs both CLIs' `validate` on every case instance and requires identical output.
- **Zig port, phase 2: module resolution** ([#165](https://github.com/exergy-connect/xYang/issues/165)): `xyang-zig` now finishes a load the way `src/xyang/parser/yang_parser.py` does. `import` loads the module through the module search path (the importing file's directory, then each `--include-path`; `name@revision.yang`, then `name.yang`, then the newest `name@*.yang`, with Python's warning when the requested revision is not the file opened) and caches it per resolved path, so every importer shares one module. `include` merges submodules (typedefs, identities, groupings, features, imports, statements), with Python's errors for a `belongs-to` mismatch, duplicates and circular includes or imports. Then, in Python's order: `uses` expands groupings (prefixed, module-level and container-local scope; grouping typedefs registered where used), `refine` applies type, config, mandatory, default, must, min/max-elements, if-feature and description, `uses`-level `augment` merges into the expanded grouping, top-level `augment` merges into this module or an imported one (stamping the defining module), `deviate not-supported` removes its target (on a private copy of an imported module), extension invocations go through one apply registry (RFC 8791 `sx:structure` is kept, `sx:augment-structure` still fails as phase 5), and the list-key checks run. `if-feature` and `when` on `uses` and `augment` are merged onto each added node. `deviate add|replace|delete` no longer fail: like Python they print `Ignoring unsupported 'deviate KIND' for PATH` and are not applied. Identity derivation (`identity_graph.zig`) and `if-feature` evaluation with per-feature pruning (`if_feature_eval.zig`) are ported for the validation phases. One documented divergence: a `uses` whose grouping is not in scope fails with `Unknown grouping`, as `parser/substatements/container-grouping-hidden` requires and TypeScript does; Python warns and drops it (the case's `xfail`). Conformance: 35 of 163 cases pass (12 more: the 9 phase-2 cases and the 3 `structure/list-key-*` load checks), 128 are pending (phase 3: 58, phase 4: 49, phase 5: 16, phase 6: 5), and no case is pending for phase 2; the remaining `modules` and `reuse` cases load and wait only for instance validation. `zig/tests/cross_check.py` now also compares the resolved schema tree of every case that loads (122) with Python's, runs import/include/augment/deviation scenarios through `--include-path`, and requires Python's warnings on stderr.
- **Zig port, phase 1: scaffold, parser and `parse`** ([#165](https://github.com/exergy-connect/xYang/issues/165)): `zig/` holds a third implementation built as one static executable, `xyang-zig`, with Zig 0.17.1 pinned in `zig/build.zig.zon` and CI and only the standard library. It has a YANG tokenizer and parser that mirror `src/xyang/parser` (quoted and unquoted arguments, `+` concatenation, comments, extension invocations), an AST that mirrors `src/xyang/ast.py`, keyword dispatch through one frozen registry that matches Python's `dispatch_registry` (the cross-check compares them), and `xyang-zig parse FILE` with `--help` / `-h`, the same exit codes, and the same output and error text as `xyang parse`. Module resolution, XPath and XSD patterns come in later phases; until then `import`, `include`, a top-level `uses` / `augment` / `deviation`, `deviate add|replace|delete`, integers outside 64 bits and non-ASCII outside quoted strings fail with an explicit "xyang-zig cannot / does not" error instead of a different result. `zig build conformance` runs the 163 shared cases: 23 pass (every parse-error case in `parser/`, `types/duplicate-bit`, `types/empty-enumeration`, `choice/duplicate-case-names`) and the other 140 are listed in `zig/conformance-pending.txt` with the phase that delivers them. The runner fails if a listed case passes, an unlisted case fails, or the parser rejects a module Python loads. `zig/tests/cross_check.py` runs both CLIs on every `.yang` under `tests/cases` and `examples/meta-model.yang`. The new `Zig` workflow builds, runs `zig build test`, the conformance runner and the cross-check, and reports the ReleaseSmall binary size (258 KB on x86_64-linux). The `Local-Tests: passed` trailer does not attest the Zig job, so it does not skip it.
- **Native JSON: RFC 8791 structures** ([#164](https://github.com/exergy-connect/xYang/issues/164), [#161](https://github.com/exergy-connect/xYang/issues/161)): the #162 refusal was removed. `xyang convert` no longer raises `YangExportError` for `sx:structure` or `sx:augment-structure`. A structure is an extension invocation whose body uses the normal node encoding, so constraints, types and leafrefs are kept; reloading it runs the structure callback and rebuilds the index. A same-module `sx:augment-structure` is merged into the structure, and each added node carries `augment-structure` plus any `if-feature` and `when` that were merged, so it is not applied again. A cross-module `sx:augment-structure` is the invocation itself, and the imported structure is on that import's `x-yang.imports` stub; reload applies it once against the stub. Applying the callbacks again does not add the nodes twice. Any other extension with an apply callback and no JSON form still fails the export. Shared cases `modules/json-form-structure-constraints-164`, `modules/json-form-augment-structure-164`, `modules/json-form-augment-structure-cross-164`, `modules/json-form-nested-structure-164`.
- **Native JSON: extension definitions and invocations** ([#161](https://github.com/exergy-connect/xYang/issues/161)): `xyang convert` used to exit 0 and drop every `extension` and every place a module invoked one. Root `x-yang.extension` now carries this module's definitions (name, `argument`, `yin-element`, `description`, `reference`). An extension defined in an imported module and invoked here is the same object on that module's `x-yang.imports` stub, keyed by the importing prefix. Each invocation is `x-yang.extensions` on the node where it appears (`{"name": "prefix:ext", "argument": "..."}`, source order, nested body kept) for containers, lists, leaves, leaf-lists, choices, cases, typedefs, identities, rpcs and their input and output, and the module itself. `parse_json_schema` restores `module.extensions` and the invocation nodes, and `generate_json_schema(parse_json_schema(json))` reproduces the JSON. RFC 8791 `sx:structure` and `sx:augment-structure` round-trip ([#164](https://github.com/exergy-connect/xYang/issues/164)); the #162 refusal was removed. Any other invocation the form cannot carry fails the same way. Shared cases `modules/json-form-extensions-161` and `modules/json-form-rfc8791-extension-161`.
- **Native JSON: imported identity bases and augments** ([#158](https://github.com/exergy-connect/xYang/issues/158)): `xyang convert` used to exit 0 and write a `.yang.json` that rejected data the `.yang` sources accept. An identity based on an imported identity lost its base (`identityref value 'ext:widget' is not derived from all bases`), the `identityref` leaf pointed at a `$ref` that did not exist, and an `augment` was dropped (`Unknown field 'size'`), whether it targeted a node of an imported grouping or of the module itself. Now the form is self-contained: root `x-yang.imports` carries the imported identities a module needs (its bases, the bases of its `identityref` types and the identities of a direct import that derive from them), keyed by the importing prefix, and `parse_json_schema` binds them as import prefixes, so no file or `import` resolution is needed (a Cloudflare Worker can load it). Identity bases are written in the exported module's scope even when the `type` came from an imported grouping under another prefix, and an `identityref` `$ref` points at an entry that exists (`#/$defs/name` or `#/x-yang/imports/key/identities/name`). Own-module `augment` statements are merged into the tree like `uses`. A construct the form still cannot carry fails with `YangExportError` (`xyang convert` exit 2, no file written): an `augment` of another module's tree, an identity base that does not resolve, an imported typedef with restrictions. The validator resolves `identityref` bases in the module that wrote the `type`, as typedefs do. In `examples/mcp-interface` ([#157](https://github.com/exergy-connect/xYang/pull/157)) 1 of 12 rpc cases and 0 of 14 sessions gave the source result from the `.yang.json` before; now 12 of 12 and 14 of 14, in both languages. Shared cases `modules/json-form-*` (new case fields `json_form`, `export_error`), `tests/json/test_native_json_imports.py`. See `design/json-schema-xyang-profile.md`.
- **Discoverable CLI help** ([#153](https://github.com/exergy-connect/xYang/issues/153)): `xyang --help` / `-h` and `xyang <command> --help` / `-h` print usage, the real options, defaults, value forms, and short examples to stdout and exit 0. They do not read a module, a data file, or stdin. Unknown commands, unknown flags, and missing option values still exit 2. `xyang-ts` gains the same `--help` / `-h` behavior. Help comes from the argparse parser and from the TypeScript command registry in `ts/src/cli/args.ts`, so a flag added on that parser shows up in help without a second usage string. `--action`, `--output`, and `--context` are on that registry. `xyang-ts` still has no `--version`, and `xyang-ts convert` still prints JSON Schema to stdout with no `-o`.
- **Validate rpc and action input and output** ([#149](https://github.com/exergy-connect/xYang/issues/149)): `validate(module, data, rpc=NAME | action=PATH, direction="input"|"output", context=...)` on `xyang.validate`, `YangValidator.validate` and `validate_detailed`, and `xyang validate --rpc NAME | --action PATH [--output] [--context data.json]` (input by default). Before, `{"example-topology-tools:input": {...}}` was an `unknown-field` error and the `must` on `target` never ran; now it fails with `must` at `/example-topology-tools:input/target` and the rule's `error-message`. RFC 7951 mode takes the RFC 8040 §3.6 wrapper (`module:input` / `module:output`, in the operation's module); `--native-json` takes the bare parameters; anything else is `operation-wrapper`. Types, `mandatory`, `default`, `must`, `when`, `if-feature`, `leafref`, `identityref` and `choice` use the existing engine. **Actions** (RFC 7950 §7.15) are now parsed under container, list, grouping and augment (they used to be skipped with a warning; a module-level `action` is now a parse error), exported as `x-yang.actions`, and named by their RFC 8040 §3.5.3 data resource identifier (`/m:interfaces/interface=eth0/reset`, keys percent-encoded). Per RFC 7950 §6.4.1 the accessible tree is the context plus the operation node: a child of the root for an rpc, a child of the selected container or list instance for an action, with the parameters as its children, so `../source`, `../../mtu` and absolute paths resolve; the wrapper adds no level. **The context is validated** against the module first; its issues carry `"document": "context"` with a pointer into the context and the operation is not checked. An action needs a context holding its parent instance; a missing one is `action-parent`. An unknown rpc or action, a malformed path, missing keys, a false `if-feature` on the operation or its parent, and bad option combinations are usage errors (exit 2, `ValueError`). The module, data and context are not modified. Shared cases `operations/*`; the shared runners gain per-instance `rpc`, `action`, `direction`, `context`, `usage_error` and per-error `document`.
- **Prefixed XPath node names** ([#152](https://github.com/exergy-connect/xYang/issues/152)): `prefix:name` steps in `must`, `when` and `leafref` paths selected nothing, so every row of the issue's table with a prefix was invalid and `/b:top/b:item/b:n` reported a missing target. Each prefix is now bound when the module loads, in the module that wrote the expression (own prefix or `import` alias), and a step matches only a child that module defines, so nodes augmented in by another module and same-named children of different modules are told apart. Unprefixed steps keep matching by local name. An undeclared prefix in a leafref path now fails the load (exit 2), like `must` and `when`. `instance-identifier` values keep RFC 7951 module names (§6.11), not YANG prefixes. A `type`'s prefix and typedef name now resolve where the `type` is written, so typedefs and groupings imported from another module keep their bindings (`type l:port` in a grouping, `type lx:item-ref` in an augment). The native JSON form records `x-yang` `xpath-prefixes`, qualifies members another module augments in (`ext:name`; two augmented `name` leaves used to overwrite each other), and inlines typedefs of other modules (they used to become a plain string). XPath path caching keys on the bound modules and predicates. Shared cases `xpath/prefixed-table`, `prefixed-steps`, `prefixed-definition-site`, `prefixed-step-unknown-prefix`, `prefixed-leafref-unknown-prefix`, `references/leafref-prefixed`.
- **XPath wildcard node tests** ([#147](https://github.com/exergy-connect/xYang/issues/147)): `must` and `when` accept `*` and `prefix:*`. `count(*) = 1` was a parse error (exit 2) in both runtimes. `*` selects all data-node children, including those another module augments in, and counts list entries and leaf-list items individually; `prefix:*` selects only the children of the module the prefix is bound to in the module that wrote the expression. Per XPath 1.0 §3.7, `*` after an operand stays the multiply operator (`2 * 3`, `a * b`, `count(x) * 2`, `count(*) * 2`). An unbound `prefix:*` fails when the module loads, as an unknown prefix in an `augment` path does; wildcards in `leafref` and other schema paths are still rejected. `count(*)` and `*[x]` are now valid in expressions that used to fail to parse. Shared cases `xpath/wildcard`, `wildcard-multiply`, `wildcard-prefix`, `wildcard-unknown-prefix`, and `wildcard-schema-path`.
- **Audit engagement example:** `examples/ontology-hypergraph` models a fictional audit of a fictional client in one YANG model on the generic `example-hypergraph` core, replacing the laboratory profile: employees, accounts, terminations, account sign-ins, privileged changes, controls, collected evidence, assessments, findings, and reviews. Times are `uint32` epoch seconds so `must` expressions compare and add them. Each sign-in and change declares `breach: yes|no`, and a `must` requires the declaration to equal the facts (a per-owner join for sign-ins after termination; self-approval, missing approval, or approval after deployment for changes). Assessments must be `exception` exactly when a covered fact breaches; every breach needs a finding; findings may cite only breaching facts of their control's kind, must cite the fact's source evidence, and need an approved review. Cited evidence must come from a collection in the same engagement, be collected no later than the assessment, and be at most `max-evidence-age` older than the engagement's `as-of`; reviews follow their assessment and precede `as-of`. Four HTTP publications (firm catalogue, evidence locker, assessments, reviews) are merged by the collector, which verifies model bytes and export SHA-256 and computes no outcome. `fixtures/` holds the valid projection, 22 invalid projections, and `expected-errors.json`; `tests/test_ontology_hypergraph.py` and `ts/test/ontology_audit_example.test.ts` assert those exact errors in both languages. A valid record can report a failed control; validity is neither an audit opinion nor proof that the facts are true.
- **Agent skills:** `skills/xyang-validate/SKILL.md` covers validating instances and using the results: `--format json` output and exit codes (0 valid, 1 invalid, 2 usage or parse error), `validate` / `validate_detailed` / `validateDetailed`, RFC 7951 versus native JSON (64-bit strings, `[null]` for `empty`, absent list versus `[]`), `--features`, `--include-path`, anydata, the `xyang-ts` Action `version` input, the browser bundle, and QuickJS binaries. `skills/xyang-model/SKILL.md` gains the 1.0.0 statement rules and RFC 7951 instance rules, and fixes `npx xyang-ts` (no such package) to `npx -p @exergy-connect/xyang xyang-ts`. `llms.txt` and `AGENTS.md` link both skills. `tests/test_skills.py` checks skill frontmatter, links, discovery, that the asset `.yang.json` files match `convert`, and the CLI results the skills quote.

### Changed

- **Ontology example tests run on release** ([#154](https://github.com/exergy-connect/xYang/issues/154)): `tests/test_ontology_hypergraph.py` carries the `ontology` marker, and pull-request and main pytest pass `-m "not ontology"`. `npm test` excludes `test/ontology_audit_example.test.ts`; `npm run test:ontology` runs it. The Ontology example workflow runs on `release: published` (and `workflow_dispatch`, which publishes nothing) with `requirements-tools.txt` installed, and fails if any Python test is skipped. The 400-case target is unchanged: these tests stay in the logical count.
- **Test suite consolidated** ([#154](https://github.com/exergy-connect/xYang/issues/154)): 1,649 → 1,495 logical test cases against `main` at `da3775c`. Shared instances went from 510 to 627, Python-only tests from 632 to 496, and TypeScript-only tests from 507 to 372. The 400-case target is not met; the shared instances alone exceed it. Mirrored Python/TypeScript validation tests are now shared cases in `tests/cases`. Duplicates were deleted only where a named retained check covers them. Models load once per file. `pytest -q` takes 34 s instead of 39 s. [`tests/inventory.py`](tests/inventory.py) counts cases from the runners, and CI prints its summary. [`tests/README.md`](tests/README.md) has the policy for new tests. [`docs/test-consolidation-154.md`](docs/test-consolidation-154.md) has the counts, timings, blockers and the removed-to-retained traceability map. No production code changed.

### Fixed

- **Unresolved `uses` grouping** ([#173](https://github.com/exergy-connect/xYang/issues/173)): a `uses` whose grouping cannot be resolved fails the load with `Unknown grouping '<name>'` (the same `YangSemanticError` message TypeScript raises), including a grouping defined in a container and used outside it. A module-level grouping, and a grouping used inside the container that defines it or inside that container's descendants, still expands. Shared case `parser/substatements/container-grouping-hidden`.
- **Python leaf-list `leafref`** ([#145](https://github.com/exergy-connect/xYang/issues/145)): a relative `leafref` path on a `leaf-list` item started at the item's parent instead of the item, so it walked one level too high and a valid reference such as `../../../node/id` from a nested `leaf-list` was rejected as dangling, while TypeScript accepted it. It now starts at the item, as for an ordinary leaf (RFC 7950 §9.9.2). Absolute paths and ordinary leaves are unchanged. Instances that were wrongly rejected now pass; a dangling item is still rejected. The shared case `references/leafref-leaf-list` covers both languages.
- **Python typedef resolution** ([#142](https://github.com/exergy-connect/xYang/issues/142)): a typedef named `date`, `date-and-time`, `identifier`, `entity-name`, `field-name`, or `qualified-source` was treated as a bare `string`, so its `pattern` and `length` (and those it inherits from a base typedef) were never checked, while TypeScript enforced them. These names came from a fixed list left over from the meta-model; real YANG built-ins already resolve through the type registry. They now resolve like any other typedef, so a leaf of such a typedef, a typedef derived from it, and a `type` that narrows it all apply every level's restrictions. `examples/meta-model.yang` defines `date`, `date-and-time`, `entity-name`, and `field-name`, and its tests pass unchanged. Shared cases `types/typedef-builtin-like-names` and `types/typedef-builtin-like-names-imported` cover both languages. Data that violated such a typedef and used to pass now fails.
- **Docs:** the README's pinned `xyang-ts` Action example used `version: v0.1.4`, which has no `xyang-ts.mjs` asset; it now uses `v1.0.0`, the first release with one. The README and `qjs/README.md` no longer call `--format json` a QuickJS follow-up; the binary supports it like `xyang-ts`.
- **QuickJS release workflow:** `qjs-release.yml` runs on `ubuntu-24.04` instead of `ubuntu-latest`. `ubuntu-latest` became Ubuntu 26.04, where `qemu-user-static` has no installation candidate, so the v1.0.0 release run failed at `apt-get install` before building and attached no binaries. The build and both Linux smoke tests are unchanged. A manual run accepts `source_ref` to build and smoke-test an existing tag, such as `v1.0.0`, with the current workflow; it uploads a workflow artifact and attaches nothing.

## [1.0.0] — 2026-11-11

Changes since 0.1.11. Breaking changes for upgrading code and data:

- `xyang.json.integer_bounds` is removed; import from `xyang.types.registry` (below).
- TypeScript: `YangModule.data` and `YangStatement.data` are removed (see Changed).
- The parser rejects substatements its parent does not accept (keyword dispatch, below), and statement arguments are stricter (`yang-version`, `value`, `min-elements` / `max-elements`, boolean arguments).
- Validation is stricter in several places listed under Fixed, including JSON strings for 8/16/32-bit integers, `min-elements` and `mandatory` under absent containers, `unique`, and Python container/list shapes and leaf types.
- The `xyang-ts` GitHub Action takes `version` instead of `ref`, and `path` / `xyang-root` are removed.

### Removed

- **Breaking:** `xyang.json.integer_bounds` is removed. There is no compatibility shim and no deprecation warning. Import `YANG_INTEGER_BOUNDS`, `YANG_INTEGER_BUILTIN_NAMES`, `json_integer_bounds_for_builtin`, and `yang_integer_from_json_bounds` from `xyang.types.registry`. Integer bounds behavior is unchanged.

### Fixed

- **CI:** the Python test job installs the TypeScript dependencies before `pytest`. The registry parity tests run `ts/scripts/dump-dispatch-registry.mjs` and `ts/scripts/dump-builtin-registry.mjs`, which import `esbuild`. On a runner that has not installed `ts/node_modules` those scripts exit 1 with `Cannot find package 'esbuild'`, so every Python version failed on main from #117 on. A failing script's stderr is now part of the assertion.
- **Boolean arguments:** `mandatory`, `config`, `require-instance`, and `yin-element` accept `true` and `false` whether or not they are quoted. `"true"` and `true` are the same value. `TRUE`, `yes`, `1`, and a missing argument are a `YangSyntaxError` naming the statement and the value.
- **`range` and `length` bodies:** `range` and `length` accept `description`, `reference`, `error-message`, and `error-app-tag` (RFC 7950 §9.2.4, §9.4.4), plus a prefixed extension. An unknown child is a `YangSyntaxError` naming the parent and the keyword. The constraint string is unchanged. `error-message` and `error-app-tag` are reported on a range or length miss, the same way as `pattern`.
- **`enum` names:** an unquoted enum name such as `enum 100GE` or `enum 50|100GE` (`huawei-ifm.yang`) is read as one argument. `100GE` was split into `100` and `GE`, and `GE` was rejected as an unknown statement in the `type` body. The tokenizer also dropped characters it did not recognize, such as `|`. They are now part of an unquoted argument, and a parse error anywhere else. Python and TypeScript match.
- **TypeScript:** `tsc --noEmit` passes again. `YangTokenType` is a const object whose type includes punctuation, so `Array.includes` and `YangTokenType.INPUT` in a type position failed. `hasTokenType` does the same membership check, and input/output parameters use `typeof YangTokenType.INPUT`. Validation and schema behavior are unchanged.

### Added

- **Release benchmark:** `benchmarks/release_bench.py` measures parse and validation time (median of warmed-up repeated runs), peak RSS, and source lines for Python and TypeScript on the same checked-in workloads, and writes `benchmarks/results/latest.json` and the marked benchmark section of `README.md`. Timing uses warm, repeated runs in their own processes. Peak memory comes from separate fresh processes that do the setup and one operation, then report their own Linux `VmHWM` (the whole process peak; no baseline is subtracted and no garbage collection is forced), so it does not depend on the timing iteration count. Line counts come from `benchmarks/loc.py` (standard library only). The `Benchmark` workflow runs it when a release is published, attaches the results to the release, and opens a pull request with the README update; pull requests touching benchmark files run a smoke test. Methodology and limitations: `benchmarks/README.md`.
- **Parser keyword dispatch:** one table per language maps each parent statement to the substatements it accepts (`parser/dispatch_registry` in Python, `parser/dispatch-registry` in TypeScript). Every statement body uses that table and one miss path: the parent's handler, a prefixed extension, or `YangSyntaxError` naming the parent and the keyword. TypeScript bodies that used to accept any keyword now reject the ones Python already rejected. A prefixed extension is accepted under parents that previously skipped that check, including `typedef` ([#121](https://github.com/exergy-connect/xYang/issues/121)).
- **Documentation:** added docs/KEY-LEARNINGS.md.
- **Built-in type registry:** `src/xyang/types/registry.py` and `ts/src/types/registry.ts` are the one table per language for how a YANG built-in maps to JSON (encoding, bounds, pattern, schema export, schema import, and the RFC 7951 value check). JSON Schema export, import, and instance checks call that table. `ARCHITECTURE.md` says where to change each of those ([#113](https://github.com/exergy-connect/xYang/issues/113)).
- **Docs:** a "Deviations from RFC 7950 / RFC 7951" table in `FEATURES.md`, and README links to that section and to `design/yang-ebnf-supported-constructs.md`. The README states the Python `validate()` tuple and the TypeScript `{ isValid, errors, warnings }` result, notes that `xyang-ts convert` prints to stdout, and moves Browser ES modules and feature inference to before License. Fixes #71. Fixes #74.
- **XPath:** `contains()`, `starts-with()`, `substring-before()`, and `substring-after()` follow XPath 1.0 in Python and TypeScript. String arguments use the same conversion as `string()`. An empty second argument makes `contains` and `starts-with` true, `substring-before` empty, and `substring-after` the whole source. The wrong number of arguments raises `XPathEvaluationError`, which validation reports as `xpath-error`. An unknown function name is still a compile error (`xpath-unknown-function`) ([#85](https://github.com/exergy-connect/xYang/issues/85)).
- **Shared cases:** included submodule data nodes and typedefs (`tests/cases/modules/include`, `include-typedef`), and `augment` inside `uses` (`tests/cases/reuse/uses-augment`, `uses-augment-bad-target`). TypeScript now matches Python on these cases ([#55](https://github.com/exergy-connect/xYang/issues/55), [#62](https://github.com/exergy-connect/xYang/issues/62)).
- **Native JSON via `--native-json`:** `iter_instance` walks the input as written and yields one node per instance node (`stmt`, decoded `value`, input `pointer`, `children`). RFC 7951 is the default and is strict (`int64` / `uint64` / `decimal64` strings, `empty` as `[null]`, module-qualified members where required). Native mode is opt-in (`native_json=True`, `--native-json`) and accepts single-key lists keyed by value, JSON numbers, and `empty` as `null`. There is no fallback between modes. New error codes: `ambiguous-name`, `key-mismatch`, `list-encoding`. Error paths address the input as written. The minified browser bundle uses that same strict RFC 7951 default. This subsumes [#50](https://github.com/exergy-connect/xYang/issues/50) ([#95](https://github.com/exergy-connect/xYang/issues/95)).
- **One-call validate and machine-readable CLI:** `xyang.validate(schema, data, *, features=None, include_path=())` returns the `validate_detailed` dict (`schema` is a path or a parsed module). `xyang validate` accepts `--format text|json`, `--features` (`{"module": ["feature"]}` or `null`), and `-` for stdin. `--format json` prints `{"valid", "errors": [{path, code, message}]}` on stdout and warnings on stderr. Exit codes are 0 valid, 1 invalid, and 2 for usage or schema/parse errors ([#82](https://github.com/exergy-connect/xYang/issues/82)).
- **Discoverability:** `keywords` on the Python and TypeScript packages, agent notes in `AGENTS.md` (install, `parse` / `validate` / `convert`, validate examples, tests), and [`llms.txt`](llms.txt) ([#81](https://github.com/exergy-connect/xYang/issues/81)).
- **Native JSON format:** documented the intent of the native JSON form of YANG: reversible, unambiguous, and fast to load (`README.md`, `AGENTS.md`).
- **Structured validation errors (Python + TypeScript):** `YangValidator.validate_detailed` and `validateDetailed` return `{valid, errors, warnings}`. Each issue is `{code, path, message, expression?, severity}` and `path` is a JSON Pointer (list and leaf-list entries by position). `validate()` string output is unchanged. Shared case runners read codes and pointers from this API ([#79](https://github.com/exergy-connect/xYang/issues/79)).
- **Shared conformance cases:** language-neutral cases in `tests/cases/` (YANG modules, JSON instances, expected `(JSON Pointer, code)` errors) run by both `tests/test_cases.py` and `ts/test/cases.test.ts`; known Python/TypeScript divergences are recorded as per-implementation expected failures. A new CI workflow runs both runners on every change.
- **Python `YangValidator(module, enabled_features_by_module=...)`:** configure enabled features without dropping to `DocumentValidator`, matching TypeScript `enabledFeaturesByModule`.
- **QuickJS-ng executable:** `qjs/build.sh` builds the TypeScript CLI as a self-contained `xyang-ts` binary with QuickJS-ng 0.18.0 (static musl on Linux; macOS and Windows cross-compiled with Zig). A published GitHub Release builds all five binaries, smoke-tests the Linux ones against the Node CLI, and attaches them. Pull-request CI does not build the binaries.

### Changed

- **Breaking (TypeScript):** `YangModule.data` and `YangStatement.data` are removed, with no deprecated alias. The `__class__` dict layer is gone. Use the typed fields: on a statement, `name`, `keyword`, `argument`, `description`, `statements`, `type`, `mandatory`, `if_features`, `when`, `config`, `key`, `default`, and `findStatement`; on a module, `name`, `yangVersion`, `namespace`, `prefix`, `description`, `typedefs`, `identities`, `statements`, `import_prefixes`, `features`, `feature_if_features`, `extensions`, `extension_runtime`, and `groupings`. `ModuleData` is the module itself ([#120](https://github.com/exergy-connect/xYang/issues/120)).
- **Performance (Python):** faster parsing and instance validation with the same results. The tokenizer skips whitespace, comments, and quoted-string bodies by span instead of one character at a time, and quoted strings without a backslash skip unescaping. The instance iterator builds JSON Pointers incrementally and caches data nodes, name resolution, and typedef unwrapping per walk. RFC 7951 member keys are memoized per statement, and per-node debug logging is skipped unless enabled. `benchmarks/parse_bench.py` reproduces the timings (not run in CI). Median of 7 runs on one machine: parse of the 4 largest common modules 66.5 → 41.1 ms, `iter_instance` over 10k list entries 311 → 181 ms (RFC) and 253 → 180 ms (native), validation of the same instance 787 → 584 ms (RFC) and 722 → 576 ms (native).
- **CI:** a head commit whose message contains the trailer line `Local-Tests: passed` skips the Python matrix, the Node minimum and latest LTS jobs, and the conformance cases on pull requests. Add the trailer only after `pytest -q`, `pytest tests/test_cases.py -q -rxX`, and `cd ts && npm test` have passed locally. Pushes to `main`, tags, and releases always run the full suite. Required Checks still succeed when those jobs were skipped for the trailer, and fail when a heavy job failed or was cancelled.
- **TypeScript model:** `ts/src/core/model.ts` is the runtime model. `statements` returns the same wrapper objects when the underlying statement array is unchanged. The unused `ts/src/core/module.ts` class is removed ([#73](https://github.com/exergy-connect/xYang/issues/73)).
- **TypeScript API:** public names are camelCase (`expandUses`, `includePath`, `findStatement`, `getAllLeaves`). The snake_case names still work and warn once per process ([#72](https://github.com/exergy-connect/xYang/issues/72)).
- **TypeScript parsing:** `parseYangString(content, { filename, sourcePath, includePath, expandUses })` resolves imports from `dirname(sourcePath)` and `includePath`. `parseYangFile` builds a new parser on every call, so an edited file is read again ([#77](https://github.com/exergy-connect/xYang/issues/77)).
- **Python package:** `xyang` exports `YangSyntaxError`, `generate_json_schema`, and `parse_json_schema` ([#76](https://github.com/exergy-connect/xYang/issues/76)).
- **Python CLI:** `TypeError` and `ImportError` are no longer reported as user errors. Loading `.yaml` or `.yml` without PyYAML raises `ValueError` with the install hint ([#76](https://github.com/exergy-connect/xYang/issues/76)).
- **TypeScript API:** `YangValidator.enable_extension` is a deprecated alias of `enableExtension` and warns once per process ([#72](https://github.com/exergy-connect/xYang/issues/72)).
- **TypeScript:** removed unused `ts/src/validator/path-builder.ts` and `ts/src/validator/validation-error.ts` ([#76](https://github.com/exergy-connect/xYang/issues/76)).
- **Tests:** removed per-language tests whose valid/invalid outcome is already covered by a shared case in `tests/cases/`. Bits (empty, duplicate token, non-string), bits-in-union, duplicate bit names, empty enumerations, and `if-feature` on a list moved into shared cases.
- **Breaking:** GitHub Action `xyang-ts` input `ref` is replaced by `version` (a release tag, default `latest`). The action downloads `xyang-ts.mjs` from GitHub Release assets instead of checking out a committed bundle. The `path` input and `xyang-root` output are removed (#89).
- CI no longer commits `artifacts/xyang-ts.mjs` or `docs/xyang.umd.min.js`. A published release builds them with `npm run build:ci` and attaches them; pull-request CI only runs that build as a check and does not push commits (#89).

### Fixed

- **TypeScript validation:** a string leaf or leaf-list entry reports every restriction violation, in Python's order: `length`, then each failing `pattern`, then `enum`. `TypeChecker.validate` returns `(code, message)` pairs and `DocumentValidator` records each pair, so those codes are not inferred with `codeForMessage`. `TypeSystem.validate` remains `[boolean, string | null]` and is a thin wrapper that returns the first message. The shared case `length and pattern both violated` passes in both languages ([#119](https://github.com/exergy-connect/xYang/issues/119)).
- **Substatements (Python + TypeScript):** a prefixed extension is accepted in a `type` body; `units` is accepted on a `typedef` and copied onto leafs that use it and do not set their own; `reference` is accepted on a module; `organization`, `contact`, `description`, and `reference` are accepted in a submodule header; `type` is accepted in an extension invocation; `default` is accepted in a `choice`; `grouping` is accepted in a `container` and is visible only in that container and its descendants. A typedef reached again through the same include is one definition. ([#116](https://github.com/exergy-connect/xYang/issues/116))
- **Statement arguments (Python + TypeScript):** a statement argument is one string: a quoted string (with `+` concatenation) or an unquoted run up to whitespace, `;`, or `{`, including `:`, `/`, `.`, and digits. `yang-version` must be `1` or `1.1`, `value` must be an integer, and `min-elements` / `max-elements` must be an integer or `unbounded`. Any other value is a `YangSyntaxError` naming the statement and the value (`yang-version 1`, `yang-version "1.1"`, `namespace urn:example:m`, `value "0"`, `max-elements "20"`, `length 1..127`, unquoted `/` paths) ([#115](https://github.com/exergy-connect/xYang/issues/115)).
- JSON Schema export types int64/uint64/decimal64 as RFC 7951 strings (#63).
- **Numeric strings for 8/16/32-bit integers (Python + TypeScript):** `int8`, `int16`, `int32`, `uint8`, `uint16`, and `uint32` reject a JSON string with `Expected integer, got string`. RFC 7951 encodes those as JSON numbers, which is what `convert` already emits (`"type": "integer"`). A schema default (`default 3` on an integer typedef or union) is still applied as a number. `tests/cases/types/integer/schema-cross-check.json` requires the generated schema and the validator to agree on that set ([#63](https://github.com/exergy-connect/xYang/issues/63)).
- **RFC 8791 structure instances (Python + TypeScript):** a structure is a top-level data node, written `msg` or `m:msg`. Error paths are JSON Pointers into that member (`/m:msg/n`, `/msg/n`). Python no longer drops the member, and TypeScript accepts the qualified form ([#78](https://github.com/exergy-connect/xYang/issues/78)).
- **`empty` encoding (Python + TypeScript):** shared cases confirm the strict RFC 7951 form: `[null]` is the only valid value, and `null`, `true`, and `""` are `type` errors (`tests/cases/types/boolean-empty`) ([#59](https://github.com/exergy-connect/xYang/issues/59)).
- **Duplicate list keys (Python + TypeScript):** a duplicate key is still reported once at the list, and the entries are validated anyway, so a `range` or `must` error inside an entry is no longer hidden ([#67](https://github.com/exergy-connect/xYang/issues/67)).
- **Error paths (TypeScript):** errors point at the right node, matching Python. An unknown field is reported at the member (`top.b`, and `zzz` at the root), and `choice` / `case` names no longer appear in paths, so a leaf inside a case is `top.port` and choice errors are at the parent data node `top` ([#60](https://github.com/exergy-connect/xYang/issues/60)).
- **`min-elements` and `mandatory` on absent nodes (Python + TypeScript):** `min-elements` applies to an absent list or leaf-list (count 0) when its parent exists and its `when` / `if-feature` are active (RFC 7950 §7.7.5). Python now descends into an absent non-presence container as `{}`, so mandatory leaves and `min-elements` below it are reported, matching TypeScript; absent presence containers are still skipped. Data that omitted such nodes now fails validation. `examples/meta-model.yang` drops `min-elements 1` from the optional `foreignKeys` list, and `meta-model.yang.json` is regenerated ([#57](https://github.com/exergy-connect/xYang/issues/57)).
- **`unique` (Python + TypeScript):** the `unique` statement is parsed (Python used to reject it) and enforced (TypeScript used to skip it). Each argument is a set of descendant paths with prefixes stripped; entries missing any leaf of a set are ignored. Two entries with equal values give one `unique` error per set at the list, `Unique constraint violated in list 'servers': ip='1' (entries at index 0 and 1)`. The native JSON form carries it as `x-yang.unique` (`[["ip", "port"]]`) and reads it back ([#58](https://github.com/exergy-connect/xYang/issues/58)).
- **`identityref` values (Python + TypeScript):** values follow RFC 7951 §6.8. A bare `name` resolves in the leaf's module, and `modname:name` uses the *module name* of that module or of an import, never its prefix (`resolve_identity_value` / `resolveIdentityValue`). TypeScript now validates identityref values (direct, through a typedef, or as a union member): an unknown identity or one not derived from every base is an `identityref` error, as in Python. With `prefix p`, `m:tcp` and `tcp` are valid and `p:tcp` is an error. The instance-value argument of `derived-from()` / `derived-from-or-self()` uses the same rule; the identity literal still uses schema prefixes ([#53](https://github.com/exergy-connect/xYang/issues/53)).
- **XSD `pattern` regexes (Python + TypeScript):** a YANG `pattern` is translated from XSD (RFC 7950 §9.4.5) when the module loads, by `xyang.xsd_regex.translate` and `translateXsdRegex` (TypeScript compiles with the `u` flag). `\p{X}` / `\P{X}` Unicode categories, `\i` / `\c` / `\I` / `\C`, and the XSD meanings of `.`, `\d`, `\s`, `\w` are supported; the pattern is anchored, and `^` / `$` are literal characters as in XSD. Python no longer raises `re.error` on `\p{L}`, and TypeScript accepts `héllo` for `\p{L}+`. Block escapes (`\p{IsBasicLatin}`), class subtraction (`[a-z-[aeiou]]`), and other non-XSD syntax fail the module load with `YangSemanticError: unsupported XSD regex construct ...` ([#49](https://github.com/exergy-connect/xYang/issues/49)).
- **`deviate not-supported` (Python + TypeScript):** the target node is removed when the module is built, including a node in an imported module. The removal is applied to a copy owned by the deviating module, so loading the target module again from the same parser cache still has that node. Data for the removed node is an unknown field on the copy. `deviate add`, `replace`, and `delete` are still skipped, with a warning that names the kind and the path ([#64](https://github.com/exergy-connect/xYang/issues/64)).
- **JSON Schema `convert` (Python + TypeScript):** `description` is omitted when the YANG node has none, instead of `"description": ""`. A missing `description` is still read back as an empty string ([#83](https://github.com/exergy-connect/xYang/issues/83)).
- **Parser (Python + TypeScript):** an unquoted `if-feature` argument is accepted, including a prefixed name (`if-feature f;` and `if-feature m:f;`). Quoted and concatenated arguments are unchanged ([#65](https://github.com/exergy-connect/xYang/issues/65)).
- **Import revision-date (Python + TypeScript):** when `import x { revision-date R; }` does not find `x@R.yang`, the parser warns with the file it opened (`import 'x' revision-date R not found; using ...`) instead of falling back silently. An exact revision file is chosen ahead of a newer `x@*.yang`. A missing import reports `Could not find module`, not `submodule` ([#66](https://github.com/exergy-connect/xYang/issues/66)).
- **TypeScript:** a `bits` type that declares the same bit name twice is a parse error (`Duplicate bit name`), matching Python ([#93](https://github.com/exergy-connect/xYang/issues/93)).
- **XPath:** `+`, `-`, `*`, `div`, and `mod` are numeric operators (XPath 1.0). Python evaluates `*`, and both languages parse and evaluate `div` and `mod` (`mod` is a truncating remainder, the same as JavaScript `%`). `+` does not concatenate strings ([#48](https://github.com/exergy-connect/xYang/issues/48)).
- **FEATURES.md:** dropped the contradictory lines on augment merging, `if-feature` in JSON Schema, and path caching, removed the usage-statistics section and the stale test-count list, and moved "Recent Improvements" to [History (moved from FEATURES.md)](#history-moved-from-featuresmd) ([#68](https://github.com/exergy-connect/xYang/issues/68)).
- **Agent skill:** `skills/xyang-model/SKILL.md` documents `import`, `include`/`submodule`, and `augment`, points at `design/` for the JSON Schema profile and grammar, and includes the TypeScript CLI ([#69](https://github.com/exergy-connect/xYang/issues/69)).
- **Version and descriptions:** `xyang --version` reads the installed package version (or `unknown` when that metadata is missing). The CLI, `pyproject.toml` description, and package docstring share one description. `PERFORMANCE.md` cites the current source paths ([#70](https://github.com/exergy-connect/xYang/issues/70)).
- **TypeScript parse order:** uses expansion, then `augment`, then RFC 8791 extension indexing, and only when `expand_uses` is set — the same gate and order as Python ([#75](https://github.com/exergy-connect/xYang/issues/75)).
- **Python validation:** multi-part `range` and `length` restrictions keep every part. A value is accepted when it falls in at least one part, and an integer is still checked against its built-in minimum and maximum when a `range` is present (`range "1..3 | 10..max"` rejects `4` and `5`, and values above the type's maximum) ([#54](https://github.com/exergy-connect/xYang/issues/54)).
- **Validation (Python + TypeScript):** a `range`, `length`, or `pattern` on a `type` that names a typedef is applied after that typedef's own restrictions, so a derived typedef or a leaf can narrow a range ([#56](https://github.com/exergy-connect/xYang/issues/56)).
- **JSON Schema import:** `parse_json_schema` rejects a schema that has no root `x-yang` object, and a root property that has no `x-yang`, instead of returning an empty module named `unknown` ([#80](https://github.com/exergy-connect/xYang/issues/80)).
- **Python validation:** a present container must be a JSON object, a list or leaf-list must be a JSON array, and each list entry must be an object. Wrong shapes report `type` (`container must be an object`, `list must be an array`, `list item must be an object`, `leaf-list must be an array`) instead of being skipped or accepted as a one-element leaf-list ([#52](https://github.com/exergy-connect/xYang/issues/52)).
- **Python validation:** leaf type checks reject a JSON value of the wrong type instead of coercing it. A non-integral number or a boolean is not an integer (`Expected integer, got <json type>`), a boolean is not a decimal64, and a non-string is not a string (`Expected string, got <json type>`). Length and pattern are not applied to a non-string. Numeric strings for integer types are unchanged ([#51](https://github.com/exergy-connect/xYang/issues/51)).
- **XPath:** an unknown function name is a compile error (`xpath-unknown-function`) in Python and TypeScript.
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

## History (moved from FEATURES.md)

## Recent Improvements

### RPC and notification parsing (2026-05)
- ✅ **`notification`**: Parsed into `YangNotificationStmt` (module/submodule and under `container`, `list`, `grouping`, `augment`).
- ✅ **`rpc` / `input` / `output`**: Module-level RPC with I/O blocks parsed into dedicated AST nodes (`tests/test_rpc_input_output.py`).
- ✅ **RPC in yang.json**: `generate_json_schema` / `parse_json_schema` round-trip via `x-yang.rpcs` (`tests/json/test_rpc_json.py`); integer built-ins round-trip via JSON Schema `minimum` / `maximum`.

### TypeScript CLI and parser (2026-05)
- ✅ **`xyang-ts validate --anydata-validation` / `--anydata-module`**: Parity with Python CLI for optional anydata subtree validation; see [`ts/CHANGELOG.md`](ts/CHANGELOG.md).
- ✅ **`augment` body**: `case`, `notification`, and other data-node substatements under `augment` (and `augment` under `uses` via `YangUsesStmt.augmentations`).
- ✅ **`status` on typedefs**: Ignored at parse time (RFC 7950 §7.21.2) so standard modules with `status deprecated` parse cleanly.
- ✅ **`rpc` / `input` / `output`**: Parser and yang.json parity with Python (`ts/test/rpc_input_output.test.ts`, `ts/test/json/rpc_json.test.ts`); `rpc` not in unsupported-skip; `rpc` inside `container` rejected (syntax error).


### String patterns: modifiers and multiple substatements (2026-04)
- ✅ **YANG:** Parse several `pattern` lines, optional `modifier invert-match` blocks, and per-pattern `error-message` / `error-app-tag`.
- ✅ **Validation:** `DocumentValidator` / TS type checker apply every pattern in order, including invert semantics and pattern-specific errors.
- ✅ **JSON Schema:** Emit `x-yang.string-patterns` and reconstruct the list when parsing `.yang.json` back into an AST.

### Import, submodule, if-feature, and docs (2026-04)
- ✅ **`import` / `include` / `submodule`**: Resolve and parse dependent `.yang` files; merge included submodules; `import` prefix map for prefixed types and `if-feature` expressions.
- ✅ **`if-feature`**: Parsing on data-definition parents supported by the grammar; boolean evaluation; `DocumentValidator` integration; `uses` / `refine` propagation; per-feature conditions on `feature` statements; `copy_yang_statement` refactored with `dataclasses.replace`.
- ✅ **`FEATURES.md`**: Brought in line with the codebase (this update).

### Meta-model example and documentation (2026-04)
- ✅ **`examples/meta-model.yang`** stays aligned with the xFrame canonical module (including `year` in `primitive-type-name`, multiple `revision` statements, and current `when` / `must` paths under the `type` container).
- ✅ **`FEATURES.md` usage statistics** were recomputed with stricter patterns (e.g. `must "` only) so counts are not inflated by the word “must” inside description text.

### CLI, Convert, and JSON Schema (2026-03)
- ✅ **CLI**: `xyang` (or `python -m xyang`) with subcommands
  - `parse <file.yang>` — print module name, namespace, prefix, typedef count, etc.
  - `validate <file.yang> [data.json]` — validate JSON against the YANG module (stdin if no file)
  - `convert <file.yang> [-o path]` — convert .yang to JSON Schema; output path always ends with `.yang.json` (default: `<stem>.yang.json` alongside input)
- ✅ **Convert**: Uses `YangParser(expand_uses=False)` for a reversible AST (`uses`/`augment` not flattened at parse); the JSON generator expands `uses` when emitting; produces draft 2020-12 JSON Schema with `x-yang` annotations.
- ✅ **JSON Schema pattern fix**: Pattern strings are written as-is; `json.dumps()` performs the single escape needed for JSON. Previously patterns were double-escaped, producing invalid regex in the output (e.g. `\\\\d` instead of `\\d`).

### Union Types with Leafref and XPath String Functions (2026-02-26)
- ✅ **Union types with leafref**: Added support for union types containing leafref members
  - Union validation now handles leafref members correctly
  - Leafref validation is deferred to LeafrefResolver for proper context resolution
  - Enables typedefs with union of multiple leafref paths (e.g., top-level fields and composite subcomponents)
- **XPath string functions**: `contains()`, `substring-before()`, and `substring-after()` are not implemented. See https://github.com/exergy-connect/xYang/issues/85.

### Choice/Case and Stricter Validation (2026-02-24)
- ✅ **Choice/case statements**: Full implementation of YANG choice and case statements
  - Supports mandatory choices (exactly one case must be present)
  - Validates that only one case is present per choice
  - Properly handles choice cases in uses expansion
  - Comprehensive test suite in `tests/test_choice_case.py` (8 tests)
- ✅ **Union types in typedefs**: Full support for union types in typedef definitions
  - Validates values against all union member types
  - Properly resolves typedefs with union base types
  - Comprehensive test suite in `tests/test_typedef_union.py` (6 tests)
- ✅ **Nested typedefs (YANG 1.1)**: `typedef` inside `container`, `list`, `grouping`, etc. (e.g. IETF `ietf-notification-capabilities`); `tests/test_typedef_in_container.py`
- ✅ **Stricter structure validation**: Validator now rejects unknown fields not defined in schema
  - Field checking is scoped locally to each validation context
  - Properly handles choice/case when collecting valid field names
  - Clear error messages with path information

### Foreign Key Validation and Must Constraints (2026-02-23)
- ✅ **Foreign key primary key validation**: Added must constraints to enforce that foreign keys reference primary keys
  - Constraint on `foreignKeys` list: if `field` is specified, it must equal the referenced entity's primary key
  - Constraint on `field` leaf: validates that field references the primary key when specified
- ✅ **Parents list validation**: Added comprehensive must constraints for parent-child relationships
  - Validates that child foreign key references parent's primary key
  - Validates that child foreign key field type matches parent primary key type
- ✅ **Must constraints on leafref lists**: Full support for must constraints on list statements containing leafref types
  - `current()` correctly refers to the list item context
  - Constraints can access sibling leafref values within the same list item
  - Comprehensive test suite in `tests/test_must_on_leafref_list.py` (5 tests)
- ✅ **Leafref error messages**: Enhanced error messages to include field names for better debugging
- ✅ **Deref() improvements**: Enhanced `deref()` function to handle:
  - Entity name resolution with fallback mechanisms
  - Complex paths with predicates (e.g., `foreignKeys[0]/entity`)
  - Path stripping for predicate handling
  - Nested deref() calls with proper context preservation
- ✅ **Grouping expansion refactoring**: Moved grouping expansion to parsing phase
  - Groupings are now expanded once during parsing, not in each validator
  - Eliminates redundancy and ensures consistency across validators
  - Removed unused grouping expansion code from validators
- ✅ **Test coverage**: The suite has since grown (see **Test Coverage**); historical note: 178 tests at the time of this entry, including fixes for:
  - Foreign key validation tests
  - Parents validation tests
  - Deref() function tests
  - Current context in predicate tests
  - Leafref relative path tests

### Composite Fields and Grouping Support (2026-01-16)
- ✅ **Composite field type**: Added `composite` to primitive-type enumeration
- ✅ **Composite field structure**: Implemented composite fields with subcomponents using grouping architecture
- ✅ **Field definition refactoring**: Refactored field definitions to use grouping-based architecture
  - Created `composite-field` grouping for subcomponent definitions
  - Created `field-definition` grouping that extends `composite-field`
  - Created `foreign-key-definition` grouping for reuse
- ✅ **Primary key changes**: Changed `primary_key` from leaf-list to single leaf supporting composite fields
- ✅ **Foreign key refactoring**: Changed `foreignKey` to use `references` list for multiple entity/field combinations
- ✅ **Grouping/uses parser support**: Full parser implementation completed
  - Supports grouping definitions and uses statements
  - Supports refine statements to modify nodes from groupings
  - Supports nested groupings (grouping that uses another grouping)
  - Properly expands uses statements by copying statements from groupings
  - Must constraints from groupings are evaluated in the correct context
  - Comprehensive test suite in `tests/test_grouping_uses.py` (8 tests, all passing)

### XPath Evaluator Enhancements (2026)
- ✅ **Nested deref() support**: Full implementation of nested `deref()` calls for complex cross-entity validation
- ✅ **Path navigation fixes**: Proper handling of `../../name` and other multi-level relative paths
- ✅ **Predicate navigation**: Support for navigating from predicate results (e.g., `fields[...]/type`)
- ✅ **Leaf-list indexing**: Correct handling of `primary_key[1]` and other numeric indices
- ✅ **Code refactoring**: Modular architecture with separated concerns for better maintainability
- ✅ **Performance optimizations**: Expression caching, efficient context management, and optimized lookups

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
