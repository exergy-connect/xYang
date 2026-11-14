# Architecture

xYang parses YANG, checks RFC 7951 JSON, and exports JSON Schema. Python lives in `src/xyang`. TypeScript lives in `ts/src` and mirrors it: `src/xyang/x/y.py` corresponds to `ts/src/x/y.ts`.

Key learnings for agents: [`docs/KEY-LEARNINGS.md`](docs/KEY-LEARNINGS.md).

| To change | Look in |
|---|---|
| Parser keyword dispatch | `parser/dispatch_registry` (Python) / `parser/dispatch-registry` (TS) |
| Built-in type JSON encoding | `types/registry` |
| Typedef scope restrictions | `typedef_scope` (Python and Zig) / `typedef-scope` (TS) |
| JSON Schema export | `json/generator` |
| JSON Schema import | `json/parser` |
| Instance validation | `validator/` |
| XPath | `xpath/` |

Zig's `zig/src/ast.zig` stores each `TypeStmt` as a common header and a tagged
pointer payload for its type family. `types/registry.zig:typeKind` selects the family,
including unresolved typedef references. Unconstrained types allocate no payload;
attributes allocate only the matching family, and range/length metadata lives in
separate `TypeRestriction` objects allocated when present. Read accessors return
empty/default values without allocating. Parser handlers check applicable families
before requesting mutable payloads. Payloads share the module arena's lifetime. Type
references also retain their lexical declaration context; scope lookup follows included submodules to their parent module
and preserves the defining module for imported grouping references.

Each language has one frozen built-in table. An entry records `json_encoding`, `bounds`, `pattern`, and the schema export, schema import, and RFC 7951 value check for that type. The generator, the parser, and the validator call the table. A shared `types.json` is a possible follow-up, not part of this layout.

All typedefs live in the module's global table. A nested typedef carries an optional
`scope` restriction; lookup checks that the type reference's declaration context is that
scope or a descendant. Scope paths use escaped JSON Pointer segments; `/outer` includes
`/outer/child` but excludes `/outer-other`. Grouping contexts use `@grouping:<name>` to
keep their namespace distinct. Unrestricted typedefs retain their existing behavior.
Registration rejects overlapping declarations with the same name. Sibling contexts may
reuse names, stored under distinct `<scope>/<name>` keys. References retain their declaration
context through `uses` and augment expansion. There is no separate typedef binding pass.

The native JSON form uses global `$defs` entries with optional `x-yang.scope` and `x-yang.name`
metadata. Omitted `scope` means module-wide visibility; a scope must be a non-empty absolute
context path. For example:

```json
{
  "$defs": {
    "code": {
      "type": "string",
      "x-yang": { "scope": "/outer" }
    }
  }
}
```

This typedef is visible under `outer` and its descendants. A reference elsewhere is a schema
error. The exporter qualifies keys when sibling scopes reuse a name and escapes those keys
in `$ref` URIs. `x-yang.name` retains the original YANG name when the storage key differs.
`x-yang.type-context` on references preserves their original lexical context when a grouping
is instantiated elsewhere; without it, the native parser uses the enclosing schema context.
Export and reload preserve these restrictions, including references inside unions and lists.
