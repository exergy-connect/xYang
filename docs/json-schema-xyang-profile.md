# JSON Schema with `x-yang` extensions (xYang profile)

This document describes the **machine-readable schema shape** that xYang emits and consumes: **JSON Schema (draft 2020-12)** plus a reserved object property **`x-yang`** for YANG semantics that JSON Schema does not express. It is an **alternative to** reading the textual grammar in [`yang-ebnf-supported-constructs.md`](yang-ebnf-supported-constructs.md); both describe the same supported subset from different angles.

**Source of truth:** the implementation in `src/xyang/json/generator.py` (YANG → schema) and `src/xyang/json/parser.py` (schema → `YangModule`). When this document disagrees with the code, **the code wins**.

For CLI entry points, validation behavior, and feature checklist, see [`FEATURES.md`](../FEATURES.md). A large real example is [`examples/meta-model.yang.json`](../examples/meta-model.yang.json).

---

## Why JSON Schema + `x-yang`?

| Aspect | YANG + EBNF-style docs | JSON Schema + `x-yang` |
|--------|-------------------------|-------------------------|
| Audience | Human authors, RFC-shaped modules | Tools, IDEs, validators, code generators |
| Structure | Sequential text, statements | Nested objects, `$ref`, standard keywords |
| YANG-only rules | Grammar productions | `x-yang` carries metadata generic validators ignore |

The file is **valid JSON Schema** so off-the-shelf validators can check JSON instance shape and primitive types. **`x-yang`** is a custom property (JSON Schema allows extension keywords). Conformant validators **must ignore** unknown keywords, so they skip `x-yang` unless configured otherwise.

---

## Document identity and root object

Generated schemas include:

- **`$schema`**: `https://json-schema.org/draft/2020-12/schema`
- **`$id`**: module namespace (or a generated URN) — see `generate_json_schema()` in `generator.py`
- **`description`**: module-level description when present
- **`type`**: `"object"` at the root
- **`properties`**: top-level data nodes — one JSON property per module-level `container` / `list` / leaf / … (any identifier; `parse_json_schema` imports **all** x-yang–mapped root properties, not only `data-model`)
- **`additionalProperties`**: `false` at root (and on emitted object shapes where applicable)
- **`$defs`**: optional map of **typedef** names → schema fragments

---

## Root `x-yang` (module metadata)

The root object carries module identity and contact fields only in **`x-yang`** (not duplicated as standard JSON Schema keywords):

| Field | Meaning |
|-------|---------|
| `module` | Module name |
| `yang-version` | e.g. `"1.1"` |
| `namespace` | Module namespace URI string |
| `prefix` | Prefix string |
| `organization` | Optional |
| `contact` | Optional |

---

## Node-level `x-yang` (data schema)

For **container**, **list**, **leaf**, **leaf-list**, and leaves whose YANG type is **leafref**, the corresponding JSON Schema object includes **`x-yang`** with at least:

| `x-yang` field | Used on | Meaning |
|----------------|---------|---------|
| `type` | container / list / leaf-list | `"container"` \| `"list"` \| `"leaf-list"` |
| `type` | Ordinary leaf | `"leaf"` |
| `type` | Leaf with `type leafref` | `"leafref"` (merged from the leafref type schema; overrides the initial `"leaf"`) |
| `key` | `list` | List key string (YANG `key`) |
| `must` | When present | Array of `{ "must", "error-message", "description" }` (XPath strings) |
| `when` | When present | XPath condition string |
| `presence` | `container` | Presence string when the container is presence container |
| `choice` | `container` / `list` | When the choice is **hoisted**: `{ "name", "description" }` of the YANG `choice` (round-trip metadata) |
| `path`, `require-instance` | Leafref leaf | Leafref target path (string) and `require-instance` flag |

**`must` entries** mirror `must_stmt` + optional `error-message` and `description` substatements from YANG.

---

## Mapping YANG data nodes to JSON Schema

| YANG construct | JSON Schema shape | `x-yang.type` |
|----------------|-------------------|---------------|
| `container` | `type: "object"`, `properties`, optional `required`, `additionalProperties: false` | `"container"` |
| `list` | `type: "array"`, `items` = object schema for list entry | `"list"` |
| `leaf` | Type keywords on the same object as `x-yang` (or `$ref` to `$defs`); see **Leafref** below | `"leaf"` or `"leafref"` |
| `leaf-list` | `type: "array"`, `items` = item type schema | `"leaf-list"` |

**Cardinality:** `min-elements` / `max-elements` on list and leaf-list map to `minItems` / `maxItems` where set.

**Mandatory leaves:** `required` arrays on the parent **object** schema list mandatory child property names.

**Defaults:** Leaf `default` appears as JSON Schema `default` (string form as emitted by the generator).

---

## `choice` / `case` (hoisted into the parent object)

