# YANG EBNF: constructs supported by xYang

This document describes the **YANG 1.1–shaped subset** that the xYang parser accepts. It is derived from the implementation in `src/xyang/parser/` (`yang_parser.py` statement registry, `statement_parsers.py`, `tokenizer.py`, `parser_context.py`).

The repository root file [`meta-model-grammar.ebnf`](../meta-model-grammar.ebnf) is an older, minimal EBNF aimed at the xFrame `meta-model.yang` profile. **When the two differ, the running code wins**; the EBNF below is meant to track what xYang actually parses.

For feature semantics (validation, JSON Schema, XPath), see [`FEATURES.md`](../FEATURES.md).

---

## Lexical structure

Comments are removed before tokenization: `//` to end of line, and `/* … */` block comments.

```ebnf
(* Whitespace separates tokens; not explicit in productions below. *)

STRING       = '"' { escaped-char | any-except-"-and-\ } '"'
             | "'" { escaped-char | any-except-'-and-\ } "'" ;

(* Integer: optional leading '-', digits only — used where grammar expects INTEGER *)
INTEGER      = [ "-" ] digit { digit } ;

(* Unquoted dotted decimal (RFC 7950 ``yang-version`` argument ``1.1`` — not an ``identifier``). *)
DOTTED_NUMBER = digit { digit } "." digit { digit } ;

(* Identifiers and reserved words: RFC 7950 / YANG 1.1 ``identifier`` *)
identifier   = ( ALPHA / "_" ) *( ALPHA / DIGIT / "_" / "-" / "." ) ;

(* Keywords are reserved lexemes mapped to keyword tokens (see list below). *)
keyword      = "module" | "yang-version" | "namespace" | "prefix" | "organization" | "contact"
             | "description" | "revision" | "typedef" | "type" | "union" | "leafref" | "path"
             | "require-instance" | "enum" | "enumeration" | "string" | "pattern" | "length"
             | "int32" | "uint8" | "decimal64" | "fraction-digits" | "range" | "grouping"
             | "uses" | "refine" | "container" | "list" | "leaf" | "leaf-list" | "choice" | "case"
             | "must" | "when" | "presence" | "key" | "min-elements" | "max-elements"
             | "mandatory" | "default" | "error-message" | "true" | "false" ;

punctuation  = "{" | "}" | ";" | "=" | "+" | "/" ;
```

**Notes:**

- The first character of an `identifier` must be **A–Z, a–z, or `_`**; inner `-` and `.` match RFC 7950.
- Digit-led lexemes are **`INTEGER`** or **`DOTTED_NUMBER`** (e.g. `yang-version 1.1;`), never `IDENTIFIER`.
- Built-in type names that are **not** keywords (e.g. `boolean`) are tokenized as ordinary identifiers when used after `type`.
- `+` concatenates adjacent string literals in `must` and `when` arguments (see `_parse_string_concatenation`).

---

## Module

The file **must** begin with a single `module` statement (no `submodule`, `import`, or `include`).

```ebnf
yang_file     = module_stmt ;

module_stmt   = "module" identifier "{" module_body "}" [ ";" ] ;

module_body   = { module_stmt_item } ;

module_stmt_item
              = yang_version_stmt | namespace_stmt | prefix_stmt | organization_stmt
              | contact_stmt | description_stmt | revision_stmt
              | typedef_stmt | grouping_stmt
              | container_stmt | list_stmt | leaf_stmt | leaf_list_stmt | choice_stmt ;
```

### Module metadata

```ebnf
yang_version_stmt   = "yang-version" ( identifier | DOTTED_NUMBER ) [ ";" ] ;
namespace_stmt      = "namespace" STRING [ ";" ] ;
prefix_stmt         = "prefix" STRING [ ";" ] ;
organization_stmt   = "organization" STRING [ ";" ] ;
contact_stmt        = "contact" STRING [ ";" ] ;

revision_stmt       = "revision" revision_date [ ";" ]
                    | "revision" revision_date "{" { description_stmt } "}" [ ";" ] ;
revision_date       = STRING | identifier ;   (* unquoted dates must be a single token *)

description_stmt    = "description" STRING [ ";" ] ;
```

