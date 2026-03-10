# XPath path caching: which relative paths can be made absolute

## How caching works (evaluator)

- In `eval_path`, the cache key is `path.to_string() if path.is_absolute else None` (evaluator line 145).
- So **only absolute paths are cached**; relative paths (`../`, `.`, or no leading `/`) never get a cache key.
- The parser sets `cacheable = is_absolute` at the start of `_parse_path` (parser line 257), and path nodes from relative expressions are `is_absolute=False`.
- **Important:** The cache is keyed only by the path string. So if an absolute path contains `current()` in a predicate (e.g. `/data-model/entities[name = current()]/fields`), the same path string is evaluated from different nodes and yields different results. Caching that path would reuse the first result for all contexts and would be **wrong**. So we can only safely convert to absolute when the path (including predicates) does **not** depend on `current()` (or other context-dependent functions).

## Meta-model must expressions: evaluation

### 1. Safe to make absolute (no `current()` in path; improves caching)

| Location | Current expression | Suggested absolute | Notes |
|----------|--------------------|--------------------|------|
| **allow_unlimited_fields** (data-model) | `count(../entities[count(fields[type != 'array']) > 7]) > 0` | `count(/data-model/entities[count(fields[type != 'array']) > 7]) > 0` | Context is data-model; `../entities` = `/data-model/entities`. Predicate does not use `current()`. **Cacheable.** |
| **entities** list (entity-level must) | `../allow_unlimited_fields` (first alternative in an or) | `/data-model/allow_unlimited_fields` | When validating an entity, `../` is data-model. No `current()` in this subexpression. **Cacheable.** |

### 2. Already absolute (no change)

- `/data-model/consolidated`, `/data-model/max_name_underscores`, `/data-model/entities/...`, `/data-model/changes[id = current()]`, `/data-model/entities/field_definitions[...]`, etc. are already absolute and cached when used as path expressions.

### 3. Cannot safely make absolute for caching (depend on `current()`)

| Location | Expression | Why not cacheable if made absolute |
|----------|------------|------------------------------------|
| **primary_key** | `../fields[name = current()]` | Equivalent absolute would be something like `/data-model/entities[primary_key = current()]/fields[name = current()]`. Result depends on which entity we’re in (`current()`). Same path string, different results per entity → caching would be incorrect. |
| **entities** list | `count(fields[type != 'array']) <= 7` | `fields` is relative to the entity (current list entry). Absolute form would need `current()` to identify the entity. Result is per-entity. |
| **computed/fields/field** | `../../../../fields[name = current()]` | Identifies “current entity’s fields” from the computed field leaf. Requires knowing the containing entity (context). |
| **computed/fields/entity** | `../../../../fields[foreignKeys/entity = current()]` | Same: context-dependent. |
| **deref(../entity)/../fields[...]** | (cross-entity computed) | Depends on leafref resolution and current context. |

### 4. Short relative paths (sibling / parent)

- `../type`, `../default`, `../minDate`, `../maxDate`, `../entity`, `../../operation`, etc. are 1–2 level ups. Making them absolute would require identifying the “current” schema node from the root (e.g. “the field that contains this leaf”), which YANG XPath does not express as a simple absolute path. So these stay relative; no caching benefit from conversion.

## Recommendation

- **Apply the two safe conversions** in the meta-model:
  1. **allow_unlimited_fields:**  
     `count(../entities[count(fields[type != 'array']) > 7]) > 0`  
     → `count(/data-model/entities[count(fields[type != 'array']) > 7]) > 0`
  2. **entities list must:**  
     In the or-expression, replace `../allow_unlimited_fields` with `/data-model/allow_unlimited_fields`.

- **Do not** convert paths that depend on `current()` (or `deref(…)` from current context) to absolute for the purpose of caching, unless the cache is later extended to be keyed by (path, context) or to skip caching when the path contains context-dependent functions.

- **Optional (evaluator):** Consider caching relative path results keyed by `(path.to_string(), node_id)` or by a canonical “context path” so that repeated evaluation of the same relative path from the same context could still hit the cache. That would require a different cache design and invalidation strategy.