In YANG instance data there is **no node** for `choice` or `case` (and a container without `presence` does not add an extra semantic layer for the choice). Case leaves appear as **siblings** on the **parent container** (or list entry object).

When a container or list has **only** a `choice` as its child statement, the generator **hoists** the choice into that object:

- **No merged `properties`:** case leaves are **not** listed once at the parent; each alternative lives only inside its `oneOf` branch.
- **Mandatory choice:** `oneOf` with one branch per case; each branch is a full object schema: `type: "object"`, `properties` (only that case’s leaves), `required`, `additionalProperties: false`, on the **same** object as `x-yang.type: "container"` (or on list `items`).
- **Optional choice (≥2 cases):** `oneOf` whose first branch is `{ "type": "object", "maxProperties": 0 }` (empty instance), followed by the same per-case object branches as mandatory.

The parent container or list carries **`x-yang.choice`**: `{ "name": "<yang-choice-name>", "description": "<text>" }`, so round-trip parsing restores the real YANG `choice` identifier and its `description` (the hoisted JSON object has no `choice` data node).

If a container mixes a choice with other statements, the generator still emits a nested object keyed by the **choice** name (legacy shape) with `x-yang.type: "choice"` and `mandatory`; `parse_json_schema` supports that nested style as well.

See `tests/json/test_choice_cases.py` and `tests/json/test_issue_choice_flat_instance_json_schema.py`.

---

## Typedefs (`$defs`)

Each typedef becomes a **`$defs/<name>`** entry:

- JSON Schema fragment from the resolved base type (`pattern`, `enum`, `minimum` / `maximum`, etc.)
- `"x-yang": { "type": "typedef" }`
- `description` from the typedef when present

Leaves that use a typedef reference it with `"$ref": "#/$defs/<typedef-name>"` while keeping **`x-yang.type": "leaf"`** on the leaf node (unless the leaf is a leafref; then **`x-yang.type`** is **`"leafref"`** as above).

Inside a typedef definition, nested `$ref` to other typedefs is avoided in the generator (`typedef_names` empty in `_typedef_to_def`).

---

## Built-in YANG types → JSON Schema (and extra keywords)

| YANG `type` | JSON Schema (typical) | Notes |
|-------------|------------------------|--------|
| `string` | `type: "string"`, optional `pattern`, `minLength`, `maxLength` | Pattern may be anchored with `^` / `$` in output |
| `enumeration` | `type: "string"`, `enum: [...]` | Empty enumeration is rejected at YANG parse time |
| `boolean` | `type: "boolean"` | |
| `int8` … `uint64` | `type: "integer"`, optional `minimum` / `maximum` | Fixed bounds for `uint8`; `range` parsed when present |
| `decimal64` | `type: "number"`, `multipleOf`: `10^-n` (e.g. `0.01` for `fraction-digits` 2) | Legacy `x-fraction-digits` is still accepted on read |
| `empty` | `type: "object"`, `maxProperties: 0` | |
| `union` | `oneOf: [ ... ]` | One schema per member type |
| `leafref` | `type: "string"` | **`x-yang`** on the **leaf** merges `type: "leafref"`, `path`, `require-instance` |

Leafref path is stored as a string (`PathNode.to_string()` when parsed from YANG). Resolving references is **not** a JSON Schema concern; xYang’s validator uses this metadata.

---

## Round-trip and tooling

- **Produce:** `generate_json_schema(module)` or `schema_to_yang_json(module, output_path=...)` after parsing YANG (`YangParser`).
- **Consume:** `parse_json_schema(data)` rebuilds a `YangModule` where supported.
- **CLI:** `xyang convert <file.yang> [-o path]` writes `*.yang.json`.

The convert path uses `YangParser(expand_uses=False)` so **grouping / uses** are expanded when emitting JSON, matching the flattened AST the generator walks.

**Parser scope today:** `parse_json_schema` only reconstructs module **data** statements from a root **`properties.data-model`** object (the `meta-model` / xFrame profile). Other top-level property names are ignored until the parser is generalized. Hand-authored or converted schemas meant for round-trip through `parse_json_schema` should use that root container name.

---

## Parity with the EBNF document

Concepts documented in [`yang-ebnf-supported-constructs.md`](yang-ebnf-supported-constructs.md) (module header, typedef, type restrictions, grouping/uses/refine behavior after expansion, container/list/leaf/leaf-list, must/when, choice/case) have a corresponding representation in this JSON profile **after** parse and optional `uses` expansion.

Constructs **outside** xYang’s parser (imports, augment, RPC, etc.) do not appear in either profile until implemented.

---

## Maintenance

When changing JSON output or parser expectations:

1. Update `generator.py` / `parser.py` and tests under `tests/json/`.
2. Update this document for any new `x-yang` keys or layout changes.
3. Keep [`yang-ebnf-supported-constructs.md`](yang-ebnf-supported-constructs.md) aligned for the textual grammar side.
