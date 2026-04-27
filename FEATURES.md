# xYang Feature Set

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

### Type Definitions
- ✅ `typedef` - Type definitions (heavily used)
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
- ✅ `grouping` - Grouping statements (defines reusable schema components)
- ✅ `uses` - Uses statements (incorporates groupings)
- ✅ `refine` - Refine statements (modifies nodes from groupings)

### Instance data encodings
- ✅ **JSON ([RFC 7951](https://www.rfc-editor.org/rfc/rfc7951))** — Validators consume dict/list instance trees in this shape. Core helper ``xyang.encoding.resolve_qualified_top_level`` (``encoding/rfc7951.py``) maps a namespace-qualified object member ``module-name:node`` to a top-level schema node in that module (used for optional anydata subtree validation and reusable elsewhere).
- ⚠️ **XML** ([RFC 7950](https://www.rfc-editor.org/rfc/rfc7950) XML encoding) — Not supported yet for instance validation or qualified-name resolution.
- ⚠️ **Binary encodings** (e.g. [RFC 9254](https://www.rfc-editor.org/rfc/rfc9254) CBOR) — Not supported yet.

### Constraints
- ✅ `must` - Must constraints (19 `must "` substatements) - **Parsed and evaluated**
  - Supports must constraints on containers, lists, leaves, leaf-lists, `anydata`, and `anyxml`
  - Supports must constraints on lists containing leafref types
  - `current()` correctly refers to list item context in list must constraints
- ✅ `when` - When conditions — **Parsed and evaluated** on every RFC 7950 parent the parser supports for **data nodes**: `container`, `leaf`, `leaf-list`, `list`, `anydata`, `anyxml`, `choice`, `case`, and `uses` (not on `refine`). `augment` accepts `when` in the parse tree, but augment targets are **not** merged into the instance-validation schema (see **Features NOT Implemented**).
- ✅ `if-feature` - **Parsed** on `container`, `leaf`, `leaf-list`, `list`, `choice`, `case`, `uses`, `refine`, `augment`, `identity`, and braced `feature`; **boolean expressions** (`and` / `or` / `not`, parentheses, `prefix:feature`) evaluated for **document validation** via `DocumentValidator(..., enabled_features_by_module=...)`. `uses` / `refine` `if-feature` values are ANDed onto expanded grouping nodes; `copy_yang_statement` preserves `if_features` through `uses` expansion. Feature-level `if-feature` substatements prune `build_enabled_features_map()` (RFC 7950 §7.20.1). **Not** emitted in JSON Schema `x-yang` yet.
- ✅ `mandatory` - Mandatory fields (16 occurrences)
  - Supports mandatory on choice statements (exactly one case must be present)
- ✅ `default` - Default values (7 occurrences)
- ✅ `min-elements` - Minimum elements (5 occurrences)
- ✅ `max-elements` - Maximum elements (1 occurrence)
- ✅ `key` - List keys (heavily used)

### Type Constraints
- ✅ `pattern` - Pattern matching (6 occurrences); **multiple** patterns and **`modifier invert-match`** per RFC 7950, with per-pattern error metadata. JSON Schema: top-level `pattern` when a single non-inverted regex suffices; otherwise `allOf` / `not` plus **`x-yang.string-patterns`** for round-trip (Python and `ts/`).
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

### CLI and JSON Schema Export
- ✅ **CLI** (`xyang` or `python -m xyang`): `parse`, `validate`, `convert`
  - `xyang parse <file.yang>` — parse and print module info
  - `xyang validate <file.yang> [data.json]` — validate JSON (file or stdin) against the module
  - `xyang convert <file.yang> [-o path]` — convert .yang to JSON Schema (output path always ends with `.yang.json`)
- ✅ **JSON Schema generator**: YANG AST → JSON Schema (draft 2020-12) with `x-yang` annotations
  - `generate_json_schema(module)`, `schema_to_yang_json(module, output_path=...)`
  - Parse with `YangParser(expand_uses=False)` so the AST keeps original `uses` and `augment` structure; the generator expands `uses` when emitting. That split keeps **YANG ↔ JSON Schema** conversion reversible where `x-yang` carries the source shape.
  - Round-trip: parse YANG → generate JSON → parse JSON schema → equivalent AST where supported

## Features NOT Implemented

All RFC 7950 built-in type **names** are reserved as lexer keywords (see **Built-in Types** above), even when validation or JSON Schema support is incomplete.

### Partial / syntax only
- ⚠️ **`augment`** — Parsed into `YangAugmentStmt` (including `if-feature`, `when`, `must`, nested data definitions). With `YangParser(expand_uses=True)`, augments are resolved and merged into the target module (same gate as `uses` expansion). With `expand_uses=False`, augments stay as statements for reversible convert. **JSON Schema** emission today still does not walk merged augment semantics end-to-end for every case; validate with an expanded module when you need full augmented-tree checks.

### Not implemented (skipped when parsing)
- ⚠️ `deviation`, `rpc`, `action`, `notification`, `input`, `output` — **Lexically recognized** and **skipped** (full statement including braced body) after a **`logging` warning**; they are **not** represented in the AST, validation, or JSON Schema. Lets mixed modules parse past these constructs.

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
- **Parents** (parsed, with validation where the node participates in the data tree): `container`, `leaf`, `leaf-list`, `list`, `choice`, `case`, `uses` (merged into expanded nodes), `refine` (merged into refine targets). `augment` and `identity` store expressions in the AST for tooling; instance validation does not yet walk augment-applied schema.

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
The `refine` statement allows modifying nodes from a grouping when using it. This is particularly useful for adding constraints or changing properties. Supported substatements include **`default`** (for `leaf` and `leaf-list` targets). Multiple `default` lines under one `refine` build the leaf-list default set; the merged values are emitted in JSON Schema as **`default`** (scalar for a leaf, **array** for a leaf-list, matching draft 2020-12). Refine may add **`if-feature`** expressions, which are appended to the target node’s `if_features` (AND with any existing conditions).

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

- **Root**: Standard `$schema`, `$id`, `description`, `type`, `properties`, `additionalProperties`, and optional `$defs` (typedefs). A root **`x-yang`** object holds module metadata: `module`, `yang-version`, `namespace`, `prefix`, `organization`, `contact`.
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
- ✅ `translate(., '_', '')` - Translate/remove characters
- ✅ `contains(string1, string2)` - Check if string1 contains string2
- ✅ `substring-before(string1, string2)` - Get substring before first occurrence of string2
- ✅ `substring-after(string1, string2)` - Get substring after first occurrence of string2
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

### String Operations
- ✅ **String concatenation**: `+` operator for string concatenation
- ✅ **String functions**: `contains()`, `substring-before()`, `substring-after()` for string manipulation and pattern matching

### Arithmetic Operations
- ✅ `+`, `-`, `*`, `/` - Arithmetic operators (with `/` treated as path navigation when appropriate)

### Advanced Features
- ✅ **Nested deref()**: `deref(deref(current())/../foreignKey/entity)` - Multiple levels of dereferencing
- ✅ **Path navigation from nodes**: `deref(...)/../fields` - Navigate from dereferenced nodes
- ✅ **Leaf-list indexing**: `primary_key[1]` - Access first element of leaf-list
- ✅ **Type matching**: `deref(current())/../type = deref(...)/../fields[...]/type` - Complex type comparisons
- ✅ **Cross-entity validation**: Full support for validating foreign key relationships across entities

The XPath evaluator uses proper tokenization and AST-based parsing (not string-based), making it robust and maintainable. The implementation has been optimized and refactored for better performance and code organization.

### Path result caching

During document validation, path expression results are cached to avoid recomputing the same path. Only **absolute, cacheable** paths use the cache; relative and context-dependent paths are never cached.

- **Global cache**: If `Context.path_cache` is set (e.g. by the document validator), it is used as a single global cache for the run. There is no per-expression local cache; each `eval(ast, ctx, node)` reads and writes directly to this cache when the path is cacheable.
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

- **Augment**: Augment statements are parsed but **not** merged into the schema used for instance validation or JSON Schema generation for remote targets.
- **If-feature in JSON Schema**: Hybrid `.yang.json` does not yet carry `if-feature` under `x-yang`; use `DocumentValidator` with `enabled_features_by_module` for conditional validation.
- **XPath scope**: Only the XPath features used in `meta-model.yang` are implemented. Unsupported: axes (e.g. `child::`, `following-sibling::`), namespaces, and more complex location paths.
- **Error reporting**: In constraint validation the evaluator catches exceptions and returns `False` or `None`, so detailed error information is not surfaced to the caller.
- **Expression caching**: Caching is per-expression (local cache per `eval()`); path results that depend on `current()` or similar in predicates are not retained (purged after the expression).
- **Schema/document model**: The implementation is tied to the meta-model and document structure (e.g. schema-aware `Node`); it is not a general-purpose XPath 1.0 engine.

## Implementation notes

- **Leafref / deref**: `deref()` supports nested paths and cross-entity references: simple leafrefs (`deref(../entity)`), nested (`deref(deref(current())/../foreignKey/entity)`), relative paths, and entity/field lookups in the schema.
- **Performance**: The evaluator uses expression caching (short expressions), efficient context path handling, set-based operator lookups, and early returns where applicable.

## Usage Statistics from meta-model.yang

Counts below are from `examples/meta-model.yang`, using **line-initial** YANG keywords (or `type <keyword>`) so prose inside multi-line `description` strings is excluded. **`must`** is counted as lines matching `must "` (opening quoted expression).

- `must`: 19
- `default`: 7
- `mandatory`: 16
- `pattern`: 6
- `length`: 3
- `type enumeration` (typedef bodies): 6
- `type leafref`: 7
- `type union`: 3 (fully supported in typedefs)
- `min-elements`: 5
- `case`: 7
- `choice`: 2
- `type decimal64`: 3
- `fraction-digits`: 3
- `when`: 3
- `presence`: 1
- `max-elements`: 1
- `range`: 2

## Test Coverage

The suite currently has **310 passing tests** (`python3 -m pytest tests/`), including:
- Basic YANG parsing and validation
- Type validation (including enumeration)
- Constraint validation (must, when, if-feature, mandatory, default)
- Leafref resolution and validation
- Deref() function with nested calls
- Grouping and uses statements (including nested groupings, refine, `when` / `if-feature` on `uses` and `refine`)
- Choice/case statements (including `if-feature` on choice/case)
- Union types in typedefs
- Unknown field detection
- XPath expression evaluation
- Foreign key validation
- Parent-child relationship validation
- Must constraints on leafref lists
- Current context preservation in predicates
- Relative and absolute path resolution
- **Import / include / submodule** patterns (`tests/test_yangson_ex3_import.py` and related fixtures under `tests/data/yangson-ex3/`)
- **If-feature** parsing, evaluation, and validation (`tests/test_if_feature.py`)
- JSON schema generator (YANG → JSON Schema, round-trip; `tests/json/test_generator.py`)

## Recent Improvements

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
- ✅ **XPath string functions**: Added support for additional XPath 1.0 string functions
  - `contains(string1, string2)` - Check if string1 contains string2
  - `substring-before(string1, string2)` - Get substring before first occurrence of string2
  - `substring-after(string1, string2)` - Get substring after first occurrence of string2
  - All functions follow XPath 1.0 semantics with proper string conversion

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