**Limitation:** xYang only supports the **flat** `description` form (`description "..." ;`). The YANG 1.1 style with a braced sub-statement is **not** implemented.

---

## Typedef

```ebnf
typedef_stmt  = "typedef" identifier "{" typedef_body "}" [ ";" ] ;

typedef_body  = { type_stmt | description_stmt } ;
```

The body must include a `type` statement (enforced by validation usage patterns in practice).

---

## Type statement and built-in / derived shapes

`type` is parsed once per leaf/typedef/union member; an optional braced block holds restrictions.

```ebnf
type_stmt     = "type" type_name [ "{" type_body "}" ] [ ";" ] ;

(* type_name: typedef identifier, or a built-in type keyword from the lexer — e.g. string, int32,
   union, leafref, enumeration, decimal64. Names like boolean are plain identifiers, not keywords. *)
type_name     = identifier ;

type_body     = { type_substmt } ;

type_substmt  = "type" type_stmt              (* union member types, including nested leafref *)
              | "enum" identifier [ ";" ]
              | "pattern" STRING [ ";" ]
              | "length" ( STRING | identifier ) [ ";" ]
              | "range" STRING [ ";" ]
              | "fraction-digits" INTEGER [ ";" ]
              | "path" STRING [ ";" ]
              | "require-instance" ( "true" | "false" ) [ ";" ]
              | description_stmt ;
```

**Supported type names** (after `type`) include at least:

- Keywords wired in the tokenizer / parser: `string`, `int32`, `uint8`, `boolean` is **not** a keyword — use identifier `boolean`, `union`, `leafref`, `enumeration`, `decimal64`.
- Typedef names: any identifier resolving to a `typedef` in the module.

**Union:** `type union {` … one or more nested `type … ;` members … `}`.

**Leafref:** `type leafref { "path" STRING ; [ "require-instance" ( "true" | "false" ) ; ] }`.

**Enumeration:** `type enumeration {` zero or more `enum` **identifier** `;` … `}` (optional per-enum description blocks are not expanded in the EBNF here; the parser accepts `enum` name then `;`).

**String:** optional `{ length … ; pattern … ; description … }`.

**Numeric:** `int32` / `uint8` with optional `{ range STRING ; }`; `decimal64` with required `{ fraction-digits INTEGER ; }`.

**Unknown braced content:** Inside a non-union `type` block, nested `{` / `}` that are not recognized at the top level may be skipped by the parser (legacy tolerance). Prefer the explicit substmts above.

---

## Grouping, uses, refine

```ebnf
grouping_stmt = "grouping" identifier "{" grouping_body "}" [ ";" ] ;

grouping_body = { grouping_body_stmt } ;

grouping_body_stmt
              = description_stmt | choice_stmt
              | container_stmt | list_stmt | leaf_stmt | leaf_list_stmt
              | uses_stmt ;

uses_stmt     = "uses" identifier [ "{" uses_body "}" ] [ ";" ] ;

uses_body     = { refine_stmt | description_stmt } ;

refine_stmt   = "refine" refine_target "{" refine_body "}" [ ";" ] ;

refine_target = identifier ;   (* single token: e.g. "type"; slash-paths are not multi-token targets *)

refine_body   = { refine_body_item } ;

refine_body_item
              = type_stmt
              | must_stmt
              | description_stmt ;
(* Additionally, "default" … is accepted in the refine block but only skipped — not stored on the AST. *)
```

`refine` may also encounter a `default` statement; the parser consumes it but does not attach a structured default to the refine AST (see `parse_refine` in `statement_parsers.py`).

By default, `YangParser(expand_uses=True)` **expands** `uses` after parse; the AST stored on the module then inlines grouping content (with refines applied).

---

## Data nodes: container, list, leaf, leaf-list, choice, case

### Container

