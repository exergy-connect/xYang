# xYang Feature Set

This document lists the YANG features implemented in xYang, based on actual usage in `meta-model.yang`.

## Features Implemented

### Module Structure
- ✅ `module` - Module definition
- ✅ `yang-version` - YANG version (1.1)
- ✅ `namespace` - Module namespace
- ✅ `prefix` - Module prefix
- ✅ `organization` - Organization (1 occurrence)
- ✅ `contact` - Contact info (1 occurrence)
- ✅ `description` - Description text
- ✅ `revision` - Revision history (1 occurrence)

### Type Definitions
- ✅ `typedef` - Type definitions (heavily used)
- ✅ `type` - Type references

### Built-in Types
- ✅ `string` - String type
- ✅ `int32` - 32-bit integer
- ✅ `uint8` - 8-bit unsigned integer
- ✅ `boolean` - Boolean type
- ✅ `decimal64` - Decimal64 type (2 occurrences)

### Derived Types
- ✅ `enumeration` - Enumeration type (6 occurrences)
- ✅ `union` - Union type (3 occurrences) - **Full support in typedefs with validation, including union types with leafref members**

### Data Structures
- ✅ `container` - Container statements
- ✅ `list` - List statements (with key)
- ✅ `leaf` - Leaf statements
- ✅ `leaf-list` - Leaf-list statements
- ✅ `choice` - Choice statements (mutually exclusive alternatives)
- ✅ `case` - Case statements (choice alternatives)
- ✅ `grouping` - Grouping statements (defines reusable schema components)
- ✅ `uses` - Uses statements (incorporates groupings)
- ✅ `refine` - Refine statements (modifies nodes from groupings)

### Constraints
- ✅ `must` - Must constraints (57+ occurrences) - **Parsed and evaluated**
  - Supports must constraints on containers, lists, leaves, and leaf-lists
  - Supports must constraints on lists containing leafref types
  - `current()` correctly refers to list item context in list must constraints
- ✅ `when` - When conditions (1 occurrence) - **Parsed and evaluated**
- ✅ `mandatory` - Mandatory fields (15 occurrences)
  - Supports mandatory on choice statements (exactly one case must be present)
- ✅ `default` - Default values (29 occurrences)
- ✅ `min-elements` - Minimum elements (5 occurrences)
- ✅ `max-elements` - Maximum elements (2 occurrences)
- ✅ `key` - List keys (heavily used)

### Type Constraints
- ✅ `pattern` - Pattern matching (7 occurrences)
- ✅ `length` - Length constraints (8 occurrences)
- ✅ `range` - Range constraints (1 occurrence)
- ✅ `fraction-digits` - Decimal fraction digits (2 occurrences)

### Type References
- ✅ `leafref` - Leaf references (11 occurrences) - **Parsed and resolved via deref()**
- ✅ `path` - Leafref paths
- ✅ `require-instance` - Leafref require-instance

### Container Features
- ✅ `presence` - Container presence (4 occurrences)

## Features NOT Implemented

The following YANG features are not used in `meta-model.yang` and are not implemented:

- ❌ `augment` - Augmentation
- ❌ `deviation` - Deviation
- ❌ `import` - Module imports (modules are self-contained)
- ❌ `extension` - Extension statements
- ❌ `identity` / `identityref` - Identity statements
- ❌ `bits` - Bits type
- ❌ `empty` - Empty type
- ❌ `instance-identifier` - Instance identifier

## When Conditions

xYang supports `when` statements for conditional validation. When a `when` condition evaluates to `false`, the associated statement (container, leaf, list, etc.) is skipped during validation. This allows conditional inclusion of schema elements based on data values.

Example from `meta-model.yang`:
```yang
container item_type {
  when "../type = 'array'";
  description "Required for array fields";
  ...
}
```

If `../type = 'array'` evaluates to false, the `item_type` container is not validated and is treated as optional.

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
The `uses` statement incorporates a grouping into the current schema node. When a `uses` statement is encountered, the statements from the grouping are copied and expanded into the current location.

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
The `refine` statement allows modifying nodes from a grouping when using it. This is particularly useful for adding constraints or changing properties.

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
- ✅ `bool(...)` - Convert value to boolean following YANG rules
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

