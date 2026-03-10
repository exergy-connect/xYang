# Where the "duplicate" came from

## Two different effects

### 1. Duplicate `must_statements` on the leaf (parser bug)

For the **minimal** YANG (no uses/grouping), the leaf `"field"` is **not** in `computed.statements`. The parser only has:

- `computed.statements` = `[operation, list "fields"]`
- `list "fields".statements` = `[leaf "field"]`

So the validator only visits the leaf **once** (when descending into the list entry). The duplicate errors come from the leaf having **two** must statements:

- **`parse_leaf_must`** calls `parse_must(...)` and then does `context.current_parent.must_statements.append(must_stmt)`.
- **`parse_must`** itself does `context.current_parent.must_statements.append(must_stmt)` when the parent is a `YangStatementWithMust` (e.g. a leaf).

So the same must is appended **twice** for a leaf. Then in the validator, `for must in stmt.must_statements` runs twice and reports two errors for the same path.

So in the minimal test the “duplicate iteration” is this loop over `must_statements`, not two different visit paths.

### 2. Same leaf as direct container child (validator + schema)

The **second** call chain you saw (container → leaf without going through the list) would happen only if **the same leaf** appeared in **both**:

- `computed.statements` (wrong: leaf as direct child of container), and  
- `list "fields".statements` (correct).

That can happen after **uses/grouping expansion** in the meta-model: expansion can copy nodes so that a key leaf is both inside the list and (incorrectly) as a direct child of the parent container. The **validator** fix (skip leaves with `is_list_key` when visiting a container’s children) prevents that second visit. The **parser** fix (marking key leaves with `is_list_key`) makes that skip correct and avoids heuristics.

## Summary

| Source | Effect |
|--------|--------|
| **Parser**: `parse_leaf_must` + `parse_must` both append | Leaf gets 2 identical musts → validator loop runs twice → 2 errors per path. |
| **Schema/expansion**: key leaf in both container and list | Validator would visit leaf twice (container then list entry). Fixed by skipping `is_list_key` leaves when visiting container children. |

In the minimal test, only (1) applies. Fixing (1) removes the duplicate errors there; (2) and the `is_list_key` logic protect the meta-model case.
