# xYang Feature Set

## Deviations from RFC 7950 / RFC 7951

| Behavior | RFC says | xYang does | Code |
| --- | --- | --- | --- |
| XPath value lists `('a','b')` | YANG XPath is XPath 1.0, which has no literal sequences (an XPath 2.0 form) | A parenthesized list of string or number literals is one value. `=` is true when the left side equals any item. Only literals are allowed inside | `src/xyang/xpath/parser.py`, `ts/src/xpath/parser.ts` |
| Case-insensitive function names | XPath 1.0 function names are case-sensitive | Names are folded with `lower()` / `toLowerCase()` before lookup | `src/xyang/xpath/evaluator.py`, `ts/src/xpath/evaluator.ts` |
| Flat typedef scope | A typedef nested in a statement is visible only in that statement and its descendants | Every typedef is stored on the module map, so a typedef nested in a container is visible module-wide. Duplicate names are rejected; scoped shadowing is not modeled | `src/xyang/parser/statements/typedef.py`, `ts/src/parser/statements/typedef.ts` |
| `deviate replace` of a defaulted property | RFC 7950 §7.20.3.2: the properties to replace must exist in the target node | `config`, `mandatory`, `min-elements` and `max-elements` count as present when the target omits them, because each has a default value. `default`, `units` and `type` must be present | `src/xyang/augment_expand.py`, `ts/src/transform/augment-expand.ts`, `zig/src/augment_expand.zig` |
| Unqualified top-level members | RFC 7951 requires a namespace-qualified name on each member of a top-level JSON object (`m:top`) | A top-level member may be unqualified (`top`) or qualified (`m:top`) | `src/xyang/encoding/instance.py`, `ts/src/encoding/instance.ts` |

Other gaps are tracked as `xfail` entries in `tests/cases/`, listed with `rg -n '"(python|ts)": "' tests/cases --glob case.json`.

This document lists the YANG features implemented in xYang. Primary usage is reflected in `examples/meta-model.yang`; multi-module parsing and `if-feature` are also covered by dedicated tests (e.g. `tests/test_yangson_ex3_import.py`, `tests/test_if_feature.py`).

## Features Implemented

