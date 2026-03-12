# LOC and code complexity: native YANG parser vs JSON/YANG parser

This document compares **lines of code (LOC)** and **structural complexity** between the two ways to obtain a YANG schema AST in xYang:

1. **Native YANG parser** — parses `.yang` source (text) into a `YangModule` AST.
2. **JSON/YANG parser** — parses `.yang.json` (JSON Schema with x-yang annotations) into the same `YangModule` AST.

Both outputs feed the same validation pipeline (`YangValidator`, `DocumentValidator`, XPath, type checker). The comparison is about the **parsing path only**, not validation.

## Summary

| Metric | Native YANG parser | JSON/YANG parser |
|--------|-------------------|------------------|
| **LOC (parser only)** | **1,414** | **474** |
| **LOC (including shared AST + module)** | **1,643** | **703** |
| **Files** | 6 | 1 |
| **Classes** | 8 | 0 |
| **Top-level functions** | 2 | 14 |
| **Statement/context types** | Token stream, context, registry, 45+ parse methods | Dict walk + helpers |
| **Input format** | YANG 1.1 text | JSON (pre-flattened schema) |

The JSON parser is **~3× fewer LOC** (parser-only) and **single-file** with no lexer or grammar layer.

---

## Lines of code

### Native YANG parser

| File | LOC | Role |
|------|-----|------|
| `parser/statement_parsers.py` | 745 | One parse method per statement kind (module, container, list, leaf, leaf-list, typedef, grouping, uses, refine, choice, case, type, must, when, key, …). |
| `parser/parser_context.py` | 243 | Token types, `Token`, `YangToken`, `TokenStream`, `ParserContext` (current statement stack, expectations). |
| `parser/yang_parser.py` | 219 | `YangParser`: registry setup, driver, uses-expansion hook, `parse_file` / `parse_string`. |
| `parser/tokenizer.py` | 167 | `YangTokenizer`: lexer for YANG keywords, identifiers, strings, numbers, braces, semicolons. |
| `parser/statement_registry.py` | 29 | `StatementRegistry`: map (parent, statement_name) → parse function. |
| `parser/__init__.py` | 11 | Re-exports. |
| **Subtotal (parser)** | **1,414** | |
| `ast.py` | 192 | Shared AST node types (container, list, leaf, leaf-list, typedef, type, must, when, uses, …) plus shared parsed XPath storage for `must`/`when`. |
| `module.py` | 37 | `YangModule` (name, namespace, prefix, typedefs, statements). |
| **Total (parser + shared)** | **1,643** | |

### JSON/YANG parser

| File | LOC | Role |
|------|-----|------|
| `json/parser.py` | 474 | Load JSON, resolve `$ref`/`allOf`, map properties + `x-yang` to AST nodes, build `YangModule`. Also feeds `must`/`when` expressions into the shared XPath parser. |
| **Subtotal (parser)** | **474** | |
| Shared `ast.py` + `module.py` | 229 | Same as above (both parsers produce the same AST). |
| **Total (parser + shared)** | **703** | |

### Shared components (counted once)

- **`ast.py`** (192 LOC): Defines `YangContainerStmt`, `YangListStmt`, `YangLeafStmt`, `YangLeafListStmt`, `YangTypedefStmt`, `YangTypeStmt`, `YangMustStmt`, `YangWhenStmt`, and related nodes, plus a shared base that parses and caches XPath for `must`/`when`. Used by **both** parsers and by the validator.
- **`module.py`** (37 LOC): `YangModule` (name, namespace, prefix, typedefs, statements). Same for both.

---

## Structural complexity

### Native YANG parser

- **Pipeline:** Source text → **tokenizer** (lexer) → **token stream** → **parser** (registry-driven recursive descent) → **AST**.
- **Layers:**
  1. **Lexer** (`tokenizer.py`): Character-level scanning; emits tokens (keyword, identifier, string, number, `{`, `}`, `;`, etc.).
  2. **Context** (`parser_context.py`): Token stream abstraction, `ParserContext` with current module and statement stack for error reporting and expectations.
  3. **Registry** (`statement_registry.py`): Maps (parent_statement, child_statement_name) to a handler function (e.g. `module:container` → `parse_container`).
  4. **Statement parsers** (`statement_parsers.py`): **45+ methods** (one per YANG statement or sub-statement). Handles grammar rules, nesting, grouping/uses/refine, choice/case, type constraints, must/when, etc.
  5. **Driver** (`yang_parser.py`): Creates tokenizer + registry + parsers, drives parse, optionally runs **uses expansion** after parse.
