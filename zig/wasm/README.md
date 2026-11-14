# Zig WebAssembly build

Build the existing Zig validation core as a freestanding Wasm library with Zig
0.17.1. It imports no host functions and needs neither WASI nor a filesystem.

The release workflow builds and tests this library, then attaches `xyang.wasm`
and its dependency-free JavaScript wrapper, `xyang.mjs`, to new
[GitHub Releases](https://github.com/exergy-connect/xYang/releases). Download
both assets from the same release. A manual run of **Release Zig binaries**
uploads them in the `xyang-zig-binaries` workflow artifact without publishing a
release.

To build from source:

```bash
cd zig
zig build
zig build wasm -Doptimize=ReleaseSmall
node --test tests/wasm.test.mjs
```

The artifact is `zig/zig-out/bin/xyang.wasm`. The Wasm build is opt-in and does
not change the native CLI build. `-Doptimize=ReleaseSafe` enables runtime safety
checks; `ReleaseSmall` prioritizes artifact size. The module has a 2 MiB stack
and a 256 MiB maximum linear memory, including the stack, model, inputs, and
validation scratch space. Linear memory can grow but does not shrink; freed
allocations are reused. Traps, including stack exhaustion, require the host to
discard and recreate the instance.

## JavaScript host

First generate a canonical native JSON model from its YANG source:

```bash
xyang convert examples/meta-model.yang -o meta-model.yang.json
```

From the repository root, Node.js can use the dependency-free ESM wrapper:

```js
import { readFile } from "node:fs/promises";
import { createValidator } from "./zig/wasm/xyang.mjs";

const validator = await createValidator(await readFile("zig/zig-out/bin/xyang.wasm"));
validator.loadModel(await readFile("meta-model.yang.json", "utf8"));
const result = validator.validate('{"data-model":{"name":"example","entities":[]}}');
console.log(result.valid, result.errors, result.warnings);
validator.reset();
```

In a browser, serve `xyang.mjs`, `xyang.wasm`, and the model as static assets:

```js
import { createValidator } from "./xyang.mjs";

const validator = await createValidator(await (await fetch("./xyang.wasm")).arrayBuffer());
validator.loadModel(await (await fetch("./meta-model.yang.json")).text());
console.log(validator.validate('{"data-model":{"name":"example","entities":[]}}'));
```

Both methods take JSON **text**, so the host need not decode large integer
literals through JavaScript numbers. Each `createValidator` call creates an
independent instance with one retained model. Loading another model replaces it;
a failed load preserves the previous model. Validation reuses the loaded model
and releases scratch allocations on the next call. The wrapper copies results
out before freeing inputs and reacquires memory views after guest calls.

### RPC and action validation

Pass an optional second argument to `validate`. The loaded native model must
contain the selected RPC or action. For example, with a model defining an
`add-link` RPC in module `m`:

```js
const result = validator.validate('{"m:input":{"source":"r1","target":"r2"}}', {
  rpc: "add-link",
  context: '{"m:topology":{"node":[{"name":"r1"},{"name":"r2"}]}}',
});
```

| Option | Meaning |
| --- | --- |
| `rpc` | Nonempty RPC name in the loaded module. Mutually exclusive with `action`. |
| `action` | RFC 8040 data resource path, e.g. `/m:interfaces/interface=eth0/reset`. Requires `context`. |
| `direction` | `"input"` (default) or `"output"`. Output requires `rpc` or `action`. |
| `context` | Server data as JSON **text**, preserving exact numeric literals. Requires `rpc` or `action`; the decoded value must be an object. |

Use the selected operation's module-qualified `module:input` or `module:output`
wrapper in the data. For an action, percent-encode list key values in its path.
The core validates context first; diagnostics about server data have
`document: "context"`, while operation diagnostics have `document: "data"`.
Context supplies action parents and the accessible tree for XPath, defaults,
`must`, `when`, and references. Every call supplies its own options and context;
they are not retained for subsequent calls.

Invalid combinations, unknown operations, and malformed action paths throw with
`code: "Usage"`. Invalid data, invalid context data, or a missing action parent
return `valid: false` with diagnostics. Invalid option shapes and unknown option
names in JavaScript throw `TypeError`; malformed context JSON throws with
`code: "InvalidJson"`.

An invalid instance returns `{ valid: false, errors, warnings }`. Each diagnostic
includes `pointer` (the JSON Pointer into the instance), `path` (display path),
`code`, `message`, `severity`, `expression`, and `document`. Malformed JSON,
invalid native models, missing models, and validation execution errors throw a
JavaScript `Error` with a `code` property. This is an experimental API.

## Raw ABI

All arguments and return values are Wasm `i32` values, interpreted as unsigned.
Strings are UTF-8 bytes in the exported `memory`; lengths exclude a terminator.

| Export | Contract |
| --- | --- |
| `xyang_alloc(len) -> ptr` | Allocate caller-owned input bytes; returns 0 on failure or zero length. |
| `xyang_free(ptr, len)` | Free that allocation with its original pointer and length; zero is a no-op. |
| `xyang_load_model(ptr, len) -> status` | Load a canonical `.yang.json`, copying all retained input. |
| `xyang_validate(ptr, len) -> status` | Validate an RFC 7951 JSON document against the retained model. |
| `xyang_validate_with_options(ptr, len, options_ptr, options_len) -> status` | Validate with a UTF-8 JSON options object containing `rpc`, `action`, `direction`, and/or `context`. |
| `xyang_result_ptr() -> ptr` | Address of the last call's JSON result. |
| `xyang_result_len() -> len` | Byte length of that result. |
| `xyang_reset()` | Release the model and last result; caller allocations are unaffected. |

Status 0 means the API call completed, including validation with `valid:false`.
Status 1 means an API error; the result is `{ "err": "Code", "message": "..." }`.
A successful load returns `{ "loaded": true }`.

The options buffer uses the same field types as the JavaScript API: `context`
is a JSON **string containing JSON text**, not an embedded object. For example,
`{"rpc":"add-link","context":"{\"m:topology\":{\"node\":[]}}"}`.
The guest parses this text directly. The options buffer follows the same
ownership rules as the data buffer. Unknown fields and invalid field types
return status 1 with `err: "Usage"`. The two-argument `xyang_validate` export
remains available for document validation.

The result is guest-owned and valid until the next load, validation, or reset.
Do not free it. Caller input buffers must remain allocated for the duration of a
call and can be freed immediately afterwards. Pass only valid allocated ranges;
for empty input allocate at least one byte and pass length zero. Calls must be
serialized within an instance. Reacquire memory views after any guest allocation
or call because memory growth can invalidate them.

## Scope and verification

This build exposes native model loading and RFC 7951 document and operation
validation (all declared features enabled). YANG source parsing,
filesystem import resolution, model export, native instance encoding, feature
selection are not exposed. The existing native JSON
loader reconstructs embedded import metadata without host file access.

The Node test runner uses committed `expected.yang.json` forms and generates
operation models from existing shared YANG cases using the native Zig CLI
(hence the `zig build` before running tests). It compares validity, diagnostic
documents/pointers/codes, usage errors, and expected message fragments. Operation
cases requiring disabled features, native instance encoding, or loading a separate
augmenting source module are explicitly skipped because those loading/options
APIs are outside this build's scope. ABI tests cover isolation, reset, malformed
inputs, transactional model replacement, input ownership, memory growth, and
allocation reuse, option decoding, and exact context integers across the
JavaScript boundary. Shared validation scenarios are reused; no YANG or native
JSON fixtures are hand-authored for this build.
