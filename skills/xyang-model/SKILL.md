---
name: xyang-model
description: Author or edit YANG modules and x-yang JSON Schema (.yang.json) models validated by xYang. Use when writing .yang, generating or hand-editing *.yang.json, validating instance JSON, leafref/identityref/instance-identifier, must/when, or JSON Schema x-yang annotations.
---

# xyang-model

Author **YANG 1.1 modules** (`.yang`) and/or **JSON Schema with `x-yang`** (conventional suffix **`.yang.json`**) that [xYang](https://github.com/exergy-connect/xYang) can parse, convert, and use to validate JSON instance data.

Prefer **textual YANG first**, then **`xyang convert`** to produce JSON Schema—fewer mistakes than hand-writing `x-yang` trees.

## When to use

- User wants a **data model** as YANG or as **JSON Schema + `x-yang`** compatible with xYang.
- User mentions **xYang**, **`.yang.json`**, **`x-yang`**, **validate** against a module, **leafref**, **identityref**, **instance-identifier**, **must**, **when**, **grouping** / **uses**, or **meta-model**-style schemas.
- Editing **`examples/meta-model.yang`** or schemas derived from it (e.g. xFrame consolidation inputs).

## Validate your work

From the xYang repo (or an environment with `xyang` / `pip install -e .`):

```bash
# Parse YANG (syntax + supported semantics)
xyang parse path/to/module.yang

# YANG → JSON Schema (draft 2020-12 + x-yang); output name should end with .yang.json
xyang convert path/to/module.yang -o path/to/module.yang.json

# Validate instance JSON against the module
xyang validate path/to/module.yang path/to/data.json
```

Without installing: `PYTHONPATH=src python3 -m xyang …` from the xYang repo root.

Python API: `parse_yang_string`, `parse_yang_file`, `YangValidator`, `xyang.json.generate_json_schema`, `xyang.json.parse_json_schema` (see repo `README.md`).

## Authoritative references (this repo)

| Topic | Location |
|--------|-----------|
| Supported YANG / CLI / feature checklist | `FEATURES.md` |
| JSON Schema + `x-yang` shape (emit & parse) | `docs/json-schema-xyang-profile.md` |
| Supported textual grammar (EBNF-style) | `docs/yang-ebnf-supported-constructs.md` |
| Large real YANG example | `examples/meta-model.yang` |
| Generated JSON Schema example | `examples/meta-model.yang.json` |

## Design rules for **valid xYang models**

1. **Self-contained modules** — `import` / `include` / `augment` are **not** implemented; keep one module per file for tooling.
2. **Instance data keys** match **leaf**, **container**, **list**, and **choice case** names under the schema tree (no `choice` / `case` keys in JSON).
3. **Leafref** — `type leafref { path "…"; }` with absolute or relative paths as supported; instance validation resolves targets. JSON: `x-yang.type: "leafref"`, `path`, `require-instance` on the leaf (see profile doc).
4. **Identity / identityref** — identities and `identityref` with `base` are supported; JSON uses `$defs` and `x-yang` for bases (see profile doc).
5. **instance-identifier** — string path; with `require-instance true`, xYang expects an **absolute** path (`/…`) that resolves in the instance (see `FEATURES.md`).
6. **when** — if a `when` is false, omit instance data for that branch; presence when false is invalid.
7. **must** — XPath must be expressible by xYang’s XPath subset; test with `xyang validate`.
8. **JSON round-trip** — not every construct round-trips through JSON Schema; prefer **`xyang convert`** from YANG for a canonical `.yang.json`.

## Workflow A: YANG-first (recommended)

1. Start from `assets/minimal-module.yang` (or the matching JSON Schema `assets/minimal-module.yang.json`, produced by `xyang convert` from that YANG), **`assets/netlab-topology.yang`** (nodes, links with **leafref** + **must** for no self-loops, services with **instance-identifier** paths to nodes), or `examples/meta-model.yang`.
2. Run `xyang parse` until clean.
3. Run `xyang convert … -o …yang.json` for JSON Schema consumers.
4. Run `xyang validate` with representative instance JSON.

## Workflow B: JSON Schema + `x-yang` (advanced)

1. Read **`docs/json-schema-xyang-profile.md`** end-to-end.
2. Root object: `$schema`, `$id`, `type: object`, `properties` for each **top-level** data node; each property that is part of the module needs a recognizable **`x-yang`** (`container`, `list`, `leaf`, `leaf-list`, `choice`).
3. Module metadata lives in **root `x-yang`**: `module`, `yang-version`, `namespace`, `prefix`, etc.
4. Use **`$defs`** for typedefs and identities as described in the profile doc.
5. Call **`parse_json_schema`** in Python or rely on tools that emit the same shape; then **`xyang validate`** using the round-tripped module if you export back to YANG, or validate via the API.

## Unsupported (do not use in models meant for xYang)

See **`FEATURES.md` § “Features NOT Implemented”** (e.g. `import`, `augment`, `bits`, …). Built-in type **names** may lex as keywords even when validation is incomplete—stick to documented combinations.

## After authoring

- **Parse + validate** before committing.
- For xFrame pipelines, the **meta-model** shape still originates from YANG / `meta-model.yang.json`; this skill aligns with that contract.

## References

- Minimal starter pair: `skills/xyang-model/assets/minimal-module.yang` and **`skills/xyang-model/assets/minimal-module.yang.json`** (same module; JSON is the `xyang convert` output).
- **Netlab-style topology** (referential integrity): `assets/netlab-topology.yang`, **`assets/netlab-topology.yang.json`**, and sample instance **`assets/netlab-topology-instance.json`**. Try:
  - `xyang validate skills/xyang-model/assets/netlab-topology.yang skills/xyang-model/assets/netlab-topology-instance.json`
  - Break integrity: set a link’s `source` and `target` to the same node (must on `links`), or set `services/runs-on` to a bad path or a path that does not exist (e.g. wrong `name` in a predicate) (**instance-identifier** with `require-instance`).
- Tests for JSON parity: `tests/json/` in the xYang repo
