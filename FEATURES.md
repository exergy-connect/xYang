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
- ✅ `union` - Union type (3 occurrences)

### Data Structures
- ✅ `container` - Container statements
- ✅ `list` - List statements (with key)
- ✅ `leaf` - Leaf statements
- ✅ `leaf-list` - Leaf-list statements

### Constraints
- ✅ `must` - Must constraints (57 occurrences) - **Parsed and evaluated**
- ✅ `when` - When conditions (1 occurrence) - **Parsed and evaluated**
- ✅ `mandatory` - Mandatory fields (15 occurrences)
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

- ❌ `grouping` / `uses` - Grouping and uses statements
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

### Arithmetic Operations
- ✅ `+`, `-`, `*`, `/` - Arithmetic operators (with `/` treated as path navigation when appropriate)

### Advanced Features
- ✅ **Nested deref()**: `deref(deref(current())/../foreignKey/entity)` - Multiple levels of dereferencing
- ✅ **Path navigation from nodes**: `deref(...)/../fields` - Navigate from dereferenced nodes
- ✅ **Leaf-list indexing**: `primary_key[1]` - Access first element of leaf-list
- ✅ **Type matching**: `deref(current())/../type = deref(...)/../fields[...]/type` - Complex type comparisons
- ✅ **Cross-entity validation**: Full support for validating foreign key relationships across entities

The XPath evaluator uses proper tokenization and AST-based parsing (not string-based), making it robust and maintainable. The implementation has been optimized and refactored for better performance and code organization.

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
xYang/
├── xpath/
│   ├── __init__.py              # Exports XPathEvaluator
│   ├── evaluator.py             # Main XPath evaluator (orchestrator)
│   ├── parser.py                # Tokenizer and recursive descent parser
│   ├── ast.py                   # AST node definitions
│   ├── path_evaluator.py        # Path navigation logic
│   ├── schema_leafref_resolver.py  # Schema and leafref resolution utilities
│   ├── predicate_evaluator.py   # Predicate filtering logic
│   ├── function_evaluator.py    # XPath function implementations
│   ├── comparison_evaluator.py  # Comparison operations
│   └── utils.py                 # Utility functions (yang_bool, etc.)
├── errors.py                    # Custom exception classes
├── parser.py                    # YANG parser
├── validator.py                 # Validation engine
└── ...
```

The modular architecture separates concerns:
- **Path evaluation**: Handles all path navigation and context management
- **Deref resolution**: Specialized logic for resolving leafref paths
- **Predicate evaluation**: Handles filtering and indexing of lists
- **Function evaluation**: Dictionary-based dispatch for XPath functions
- **Comparison operations**: Type-coercion aware comparisons

## Limitations

1. **Leafref Resolution**: `deref()` is implemented with full support for nested paths and cross-entity references. It correctly resolves:
   - Simple leafrefs: `deref(../entity)`
   - Nested leafrefs: `deref(deref(current())/../foreignKey/entity)`
   - Relative paths from any context
   - Entity and field lookups in the schema

2. **XPath Scope**: Only the XPath features actually used in `meta-model.yang` are implemented. More complex XPath features (e.g., axes, namespaces, complex location paths) are not supported.

3. **Error Handling**: The XPath evaluator catches exceptions during evaluation and returns `False` or `None` for constraint validation. This ensures validation doesn't crash on invalid expressions, but detailed error information may be lost in constraint evaluation contexts.

4. **Performance**: The evaluator includes optimizations such as:
   - Expression caching for short expressions
   - Efficient context path management
   - Set-based operator lookups
   - Early returns for common cases

## Usage Statistics from meta-model.yang

- `must`: 57 occurrences
- `default`: 29 occurrences
- `mandatory`: 15 occurrences
- `leafref`: 11 occurrences
- `pattern`: 7 occurrences
- `enumeration`: 6 occurrences
- `min-elements`: 5 occurrences
- `presence`: 4 occurrences
- `union`: 3 occurrences
- `max-elements`: 2 occurrences
- `decimal64`: 2 occurrences
- `fraction-digits`: 2 occurrences
- `when`: 1 occurrence
- `range`: 1 occurrence

## Recent Improvements

### XPath Evaluator Enhancements (2026)
- ✅ **Nested deref() support**: Full implementation of nested `deref()` calls for complex cross-entity validation
- ✅ **Path navigation fixes**: Proper handling of `../../name` and other multi-level relative paths
- ✅ **Predicate navigation**: Support for navigating from predicate results (e.g., `fields[...]/type`)
- ✅ **Leaf-list indexing**: Correct handling of `primary_key[1]` and other numeric indices
- ✅ **Code refactoring**: Modular architecture with separated concerns for better maintainability
- ✅ **Performance optimizations**: Expression caching, efficient context management, and optimized lookups