### Module Structure
- ✅ `module` - Module definition
- ✅ `yang-version` - YANG version (1.1)
- ✅ `namespace` - Module namespace
- ✅ `prefix` - Module prefix
- ✅ `organization` - Organization (1 occurrence)
- ✅ `contact` - Contact info (1 occurrence)
- ✅ `description` - Description text
- ✅ `revision` - Revision history (9 revisions in the current `examples/meta-model.yang`)
- ✅ `import` - Import other modules (loads `.yang` from the directory of the file being parsed, optional `YangParser(include_path=...)` for extra search paths); `import` prefix map on `YangModule.import_prefixes`
- ✅ `include` - Include submodules into the parent module (merged typedefs, identities, groupings, features, top-level statements)
- ✅ `submodule` / `belongs-to` - Submodule files parsed and merged via `include`
- ✅ `feature` - Feature declarations; optional braced body with `description`, `reference`, and `if-feature` (per-feature conditions stored on the module)
- ✅ `notification` - Notification statements (RFC 7950 §7.16); parsed into `YangNotificationStmt` at module/submodule level and under `container`, `list`, `grouping`, and `augment` (YANG 1.1 `*notification-stmt` in those bodies)
- ✅ `rpc` / `input` / `output` - RPC statements (RFC 7950 §7.14); module-level `rpc` with optional `input` and `output` blocks parsed into `YangRpcStmt`, `YangInputStmt`, and `YangOutputStmt`. Data definitions (leaves, containers, `uses`, etc.) are allowed inside `input`/`output`. Stray `input`/`output` outside `rpc` or `action` are a **parse error**. **JSON Schema:** module RPCs live under root `x-yang.rpcs` (round-trip via `parse_json_schema`; `tests/json/test_rpc_json.py`). **Instance validation** ([#149](https://github.com/exergy-connect/xYang/issues/149)): see [rpc and action instances](#rpc-and-action-instances).
- ✅ `action` - Action statements (RFC 7950 §7.15) under `container`, `list`, `grouping` and `augment`, parsed into `YangActionStmt` (a `YangRpcStmt` subclass) with `input` / `output`; a module-level `action` is a parse error. **JSON Schema:** `x-yang.actions` on the container or list, keyed by action name (`module:name` for an action another module augments in), same shape as `rpcs` with `x-yang.type` `action`.

### rpc and action instances

`validate(module, data, rpc=NAME | action=PATH, direction="input"|"output", context=...)` (TypeScript `{ rpc | action, direction, context }`, CLI `--rpc NAME | --action PATH [--output] [--context data.json]`, default input) validates one operation's input or output with the normal engine (types, `mandatory`, `default`, `must`, `when`, `if-feature`, `leafref`, `identityref`, `choice`).

- **Encoding:** RFC 7951 mode takes the RFC 8040 §3.6 wrapper `{"module:input": {...}}` (or `module:output`), where `module` defines the operation (`aug:input` for an action `aug` augments in). `--native-json` takes the bare parameters. Any other top level is `operation-wrapper`.
- **Action target:** `PATH` is the RFC 8040 §3.5.3 data resource identifier of the action node, the path RESTCONF POSTs to below `{+restconf}/data`: `/m:interfaces/interface=eth0/reset`. The first segment is module-qualified, later ones when the module changes; every list step gives all its keys, comma-separated and percent-encoded (`/m:pair=x,2/swap`, `interface=eth%2F0`). A path that is malformed, names a node that is not a container or list, misses keys, names no action, or whose action or parent has a false `if-feature` is a usage error (exit 2). An action needs `context`.
- **Accessible tree (RFC 7950 §6.4.1):** the server data from `context` plus the operation node. For an rpc the operation node is a child of the root named after the rpc; for an action it is a child of the selected container or list instance. The parameters are the operation node's children, so `../source` (rpc), `../../mtu` (action, the parent entry's leaf) and absolute paths such as `/m:add-link/m:source` or `count(/m:interfaces/m:interface/m:reset)` resolve. The wrapper is encoding only and adds no level. The selected list entry must be in the context (keys compared as canonical text); a missing entry or presence container is `action-parent` on the context. An absent non-presence container exists implicitly.
- **Context:** validated against the module first, as an ordinary instance (encoding, types, `mandatory`, `must`, `when`, `leafref`, `choice`, unknown members, features). Its issues carry `"document": "context"` and a JSON Pointer into the context (`validate()` text prefixes them with `context`), and the operation is then not checked, so it never reads bad data. A valid context is not re-validated with the operation, and its defaults are visible to the operation's XPath. Without `context`, an rpc's references outside the operation are unresolved (`leafref` fails, `must` is false).
- **Errors:** paths address the data as written, including the wrapper (`/m:input/delay`). Option misuse (`rpc` with `action`, `direction` / `context` without either, unknown rpc, non-object `context`) is a usage error.
- **Immutability:** the module, the data and the context are not modified; the accessible tree is a shallow copy with copied statements on the path to the operation.
- Shared cases: `tests/cases/operations/`.

### Type Definitions
- ✅ `typedef` - Type definitions at **module** level and **nested** under `container`, `list`, `choice`, `case`, `grouping`, `notification`, and `rpc` `input`/`output` (RFC 7950 §7.3; YANG 1.1). Each name is registered on `module.typedefs` so leaves can reference it (e.g. `type notification-support` inside the same container). Typedefs are **not** copied into the data tree by `uses` expansion. **Limitation:** one flat typedef map per module (duplicate names in different scopes are rejected; scoped shadowing is not modeled).
- ✅ `type` - Type references

### Built-in Types
The lexer treats **all** RFC 7950 built-in type names (Section 4.2.4) as reserved keywords: `binary`, `bits`, `boolean`, `decimal64`, `empty`, `enumeration`, `identityref`, `instance-identifier`, `int8`, `int16`, `int32`, `int64`, `leafref`, `string`, `uint8`, `uint16`, `uint32`, `uint64`, `union`.

**All** of these built-in types are **validated** during document validation (`DocumentValidator` / `xyang validate`): values are checked against the rules for that type (numeric `range`, `string` / `binary` `length` and `pattern`, `decimal64`, `enumeration`, `bits`, ordered **`union`** members, **`leafref`** / **`identityref`** / **`instance-identifier`** with `require-instance` semantics, and so on). **JSON Schema** representation and `x-yang` round-trip detail still vary by type (see **YANG.json hybrid format**). Types heavily used in `meta-model.yang`:
- ✅ `string` - String type
- ✅ `binary` - Base64 instance string; `length` on decoded octets; `pattern` on lexical form
- ✅ `int32` - 32-bit integer
- ✅ `uint8` - 8-bit unsigned integer (1 occurrence)
- ✅ `boolean` - Boolean type
- ✅ `decimal64` - Decimal64 type (3 occurrences)
- ✅ `empty` - Empty type (presence-only leaf; validated)
- ✅ `bits` - Bits type

### Derived Types
- ✅ `enumeration` - Enumeration type (6 `type enumeration` typedef bodies) (built-in keyword; `enum` is the substatement keyword inside the block). The meta-model’s `primitive-type-name` enumeration includes **year** (calendar year) alongside string, integer, number, boolean, array, datetime, date, duration_in_days, and qualified types.
- ✅ `union` - Union type (3 occurrences) - **Full support in typedefs with validation, including union types with leafref members**

### Data Structures
- ✅ `container` - Container statements
- ✅ `list` - List statements (with key)
- ✅ `leaf` - Leaf statements
- ✅ `leaf-list` - Leaf-list statements
- ✅ `anydata` / `anyxml` — Parsed; inner JSON unconstrained unless you enable the optional ``xyang.ext`` subtree validator ([draft-ietf-netmod-yang-anydata-validation](https://datatracker.ietf.org/doc/html/draft-ietf-netmod-yang-anydata-validation); uses ``xyang.encoding`` / RFC 7951 qualified names). JSON Schema: open union + `x-yang.type` for round-trip.
- ✅ `choice` - Choice statements (mutually exclusive alternatives)
- ✅ `case` - Case statements (choice alternatives)
- ✅ `grouping` - Grouping statements (defines reusable schema components); may contain nested `typedef` and nested `grouping`
- ✅ `uses` - Uses statements (incorporates groupings)
- ✅ `refine` - Refine statements (modifies nodes from groupings)

### Instance data encodings
- ✅ **JSON ([RFC 7951](https://www.rfc-editor.org/rfc/rfc7951))** — Validators consume dict/list instance trees in this shape. Core helper ``xyang.encoding.resolve_qualified_top_level`` (``encoding/rfc7951.py``) maps a namespace-qualified object member ``module-name:node`` to a top-level schema node in that module (used for optional anydata subtree validation and reusable elsewhere). RFC 7951 is the default.
- ✅ **Native JSON** — Opt-in with `--native-json`, Python `native_json=True`, TypeScript `{ nativeJson: true }`, or case.json `"encoding": "native"`. Dict-style input: keyed objects for single-key lists, bare names, JSON numbers, and `null` for empty. Error paths point at the input as written. There is no fallback between the two encodings (`src/xyang/encoding/instance.py`, `ts/src/encoding/instance.ts`).
- ⚠️ **XML** ([RFC 7950](https://www.rfc-editor.org/rfc/rfc7950) XML encoding) — Not supported yet for instance validation or qualified-name resolution.
- ⚠️ **Binary encodings** (e.g. [RFC 9254](https://www.rfc-editor.org/rfc/rfc9254) CBOR) — Not supported yet.

### Constraints
- ✅ `must` - Must constraints (19 `must "` substatements) - **Parsed and evaluated**
  - Supports must constraints on containers, lists, leaves, leaf-lists, `anydata`, and `anyxml`
  - Supports must constraints on lists containing leafref types
  - `current()` correctly refers to list item context in list must constraints
- ✅ `when` - When conditions — **Parsed and evaluated** on every RFC 7950 parent the parser supports for **data nodes**: `container`, `leaf`, `leaf-list`, `list`, `anydata`, `anyxml`, `choice`, `case`, and `uses` (not on `refine`).
- ✅ `if-feature` - **Parsed** on `container`, `leaf`, `leaf-list`, `list`, `choice`, `case`, `uses`, `refine`, `augment`, `identity`, and braced `feature`; **boolean expressions** (`and` / `or` / `not`, parentheses, `prefix:feature`) evaluated for **document validation** via `DocumentValidator(..., enabled_features_by_module=...)`. `uses` / `refine` `if-feature` values are ANDed onto expanded grouping nodes; `copy_yang_statement` preserves `if_features` through `uses` expansion. Feature-level `if-feature` substatements prune `build_enabled_features_map()` (RFC 7950 §7.20.1). **Not** emitted in JSON Schema `x-yang` yet.
- ✅ `mandatory` - Mandatory fields (16 occurrences)
  - Supports mandatory on choice statements (exactly one case must be present)
- ✅ `default` - Default values (7 occurrences)
- ✅ `min-elements` - Minimum elements (5 occurrences)
- ✅ `max-elements` - Maximum elements (1 occurrence)
- ✅ `key` - List keys (heavily used)
- ✅ `unique` - Unique leaf combinations across list entries (RFC 7950 §7.8.3); entries missing a leaf of the set are ignored. Round-trips as `x-yang.unique`

### Type Constraints
- ✅ `pattern` - Pattern matching (6 occurrences); XSD regex syntax (RFC 7950 §9.4.5) translated at load time, including `\p{X}` categories and `\i` / `\c`; unsupported XSD constructs fail the module load; **multiple** patterns and **`modifier invert-match`** per RFC 7950, with per-pattern error metadata. JSON Schema: top-level `pattern` when a single non-inverted regex suffices; otherwise `allOf` / `not` plus **`x-yang.string-patterns`** for round-trip (Python and `ts/`).
- ✅ `length` - Length constraints (3 occurrences)
- ✅ `range` - Range constraints (2 occurrences)
- ✅ `fraction-digits` - Decimal fraction digits (3 occurrences)

### Type References
- ✅ `leafref` - Leaf references (7 `type leafref` uses) - **Parsed and resolved via deref()**
- ✅ `path` - Leafref paths
- ✅ `require-instance` - Leafref require-instance
- ✅ `instance-identifier` - **Parsed** with `require-instance`; validation resolves absolute paths when `require-instance` is true; JSON Schema `x-yang.type` + `require-instance`

### Identity
- ✅ `identity` / `base` - Identity statements (multi-base supported); `if-feature` on `identity` is parsed
- ✅ `identityref` / `base` - Identityref type; instance values as qualified names; validation against the derivation graph
- ✅ XPath `derived-from()` / `derived-from-or-self()` in `must` expressions
- ✅ JSON Schema: `$defs` per identity (`enum` of qualified names) and `$ref` / `allOf` on `identityref` leaves; `parse_json_schema` round-trip

### Container Features
- ✅ `presence` - Container presence (1 occurrence)
- ✅ `config` (RFC 7950 §7.21.1) — explicit `config true` / `config false` on container, leaf, leaf-list, list, choice, and case; stored on the AST (`config: Optional[bool]`, `None` = inherit) and echoed in `x-yang` JSON Schema; `refine` may set `config` on container, leaf, list, and leaf-list targets

### CLI and JSON Schema Export
- ✅ **CLI** (`xyang` or `python -m xyang`): `parse`, `validate`, `convert`
  - `xyang parse <file.yang>` — parse and print module info
  - `xyang validate <file.yang> [data.json]` — validate JSON (file or stdin) against the module
  - `xyang validate … --anydata-validation complete|candidate` — validate RFC 7951 qualified members under `anydata` using `--anydata-module` paths and/or every `*.yang` in `--include-path` and the host directory ([draft anydata validation](https://datatracker.ietf.org/doc/html/draft-ietf-netmod-yang-anydata-validation); see `examples/ietf-yang-push/README.md`)
  - `xyang convert <file.yang> [-o path]` — convert .yang to JSON Schema (output path always ends with `.yang.json`)
- ✅ **CLI** (`xyang-ts`, package `@exergy-connect/xyang` under [`ts/`](ts/)): `parse`, `validate`, `convert`
  - Same `--include-path` semantics as Python
  - `xyang-ts validate … --anydata-validation complete|candidate` and repeatable `--anydata-module` (loads import closure; unparseable extra modules skipped with a warning)
  - Unwraps a single top-level `module:local` instance key when it names the host module (e.g. `ietf-yp-notification:envelope`)
  - **Limitation:** cross-module `augment` merge for the anydata module map is not applied yet (Python runs `apply_augmentations_across_module_map`); large bundles such as `examples/ietf-yang-push` may still require `expandUses: false` until uses/refine expansion matches Python
- ✅ **JSON Schema generator**: YANG AST → JSON Schema (draft 2020-12) with `x-yang` annotations
  - `generate_json_schema(module)`, `schema_to_yang_json(module, output_path=...)`
  - Parse with `YangParser(expand_uses=False)` so the AST keeps original `uses` and `augment` structure; the generator expands `uses` when emitting. That split keeps **YANG ↔ JSON Schema** conversion reversible where `x-yang` carries the source shape.
  - Round-trip: parse YANG → generate JSON → parse JSON schema → equivalent AST where supported
  - **RPC:** `x-yang.rpcs` maps RPC name → `{ "x-yang": { "type": "rpc" }, "input": {…}, "output": {…} }` (I/O blocks use `x-yang.type` `input` / `output`; config data stays in root `properties`)

## Features NOT Implemented

All RFC 7950 built-in type **names** are reserved as lexer keywords (see **Built-in Types** above), even when validation or JSON Schema support is incomplete.

### Partial / syntax only
- ✅ **`augment`** — Parsed into `YangAugmentStmt` and, with `YangParser(expand_uses=True)`, merged into the target schema (including cross-file targets via `import`). Augmented nodes record `defining_module` for RFC 7951 JSON (`module:identifier` when the defining module differs from the parent). CLI `--anydata-validation` loads extra modules through one parser cache and registers the import closure so augments apply to the same `YangModule` instances used for validation. With `expand_uses=False`, augments stay as explicit statements for reversible convert.
- ✅ `deviation` is applied after augments, including across an `import` (on a copy; the cached module is unchanged). `deviate not-supported` removes the target node. `deviate add`, `replace`, and `delete` change `config`, `default`, `mandatory`, `min-elements`, `max-elements`, `must`, `type`, `units`, and `unique` (RFC 7950 §7.20.3.2). An invalid deviate fails the load: `add` of a single-valued property the target has, `replace` of one it lacks, `delete` of a value it does not have, or a property the target node cannot carry. A path may pass through an rpc or action `input` / `output` that the module does not write. `convert` applies the module's own deviations; a deviation of another module's tree is an export error.

### Not implemented (skipped when parsing)
- None today: `action` is parsed (above).

### Dynamic extension framework
- ✅ `extension` definitions are parsed into the AST and tracked on `YangModule.extensions`.
- ✅ Prefixed extension invocations (`prefix:name`) are parsed generically into AST nodes, including nested statement bodies.
- ✅ Capability registry (`xyang.ext.capabilities`) allows semantic plugins to transform generic invocations without hardcoding extension names in the core parser.
- ✅ Built-in capability plugin for RFC 8791 (`ietf-yang-structure-ext`) maps:
  - `sx:structure` and `sx:augment-structure` remain generic extension-invocation AST nodes
  - RFC 8791 semantics are applied by extension post-parse hooks (including `augment-structure` merge pass)

Other reserved built-in type names may parse but lack full validation or JSON Schema parity; see **Built-in Types** and sections above.

## When Conditions

xYang supports `when` statements for conditional validation. When a `when` condition evaluates to `false`, the associated statement is skipped; if instance data is present for that branch, validation reports an error (see RFC 7950 §7.21.5). Supported parents match the implemented subset of the data model: `container`, `leaf`, `leaf-list`, `list`, `choice`, `case`, and `uses`. For `choice` and `case`, the XPath context is the same as for other children of the enclosing container or list entry (the choice/case nodes do not appear as data keys).

Example from `meta-model.yang` (leaf-list `enum` only when primitive allows enumerated values):
```yang
leaf-list enum {
  when "../primitive = ('string', 'integer', 'number', 'year')";
  type union {
    type string;
    type int32;
    ...
  }
}
```

If the `when` expression evaluates to false, the node is not part of the effective schema for that instance; data under that branch is then invalid if present.

## If-feature (RFC 7950 §7.20)

The validator evaluates `if-feature` **before** `when` and structural rules (RFC 7950 ordering): if the expression is false, the node is inactive; instance data for that node is an error.

- **Expressions**: `and`, `or`, `not`, parentheses; feature names or `prefix:feature` (imports and own module prefix).
- **API**: `DocumentValidator(module, enabled_features_by_module={ "module-name": frozenset({"feat", ...}), ... })`. Modules omitted from the map use all **pruned** declared features (after applying each feature’s own `if-feature` substatements).
- **Parents** (parsed, with validation where the node participates in the data tree): `container`, `leaf`, `leaf-list`, `list`, `choice`, `case`, `uses` (merged into expanded nodes), `refine` (merged into refine targets).

See `src/xyang/validator/if_feature_eval.py` and `tests/test_if_feature.py`.

## Grouping and Uses Implementation

xYang supports `grouping` and `uses` statements for defining and reusing schema components. This allows for modular schema design and eliminates duplication.

### Grouping Definition
Groupings can be defined at the module level and contain any schema statements (containers, lists, leaves, leaf-lists, and even other uses statements).

Example:
```yang
grouping common-fields {
  leaf name {
    type string;
    mandatory true;
  }
  leaf description {
    type string;
  }
}
```

### Uses Statement
The `uses` statement incorporates a grouping into the current schema node. When a `uses` statement is encountered, the statements from the grouping are copied and expanded into the current location. A `when` substatement on `uses` is AND-merged onto each top-level node from the grouping (parent context for evaluation). An `if-feature` substatement on `uses` is likewise AND-prepended to each expanded root node’s `if_features` list.

Example:
```yang
container data {
  uses common-fields;
  leaf value {
    type int32;
  }
}
```

### Refine Statement
The `refine` statement allows modifying nodes from a grouping when using it. This is particularly useful for adding constraints or changing properties. Supported substatements include **`default`** (for `leaf` and `leaf-list` targets), **`config`** (for container, leaf, list, and leaf-list targets), and **`mandatory`** (for leaf and choice targets). Multiple `default` lines under one `refine` build the leaf-list default set; the merged values are emitted in JSON Schema as **`default`** (scalar for a leaf, **array** for a leaf-list, matching draft 2020-12). Refine may add **`if-feature`** expressions, which are appended to the target node’s `if_features` (AND with any existing conditions).

Example:
```yang
container data {
  uses base-field {
    refine type {
      must ". != 'invalid'" {
        error-message "Type cannot be invalid";
      }
    }
  }
}
```

### Nested Groupings
Groupings can use other groupings, allowing for composition and extension of schema components.

### Context Preservation
When groupings are expanded via `uses`, must constraints and XPath expressions are evaluated in the context where the grouping is used, not where it was defined. This ensures that relative paths like `../type` correctly reference the expanded location.

## YANG.json hybrid format

The **`.yang.json`** output (from `xyang convert` or `schema_to_yang_json()`) is a **hybrid** of standard JSON Schema and YANG-specific annotations. It is valid JSON Schema (draft 2020-12) so generic tools can validate structure and types, while an **`x-yang`** custom property carries the semantics that JSON Schema does not natively express.

### Structure

- **Root**: Standard `$schema`, `$id`, `description`, `type`, `properties`, `additionalProperties`, and optional `$defs` (typedefs). A root **`x-yang`** object holds module metadata: `module`, `yang-version`, `namespace`, `prefix`, `organization`, `contact`, and optional **`rpcs`** (module-level RPC definitions; not mixed into `properties`).
- **Nodes**: Each schema node (container, list, leaf, leaf-list) has an **`x-yang`** object alongside the JSON Schema keywords. It always includes `type` (e.g. `"container"`, `"leaf"`, `"list"`, `"leaf-list"`). Lists include `key`; nodes with `must` constraints include a **`must`** array of `{ "must", "error-message", "description" }`.
- **Typedefs**: In `$defs`, each typedef has `"x-yang": { "type": "typedef" }` plus the usual JSON Schema type/pattern/enum/etc.

### What lives in JSON Schema vs x-yang

| Concern | JSON Schema | x-yang |
|--------|-------------|--------|
| Structure (object, array, types) | ✅ `type`, `properties`, `items`, `$ref`, `$defs` | — |
| Simple constraints | ✅ `pattern`, `minLength`, `maxLength`, `minimum`, `maximum`, `enum`, `default`, `multipleOf` (decimal64: `10^-fraction-digits`) | — |
| String patterns (YANG) | ✅ `allOf` / `not` when multiple or inverted | ✅ `string-patterns`: ordered list with regex + `invert` for full fidelity |
| Node kind | — | ✅ `type`: container, list, leaf, leaf-list |
| List key | — | ✅ `key` |
| Leafref | `type: "string"` (value shape only) | ✅ `type: "leafref"`, `path`, `require-instance` |
| Must constraints | — | ✅ `must`: array of expression + error-message + description |
| When conditions | — | ✅ `when`: object `{ "condition": "<xpath>" }` with optional `"description"` (RFC-style substatement text) |
| If-feature | — | `if-features`: array of strings (one per `if-feature` substatement, AND in YANG order) on data nodes, hoisted `choice` metadata, choice `oneOf` case branches, and identity `$defs` |
| Module metadata | — | ✅ Root `x-yang`: module name, namespace, prefix, etc. |
| RPC / input / output | — | ✅ Root `x-yang.rpcs`; per-RPC `input` / `output` objects with data-node `properties` |
| Integer built-in (leaf) | ✅ `type: "integer"` with `minimum` / `maximum` (canonical bounds per built-in, e.g. `uint8` → 0..255) | — |

### Leafref in hybrid form

A leafref is emitted as a string type in JSON Schema (so the value is still validated as a string), with the reference semantics in **x-yang**:

```json
{
  "type": "string",
  "x-yang": {
    "type": "leafref",
    "path": "../fields/name",
    "require-instance": true
  }
}
```

Full validation (reference existence, deref, etc.) is done by the YANG validator using the x-yang metadata, not by a plain JSON Schema validator.

### Must constraints in hybrid form

Must constraints are not expressible in JSON Schema, so they appear only under **x-yang**:

```json
"x-yang": {
  "type": "leaf",
  "must": [
    {
      "must": "not(../maxDate) or . <= ../maxDate",
      "error-message": "minDate must be less than or equal to maxDate when both are specified",
      "description": "..."
    }
  ]
}
```

The XPath expression is preserved as a string; the YANG validator evaluates it during validation.

### When conditions in hybrid form

`when` is always an object (not a bare string): required **`condition`** (XPath) and optional **`description`** when the YANG source had a `when { description "..."; }` substatement.

```json
"x-yang": {
  "type": "leaf",
  "when": {
    "condition": "../primitive = ('date','datetime')",
    "description": "minDate applies only to date and datetime primitives."
  }
}
```

### Round-trip and tooling

- **Generate**: Parse `.yang` with `YangParser(expand_uses=False)` (reversible AST: `uses`/`augment` not flattened at parse) → `generate_json_schema(module)` or `schema_to_yang_json(module, output_path=...)` → `.yang.json`.
- **Parse back**: `parse_json_schema(data)` reads the same file and reconstructs a `YangModule` (equivalent where supported); the json parser understands `x-yang` and `$defs`.
- **Generic JSON Schema tools**: Can use the file for structure and type checking; they ignore `x-yang`. Full YANG semantics (must, when, leafref resolution) require xYang’s validator.

## XPath Implementation

xYang implements a comprehensive XPath evaluator that handles all the XPath expressions used in `meta-model.yang`:

### Path Navigation
- ✅ **Relative paths**: `../field`, `../../field`, `../../name` - Supports going up multiple levels with proper list index handling
- ✅ **Absolute paths**: `/data-model/entities` - Navigation from root
- ✅ **Current node**: `.` and `current()` - Access current context value
- ✅ **Path continuation**: `fields[name = "x"]/type` - Navigate from predicate results

### Functions
- ✅ `string-length(.)` - Get length of current node value
- ✅ `contains(., 'ab')` - True when the first string contains the second (XPath 1.0). An empty second argument is true
- ✅ `starts-with(., 'z')` - True when the first string starts with the second. An empty second argument is true
- ✅ `substring-before(., '-')` - Substring preceding the first occurrence of the second argument; empty when that argument is empty or does not occur
- ✅ `substring-after(., '-')` - Substring following the first occurrence of the second argument; the whole source when that argument is empty; empty when it does not occur
- ✅ `translate(., '_', '')` - Translate/remove characters
- ✅ `count(...)` - Count elements in a list
- ✅ `deref(...)` - **Resolve leafref with full support for nested paths**
  - Supports: `deref(../entity)`, `deref(current())`, `deref(deref(...)/../foreignKey/entity)`
  - Handles relative paths from any context
  - Resolves entity and field references correctly
- ✅ `current()` - Get current node value (preserved in predicate contexts)
- ✅ `not(...)` - Logical negation
- ✅ `true()`, `false()` - Boolean literals
- ✅ `boolean(...)` - Convert value to boolean following YANG / XPath 1.0 rules
- ✅ `number(...)` - Convert value to number following XPath rules

- ✅ **Wildcard node tests** (XPath 1.0 §2.3, §3.7): `*` selects every data-node child of the context node, including children another module augments in, and counts list entries and leaf-list items one by one (`count(*)`, `*[x]`, `a/*/b`). `prefix:*` selects only the children defined by the module that `prefix` is bound to in the module that wrote the expression (its own prefix or an `import`). `*` is the multiply operator after an operand (`2 * 3`, `a * b`, `count(*) * 2`) and a node test otherwise. A `prefix:*` whose prefix the module does not bind is rejected when the module loads. Wildcards are not allowed in schema paths (`leafref`, `augment`, `refine`). Nodes in a choice's cases are included. A `prefix:*` inside a grouping that another module uses resolves against the module that wrote the grouping. Tests: `tests/cases/xpath/wildcard*`.
- ✅ **Prefixed node names** ([#152](https://github.com/exergy-connect/xYang/issues/152), RFC 7950 §6.4.1, §9.9.2): `prefix:name` steps in `must`, `when` and `leafref` `path`, absolute, relative and in predicates (`/a:top/a:item[a:n = 'x']`, `../b:item/b:n`). The prefix is bound when the module loads, in the module that wrote the expression (its own prefix or an `import` alias), so a grouping or typedef from module X used in module Y keeps X's prefixes. A prefixed step matches only a child that module defines (a node augmented in by another module needs that module's prefix; two children with the same local name in different modules are told apart). An unprefixed step matches the local name, as before. An undeclared prefix fails the load (exit 2). `instance-identifier` values are RFC 7951 data (§6.11): their prefixes are module names, not YANG prefixes, so `/base:top/item[n='x']` is valid and `/bs:top/...` with an import alias is not. The native JSON form records `{prefix: module}` as `x-yang` `xpath-prefixes` on each `must`, `when` and leafref and qualifies members another module augments in (`ext:name`), so bindings survive the round trip; a form without that map may use only the module's own prefix. Tests: `tests/cases/xpath/prefixed-*`, `tests/cases/references/leafref-prefixed`.
- ✅ **Native JSON form of extensions** ([#161](https://github.com/exergy-connect/xYang/issues/161)): `x-yang.extension` carries this module's extension definitions; an imported extension this module invokes is on that import's `x-yang.imports` stub. Invocations are `x-yang.extensions` on the node where they appear, in source order, with a nested body. `parse_json_schema` restores both. RFC 8791 `sx:structure` and `sx:augment-structure` round-trip ([#164](https://github.com/exergy-connect/xYang/issues/164)); the #162 refusal was removed. A structure is re-indexed on reload, a same-module `sx:augment-structure` is already merged, and a cross-module one is applied once against the import stub. Tests: `tests/cases/modules/json-form-extensions-161`, `tests/cases/modules/json-form-rfc8791-extension-161`, `tests/cases/modules/json-form-*-164`.
- ✅ **Native JSON form of imported identities and augments** ([#158](https://github.com/exergy-connect/xYang/issues/158)): `x-yang.imports` carries the imported identities a module needs (stubs keyed by the importing prefix, each with its own `imports`), so the `.yang.json` loads and validates with no files or `import` resolution; `identityref` bases are written in the exported module's scope and `$ref` an entry that exists. A module's own `augment` statements, including those onto nodes of an imported grouping, are merged into the form. An `augment` of another module's tree, an identity base that does not resolve, and restrictions on an imported typedef raise `YangExportError` (`xyang convert` exit 2, nothing written). Tests: `tests/cases/modules/json-form-*`, `tests/json/test_native_json_imports.py`.
- ✅ **Types resolve where written** ([#152](https://github.com/exergy-connect/xYang/issues/152)): a `type`'s prefix and typedef name resolve in the module that wrote the `type`, so `type lx:item-ref` in an augment and `type l:port` in an imported grouping work; the native JSON form inlines a typedef of another module (restrictions on such a `type` are rejected rather than dropped). A leafref or instance-identifier behind a typedef is checked like a direct one.

### Comparisons
- ✅ `=`, `!=`, `<=`, `>=`, `<`, `>` - All comparison operators with proper type coercion

### XPath 2.0-style additions
xYang supports a small XPath 2.0–style extension so that **literal sequences** can appear on the right-hand side of equality, meaning “left equals any item in the sequence”:

- **Literal sequence syntax**: A parenthesized, comma-separated list of string or number literals is parsed as a single expression that evaluates to a **list** of those values:
  - `('integer', 'number')` → evaluates to `['integer', 'number']`
  - `(1, 2, 3)` → evaluates to `[1, 2, 3]`
  - Only **literals** are allowed inside the parentheses (no expressions or function calls). A single literal in parentheses, e.g. `('x')`, is also treated as a one-element sequence (a list).

- **Equality with a sequence**: When the right-hand side of `=` is a list (e.g. from a literal sequence), the result is **true** if the left-hand side equals **any** element of the list. This matches the intended reading of expressions like:
  - `(../../../fields[name = current()/field]/type) = ('integer', 'number')`  
  → true when the referenced `type` is `'integer'` or `'number'`.

Parsing rule: after `(`, if the next token is a string or number literal, the parser treats the construct as a literal sequence `( literal , literal , ... )`; otherwise it parses a normal parenthesized expression.

### Logical Operators
- ✅ `or` - Logical OR
- ✅ `and` - Logical AND

### Filtering and Predicates
- ✅ **Index predicates**: `[1]`, `[2]` - Access elements by 1-indexed position
- ✅ **Comparison predicates**: `[name = current()]`, `[type != 'array']` - Filter lists by field values
- ✅ **Complex predicates**: `[name = deref(current())/../foreignKey/field]` - Predicates with function calls
- ✅ **Navigation from predicates**: `fields[name = "x"]/type` - Navigate from filtered results

### Arithmetic Operations
- ✅ `+`, `-`, `*`, `div`, `mod` (numeric)

### Advanced Features
- ✅ **Nested deref()**: `deref(deref(current())/../foreignKey/entity)` - Multiple levels of dereferencing
- ✅ **Path navigation from nodes**: `deref(...)/../fields` - Navigate from dereferenced nodes
- ✅ **Leaf-list indexing**: `primary_key[1]` - Access first element of leaf-list
- ✅ **Type matching**: `deref(current())/../type = deref(...)/../fields[...]/type` - Complex type comparisons
- ✅ **Cross-entity validation**: Full support for validating foreign key relationships across entities

The XPath evaluator uses proper tokenization and AST-based parsing (not string-based), making it robust and maintainable. The implementation has been optimized and refactored for better performance and code organization.

### Path result caching

During document validation, path expression results are cached to avoid recomputing the same path. Only **absolute, cacheable** paths use the cache; relative and context-dependent paths are never cached.

- **Global cache**: If `Context.path_cache` is set (e.g. by the document validator), it is used as a single global cache for the run. There is no local cache per expression; each `eval(ast, ctx, node)` reads and writes directly to this cache when the path is cacheable.
- **Keys**: Path results are keyed by the path string from `path.to_string()` (e.g. `/top/flag`, `/top/items`). Stored value is the **node list** only.
- **Cacheability (static)**: Whether a path is cacheable is determined **during parsing**, not at evaluation time. The parser sets `PathNode.is_cacheable` to `False` when the path is relative or when any predicate uses context-sensitive constructs (e.g. `current()`, relative steps like `../flag`). Only when `path.is_absolute` and `path.is_cacheable` are both true does the evaluator look up or store in the cache. Relative paths are never cached because their result depends on the starting node.
- **Observability**: `XPathEvaluator.get_cache_stats()` returns `lookups`, `hits`, and `hit_ratio` for the current run. Call `clear_cache_stats()` at the start of each validation run so stats reflect that run only. Enable debug logging on `xyang.xpath.evaluator` to trace which path keys trigger each lookup, hit, and store.

## Error Reporting

xYang provides enhanced error reporting with line numbers and context:

### YANG Parser Errors
- **Line numbers**: Errors include the exact line number (1-indexed) where the error occurred
- **Context lines**: Shows surrounding lines with markers indicating the error line
- **Filename**: When parsing from a file, the filename is included in the error message
- **Example**:
  ```
  test.yang: 15: Expected '{' after module name 'test'
  >>>   15 | module test
        16 |   namespace "urn:test";
        17 |   prefix "test";
  ```

### XPath Parser Errors
- **Character position**: Errors include the exact character position in the expression
- **Expression context**: Shows a snippet of the expression around the error location
- **Pointer**: Visual pointer (^) indicates the exact error location
- **Example**:
  ```
  Expected PAREN_CLOSE, got EOF
  Expression: count(fields[type !=
                         ^
  Position: 23 (end of expression)
  ```

## Code Organization

The XPath implementation is organized in a modular architecture for better maintainability:

```
src/xyang/
├── __main__.py                  # CLI entry point (parse, validate, convert)
├── xpath/
│   ├── __init__.py              # Exports XPathEvaluator, Node, Context, SchemaNav, etc.
│   ├── evaluator.py             # Main XPath evaluator (orchestrator)
│   ├── tokenizer.py             # XPath expression tokenizer
│   ├── tokens.py                # Token type definitions
│   ├── parser.py                # Recursive descent parser (XPathParser)
│   ├── ast.py                   # AST node definitions
│   ├── node.py                  # Context and Node (data/schema cursor)
│   ├── schema_nav.py            # Schema navigation and leafref resolution (SchemaNav)
│   ├── functions.py             # XPath function implementations (FUNCTIONS)
│   └── utils.py                 # Utility functions (yang_bool, compare_*, etc.)
├── parser/                      # YANG parser
│   ├── yang_parser.py           # YANG file/module parsing
│   ├── tokenizer.py             # YANG tokenizer
│   ├── statement_parsers.py     # Statement-level parsers
│   └── parser_context.py        # Parser context
├── json/                        # JSON Schema export
│   ├── __init__.py              # generate_json_schema, schema_to_yang_json, parse_json_schema
│   ├── generator.py             # YANG AST → JSON Schema (with x-yang annotations)
│   └── parser.py                # JSON Schema → YANG AST (round-trip)
├── validator/                   # Validation engine
│   ├── yang_validator.py        # Top-level YANG validator
│   ├── document_validator.py    # Document/node validation (must, when, if-feature, leafref, …)
│   ├── if_feature_eval.py       # RFC 7950 if-feature boolean expressions + enabled-feature maps
│   ├── type_checker.py          # Type checking
│   ├── path_builder.py          # Path building utilities
│   └── validation_error.py      # Validation error types
├── uses_expand.py               # Expand `uses`, merge `when` / `if-feature` from uses into grouping roots
├── refine_expand.py             # Apply `refine`, copy schema subtrees (`copy_yang_statement` + `dataclasses.replace`)
├── identity_graph.py            # Identity derivation for `identityref` / `derived-from*()`
├── errors.py                    # Custom exception classes
├── ast.py                       # YANG AST node definitions
├── types.py                     # Type utilities
└── module.py                    # Module representation (`import_prefixes`, `feature_if_features`, …)
```

The modular architecture separates concerns:
- **evaluator**: Path evaluation, predicate filtering, and expression orchestration; manages context and Node cursor
- **schema_nav**: Schema navigation and leafref/deref resolution
- **functions**: Dictionary-based dispatch for XPath functions (e.g. `count`, `current`, `deref`)
- **utils**: Type-coercion aware comparisons (`compare_eq`, `compare_lt`, `compare_gt`), `yang_bool`, node-set helpers
- **parser / tokenizer / ast**: XPath expression parsing; **node**: Context and Node (data/schema cursor) for evaluation

## Limitations

- **XPath scope**: XPath 1.0 subset listed under *XPath Implementation*; no axes (`child::`, `following-sibling::`) or namespace nodes.
- **Error reporting**: In constraint validation the evaluator catches exceptions and returns `False` or `None`, so detailed error information is not surfaced to the caller.
- **Schema/document model**: The implementation is tied to the meta-model and document structure (e.g. schema-aware `Node`); it is not a general-purpose XPath 1.0 engine.

## Implementation notes

- **Leafref / deref**: `deref()` supports nested paths and cross-entity references: simple leafrefs (`deref(../entity)`), nested (`deref(deref(current())/../foreignKey/entity)`), relative paths, and entity/field lookups in the schema.
- **Performance**: The evaluator uses expression caching (short expressions), efficient context path handling, set-based operator lookups, and early returns where applicable.

## Test Coverage

Behavior is specified by the shared cases in `tests/cases/` (see `tests/cases/README.md`).
Known gaps are listed with `rg -n '"(python|ts)": "' tests/cases --glob case.json`.