```ebnf
container_stmt   = "container" identifier "{" container_body "}" [ ";" ] ;

container_body   = { container_body_stmt } ;

container_body_stmt
                 = "presence" STRING [ ";" ]
                 | when_stmt
                 | description_stmt
                 | must_stmt
                 | container_stmt | list_stmt | leaf_stmt | leaf_list_stmt
                 | choice_stmt | uses_stmt ;
```

### List

```ebnf
list_stmt        = "list" identifier "{" list_body "}" [ ";" ] ;

list_body        = { list_body_stmt } ;

list_body_stmt   = "key" ( STRING | identifier ) [ ";" ]
                 | "min-elements" INTEGER [ ";" ]
                 | "max-elements" INTEGER [ ";" ]
                 | when_stmt
                 | description_stmt
                 | must_stmt
                 | leaf_stmt | container_stmt | list_stmt | leaf_list_stmt
                 | choice_stmt | uses_stmt ;
```

### Leaf

```ebnf
leaf_stmt        = "leaf" identifier "{" leaf_body "}" [ ";" ] ;

leaf_body        = { leaf_body_stmt } ;

leaf_body_stmt   = type_stmt
                 | "mandatory" ( "true" | "false" ) [ ";" ]
                 | "default" ( STRING | INTEGER | identifier | "true" | "false" ) [ ";" ]
                 | when_stmt
                 | description_stmt
                 | must_stmt ;
```

### Leaf-list

```ebnf
leaf_list_stmt   = "leaf-list" identifier "{" leaf_list_body "}" [ ";" ] ;

leaf_list_body   = { leaf_list_body_stmt } ;

leaf_list_body_stmt
                 = type_stmt
                 | "min-elements" INTEGER [ ";" ]
                 | "max-elements" INTEGER [ ";" ]
                 | description_stmt
                 | must_stmt ;
```

There is **no** `when` on `leaf-list` in the current registry.

### Choice and case

```ebnf
choice_stmt      = "choice" identifier "{" choice_body "}" [ ";" ] ;

choice_body      = { "mandatory" ( "true" | "false" ) [ ";" ]
                   | description_stmt
                   | case_stmt } ;

case_stmt        = "case" identifier "{" case_body "}" [ ";" ] ;

case_body        = { case_body_stmt } ;

case_body_stmt   = description_stmt
                 | leaf_stmt | container_stmt | list_stmt | leaf_list_stmt
                 | choice_stmt ;
```

---

## must and when

```ebnf
string_concat    = STRING { "+" STRING } ;

must_stmt        = "must" string_concat ( ";" | "{" must_substmts "}" [ ";" ] ) ;

must_substmts    = { "error-message" STRING [ ";" ] | description_stmt } ;

when_stmt        = "when" string_concat [ ";" ] ;
```

**Limitation:** `when` does **not** support the YANG form with a trailing braced block for sub-statements; only the string (with `+` concatenation) and an optional semicolon.

`must` / `when` expressions are interpreted as XPath by the validator (subset + extensions such as `deref()` where implemented).

---

## Statement registry summary

Parent context and accepted first tokens are exactly those registered in `YangParser._register_handlers()` in `yang_parser.py`. Unknown statements in a given context produce a syntax error.

---

## Constructs not in this grammar

Typical YANG 1.1 features **outside** xYang’s parser (see also `FEATURES.md`) include among others:

`import`, `include`, `submodule`, `augment`, `deviation`, `extension`, `identity`, `identityref`, `bits`, `empty` (as a first-class keyword — `empty` may still appear as an identifier if treated like a name), `instance-identifier`, `feature`, `if-feature`, `anydata`, `anyxml`, `notification`, `rpc`, `action`, `input`, `output`, etc.

---

## Maintenance

When extending the parser:

1. Update `YangTokenType` / `YANG_KEYWORDS` if adding a reserved word.
2. Register `parent:statement` handlers in `yang_parser.py`.
3. Implement parsing in `statement_parsers.py`.
4. Update this document and, if still relevant, [`meta-model-grammar.ebnf`](../meta-model-grammar.ebnf).
