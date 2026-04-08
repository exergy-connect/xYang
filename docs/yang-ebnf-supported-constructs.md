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

(* Keywords: statement / constraint tokens plus RFC 7950 built-in types (Sec. 4.2.4). *)
keyword      = "module" | "yang-version" | "namespace" | "prefix" | "organization" | "contact"
             | "description" | "revision" | "typedef" | "type"
             | "binary" | "bits" | "boolean" | "decimal64" | "empty" | "enumeration"
             | "identityref" | "instance-identifier" | "int8" | "int16" | "int32" | "int64"
             | "leafref" | "string" | "uint8" | "uint16" | "uint32" | "uint64" | "union"
             | "path" | "require-instance" | "enum" | "bit" | "position" | "pattern" | "length"
             | "fraction-digits" | "range" | "grouping" | "uses" | "refine"
             | "container" | "list" | "leaf" | "leaf-list" | "choice" | "case"
             | "must" | "when" | "presence" | "key" | "min-elements" | "max-elements"
             | "mandatory" | "default" | "error-message" | "true" | "false" ;

punctuation  = "{" | "}" | ";" | "=" | "+" | "/" ;
```

**Notes:**

- The first character of an `identifier` must be **A–Z, a–z, or `_`**; inner `-` and `.` match RFC 7950.
- Digit-led lexemes are **`INTEGER`** or **`DOTTED_NUMBER`** (e.g. `yang-version 1.1;`), never `IDENTIFIER`.
- All RFC 7950 built-in type names are **keywords** in the lexer (see `YangTokenType` in `parser_context.py`). They still produce the correct spellings for `type` statements via `token.value`. Typedef and grouping **names** must not use those spellings, because those contexts require a bare `IDENTIFIER` token.
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

(* Built-in keywords use the same spelling as in YANG source; typedefs use identifier. *)
type_name     = builtin_type_keyword | identifier ;

builtin_type_keyword
              = "binary" | "bits" | "boolean" | "decimal64" | "empty" | "enumeration"
              | "identityref" | "instance-identifier" | "int8" | "int16" | "int32" | "int64"
              | "leafref" | "string" | "uint8" | "uint16" | "uint32" | "uint64" | "union" ;

type_body     = { type_substmt } ;

type_substmt  = "type" type_stmt              (* union member types, including nested leafref *)
              | enum_stmt                     (* only in ``enumeration`` — forms enum_specification *)
              | bit_stmt                      (* only in ``bits`` *)
              | "pattern" STRING [ ";" ]
              | "length" ( STRING | identifier ) [ ";" ]
              | "range" STRING [ ";" ]
              | "fraction-digits" INTEGER [ ";" ]
              | "path" STRING [ ";" ]
              | "require-instance" ( "true" | "false" ) [ ";" ]
              | description_stmt ;

(* RFC 7950: enum-specification = 1*enum-stmt. Fills ``type enumeration { … }``. *)
enum_specification = enum_stmt { enum_stmt } ;

enum_stmt     = "enum" enum_name [ ";" ] ;   (* RFC 7950 allows a braced enum-stmt body; xYang is flat-only today. *)

(* Enum value: lexer token — identifier or any built-in type keyword spelling. *)
enum_name     = identifier | builtin_type_keyword ;

(* RFC 7950 bits: at least one bit-stmt; optional position and description in bit body. *)
bit_stmt      = "bit" identifier [ "{" { bit_substmt } "}" ] [ ";" ] ;

bit_substmt   = "position" INTEGER [ ";" ]
              | description_stmt ;
```

**Supported type names** (after `type`):

- Any **built-in type keyword** (RFC 7950 Section 4.2.4; see `builtin_type_keyword` above).
- Any **typedef** name (`identifier` token).

**Union:** `type union {` … one or more nested `type … ;` members … `}`.

**Leafref:** `type leafref { "path" STRING ; [ "require-instance" ( "true" | "false" ) ; ] }`.

**Enumeration:** `type enumeration {` **enum-specification** `}` where **enum-specification** is **one or more** **enum-stmt** (each `enum` *enum-name* `;`, or a braced variant if supported). The parser currently takes a single token per `enum` name then `;` (optional nested description blocks are limited; see `parse_type_enum`).

**Bits:** `type bits {` one or more `bit` *name* `;` or `bit` *name* `{` `position` *integer* `;` [ `description` … ] `}` `}`. Implicit `position` values follow RFC 7950 (see `StatementParsers._finalize_bits_type`). Instance JSON: a single string, space-separated bit names. In generated JSON Schema, `x-yang.bits` is an object mapping each bit name to its integer position (legacy array-of-objects input is still parsed).

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

`import`, `include`, `submodule`, `augment`, `deviation`, `extension`, `feature`, `if-feature`, `anydata`, `anyxml`, `notification`, `rpc`, `action`, `input`, `output`, etc. (Several built-in type keywords are implemented for parsing/validation — see **Supported type names** and `FEATURES.md`.)

---

## Maintenance

When extending the parser:

1. Update `YangTokenType` / `YANG_KEYWORDS` if adding a reserved word.
2. Register `parent:statement` handlers in `yang_parser.py`.
3. Implement parsing in `statement_parsers.py`.
4. Update this document and, if still relevant, [`meta-model-grammar.ebnf`](../meta-model-grammar.ebnf).