During document validation, path expression results are cached per run to avoid recomputing the same path from the same context. This speeds up validation when many `must` constraints or leafref `require-instance` checks share the same path expressions (e.g. repeated `/data-model/entities` or relative paths from list items).

- **Scope**: One cache per validation run, held in `Context.path_cache` (a dict). The same cache is shared for the root context and all child contexts created during the run.
- **What is cached**: Resolved path results (node-sets). Absolute paths are keyed by path string only; relative paths are keyed by path string plus the current node’s identity so that `../foo` from different nodes is not confused.
- **Cacheability**: A path is only cached if its evaluation does not depend on context-sensitive functions. Paths that use `current()` or `deref()` in predicates are not cached, because their result can change with context. Simple structural paths (e.g. `/data-model/entities`, `../type`) are cached.
- **Observability**: `XPathEvaluator.get_cache_stats()` returns absolute/relative lookups, hits, and hit ratios for the current run. Call `clear_cache()` (or use a fresh evaluator) at the start of each validation run so stats reflect that run only.

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
│   ├── statement_registry.py    # Statement registry
│   └── parser_context.py        # Parser context
├── validator/                   # Validation engine
│   ├── yang_validator.py       # Top-level YANG validator
│   ├── document_validator.py   # Document/node validation (must, leafref, etc.)
│   ├── type_checker.py         # Type checking
│   ├── path_builder.py         # Path building utilities
│   └── validation_error.py      # Validation error types
├── errors.py                    # Custom exception classes
├── ast.py                       # YANG AST node definitions
├── types.py                     # Type utilities
└── module.py                    # Module handling
```

The modular architecture separates concerns:
- **evaluator**: Path evaluation, predicate filtering, and expression orchestration; manages context and Node cursor
- **schema_nav**: Schema navigation and leafref/deref resolution
- **functions**: Dictionary-based dispatch for XPath functions (e.g. `count`, `current`, `deref`)
- **utils**: Type-coercion aware comparisons (`compare_eq`, `compare_lt`, `compare_gt`), `yang_bool`, node-set helpers
- **parser / tokenizer / ast**: XPath expression parsing; **node**: Context and Node (data/schema cursor) for evaluation

## Limitations

- **XPath scope**: Only the XPath features used in `meta-model.yang` are implemented. Unsupported: axes (e.g. `child::`, `following-sibling::`), namespaces, and more complex location paths.
- **Error reporting**: In constraint validation the evaluator catches exceptions and returns `False` or `None`, so detailed error information is not surfaced to the caller.
- **Expression caching**: Caching applies only to short expressions; long or dynamic expressions are not cached.
- **Schema/document model**: The implementation is tied to the meta-model and document structure (e.g. schema-aware `Node`); it is not a general-purpose XPath 1.0 engine.

## Implementation notes

- **Leafref / deref**: `deref()` supports nested paths and cross-entity references: simple leafrefs (`deref(../entity)`), nested (`deref(deref(current())/../foreignKey/entity)`), relative paths, and entity/field lookups in the schema.
- **Performance**: The evaluator uses expression caching (short expressions), efficient context path handling, set-based operator lookups, and early returns where applicable.

## Usage Statistics from meta-model.yang

Counts below are from `examples/meta-model.yang` (statement or keyword occurrences):

- `must`: 30
- `default`: 28
- `mandatory`: 14
- `pattern`: 7
- `length`: 8
- `enumeration`: 8
- `leafref`: 6 (in `type` / path)
- `union`: 7 (fully supported in typedefs)
- `min-elements`: 6
- `case`: 6
- `choice`: 2
- `decimal64`: 4
- `fraction-digits`: 4
- `when`: 4
- `presence`: 1
- `max-elements`: 1
- `range`: 1

## Test Coverage

xYang has comprehensive test coverage with **195+ passing tests** covering:
- Basic YANG parsing and validation
- Type validation (including enumeration)
- Constraint validation (must, when, mandatory, default)
- Leafref resolution and validation
- Deref() function with nested calls
- Grouping and uses statements
- Choice/case statements
- Union types in typedefs
- Unknown field detection
- XPath expression evaluation
- Foreign key validation
- Parent-child relationship validation
- Must constraints on leafref lists
- Current context preservation in predicates
- Relative and absolute path resolution

## Recent Improvements

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
- ✅ **Test coverage**: All 178 tests now passing, including fixes for:
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