- **Complexity drivers:**
  - Full YANG 1.1 grammar (keywords, nesting, grouping/uses/refine, choice/case).
  - Uses expansion can be done in parser (default) or deferred to JSON generator; either way the native path must understand grouping/uses/refine.
  - Error reporting (line numbers, context) ties into token positions and context stack.
  - Many statement-specific branches and type-building (type, range, pattern, length, leafref path, etc.).

### JSON/YANG parser

- **Pipeline:** JSON (file / string / dict) → **dict walk** + **$ref/allOf resolution** → **property + x-yang mapping** → **AST**.
- **Structure:**
  - **Single entry point:** `parse_json_schema(source)`.
  - **Helpers:** `_get_xyang`, `_ref_to_typedef_name`, `_resolve_schema` (for `$ref` and `allOf`), `_type_from_schema`, `_build_typedef`, `_build_must_list`, `_property_schema_and_xyang`, `_convert_container`, `_convert_list`, `_convert_leaf`, `_convert_leaf_list`, `_convert_property`.
  - **No lexer:** Input is already a Python dict (from `json.load`).
  - **No grammar:** Structure is fixed: root has `x-yang`, `properties`, `$defs`; `data-model` container holds the top-level statements; each node has JSON Schema keys plus `x-yang` (type, key, must, leafref path, etc.).
- **Complexity drivers:**
  - Mapping JSON Schema types + x-yang into AST (string, integer, enum, leafref, $ref to typedefs, oneOf for union).
  - Resolving `$ref` and `allOf` so nested and reused definitions become a single resolved schema before conversion.
- **Greatly simplified grouping/uses/refine/choice/case handling** in the JSON path: the `.yang.json` format is produced by the **generator**, which can expand or normalize these constructs at emit time, so the JSON parser mostly sees an already-structured schema and does not need to mirror the full native YANG grammar.

---

## Why the JSON path is smaller

1. **No lexer:** No character-level tokenizer; input is parsed by the standard library (`json.load`).
2. **No grammar layer:** No token stream, no statement registry, no 45+ statement-specific parse methods. The “grammar” is the shape of the JSON (properties, $defs, x-yang).
3. **Flattened schema:** Grouping/uses/refine and choice/case are handled when **emitting** `.yang.json` (in `json/generator.py`); the JSON parser only consumes the result. So it doesn’t need grouping expansion, refine, or choice/case parsing.
4. **Single responsibility:** One file: “given this dict, produce a `YangModule`.” No separate context, token types, or registry.

The **generator** (`json/generator.py`, ~467 LOC) does the heavy work of turning a YANG AST (possibly with uses) into the hybrid JSON Schema. So the total “YANG ↔ JSON schema” path is: **native parser (1,414) + generator (467)** vs **JSON parser (474)** for the read direction only. If you already have `.yang.json`, loading it is 474 LOC; if you start from `.yang`, you use the native parser (and optionally the generator to produce `.yang.json` for other tools).

---

## When to use which

| Use case | Preferred path |
|----------|----------------|
| Schema authored in YANG (`.yang`) | Native parser (`parse_yang_file` / `parse_yang_string`). |
| Schema authored or exported as `.yang.json` | JSON parser (`parse_json_schema`). |
| Tooling that only understands JSON Schema | Generate `.yang.json` with `schema_to_yang_json` (generator); they ignore `x-yang`. |
| Round-trip YANG → JSON → AST | Parse YANG with `expand_uses=False`, run generator, then `parse_json_schema` on the result (see `tests/json/test_generator.py`). |
| Validation | Same `YangValidator` and pipeline for both; only the way the AST is built differs. |

---

## Related

- **Data flow:** `docs/dataflow.md` — how schema (from either parser) and instance data flow through validation.
- **YANG.json format:** `FEATURES.md` — section “YANG.json hybrid format” describes the JSON Schema + x-yang structure the JSON parser consumes.
- **Generator:** `src/xyang/json/generator.py` — YANG AST → `.yang.json`; handles uses expansion when emitting.
