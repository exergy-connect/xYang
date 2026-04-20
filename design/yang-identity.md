# YANG `identity` and `identityref`

This document summarizes the **identity** mechanism in YANG (RFC 7950 / YANG 1.1): what it is, how it relates to **`identityref`**, and typical reasons to use it. It is general YANG background; for what xYang implements today, see [`FEATURES.md`](../FEATURES.md) (identities and `identityref` are not parsed in xYang yet).

---

## What an identity is

An **identity** is a named, abstract label defined at module scope. Identities form a **derivation tree**: each identity may optionally declare a **`base`** identity (or, in YANG 1.1, multiple bases). A root identity has no `base`; others refine that taxonomy by inheriting from one or more bases.

Conceptually, identities behave like **open-ended class tags** or **marker interfaces**: they describe *what kind of thing* something is, without carrying data beyond the name. Unlike **`enumeration`**, the set of valid values is **not closed** at the defining module—other modules can **`import`** your base identity and define **derived** identities in their own namespace, extending the model after publication.

---

## `identityref`: referring to an identity

A leaf (or leaf-list) of type **`identityref`** holds a value that **names** one identity in a subtree rooted at a given **base** identity. Validation ensures the chosen identity **is** (or derives from) that base. The instance value is typically encoded as a **qualified name** (`prefix:identity-name`) when the identity comes from another module.

Together, **`identity`** definitions plus **`identityref`** leaves give you a typed way to point at “which kind” in a hierarchy, with **module extensibility** built in.

---

## Key use cases

### 1. Extensible classification without revising the core module

You publish a base identity (e.g. `crypto-algorithm`) and a few standard derived identities. Consumers or vendors **`import`** your module and define new identities **`base crypto-algorithm`**, then use those names in configuration or RPCs. The core schema never needs an enum update for every new algorithm.

### 2. Polymorphic or plug-in data models

A container might hold different subtrees depending on “which implementation” applies. An **`identityref`** (e.g. to `storage-backend`) can select or tag the active case: file vs. database vs. cloud, where each backend is a distinct derived identity. Tools and validators use the identity name to interpret the rest of the tree (often alongside **`choice`/`case`** or separate augmenting modules).

### 3. Protocol, encoding, or feature selection

Identities are often used for **non-overlapping alternatives** that are easier to extend than a flat string or enum: transport types, authentication methods, encoding formats, or optional capabilities. The hierarchy (`base` / derived) can express **general vs. specific** options (e.g. a family of related but distinct methods).

### 4. Cross-module agreement on symbolic constants

Because identities are global names within the import graph, two modules can refer to the **same** symbolic kind without hard-coding the same string in both places: one module defines the identity; others reference it via **`identityref`** or use the identity in **`if-feature`**-style patterns (in ecosystems that combine identities with features).

### 5. Contrasting with `enumeration` and `string`

| Mechanism | Closed set? | Extensible by other modules? | Typical role |
|-----------|-------------|-------------------------------|--------------|
| **`enumeration`** | Yes (fixed at typedef) | No | Small, stable sets of literals |
| **`string`** | No | N/A (untyped) | Free text; weaker validation |
| **`identity` / `identityref`** | Open under a base | Yes (derived identities) | Named, extensible kinds with validation |

---

## Mapping to JSON Schema

JSON Schema (e.g. draft 2020-12) has **no built-in type for YANG identities**. Instance data still encodes an **`identityref`** as a **string** (see RFC 7951 JSON encoding: often a **qualified name** `prefix:identity` when the identity is imported). So at the JSON layer the value is always a string; the extra semantics live outside plain JSON Schema.

**What JSON Schema can express directly**

- **`type: "string"`** — Matches the wire format. This is the faithful “syntax” level: any string is allowed unless you add more keywords.
- **`enum: ["…", …]`** — You can list every identity name that is valid for a given `identityref` **base** at codegen time. That gives strict structural validation in generic validators, but the set is **closed**: new derived identities in other modules are **not** accepted until the schema is regenerated. That trade-off mirrors **`enumeration`** in JSON, not the open-world YANG identity model.
- **`pattern`** — You might constrain the lexical shape (e.g. optional `prefix:` plus a restricted name). That does **not** prove an identity exists or derives from the right **base**; it is only a hint.

**What JSON Schema cannot express alone**

- The **derivation tree** (`base` / derived identities) and the rule “value must name an identity under this **base**” are **YANG data model** rules. A plain JSON Schema validator does not know imported modules or identity statements.
- Tools that need full fidelity usually add **side metadata** (for example a custom property alongside the leaf schema naming the **base** identity, or a parallel machine-readable list of allowed identities) and perform identityref checks in a **YANG-aware** validator—similar in spirit to how **`leafref`** needs path resolution outside JSON Schema.

**Practical takeaway**

Emit **`type: "string"`** for an `identityref` if you want open-ended values at schema level; use **`enum`** when you intentionally snapshot a fixed set for a given deployment or export; reserve **base-aware** validation for tooling that understands YANG identities. The xYang JSON profile does not yet define an `x-yang` shape for `identityref`; see [`json-schema-xyang-profile.md`](json-schema-xyang-profile.md) and [`FEATURES.md`](../FEATURES.md) for current coverage.

---

## Related reading

- RFC 7950 — *The YANG 1.1 Data Modeling Language* (`identity`, `identityref`, `base` statements).
- [`FEATURES.md`](../FEATURES.md) — xYang feature checklist and JSON Schema profile notes.
