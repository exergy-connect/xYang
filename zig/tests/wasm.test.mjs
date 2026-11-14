// Host ABI tests plus existing native-JSON conformance fixtures, without new models.
import assert from "node:assert/strict";
import { readFile, readdir, mkdtemp, rm } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import { createValidator } from "../wasm/xyang.mjs";

const bytes = await readFile(new URL("../zig-out/bin/xyang.wasm", import.meta.url));
const fixture = new URL("../../tests/cases/modules/json-form-structure-constraints-164/", import.meta.url);
const model = await readFile(new URL("expected.yang.json", fixture), "utf8");
const valid = JSON.stringify({ "m:msg": { n: 3, tags: ["ab"] } });

test("freestanding module has no host imports", async () => {
  const module = await WebAssembly.compile(bytes);
  assert.deepEqual(WebAssembly.Module.imports(module), []);
});

test("validation requires a model", async () => {
  const validator = await createValidator(bytes);
  assert.throws(() => validator.validate(valid), { code: "NoModel" });
});

for (const [name, text, code] of [
  ["malformed model", "{", "InvalidJson"],
  ["ordinary JSON Schema", '{"type":"object"}', "JsonForm"],
]) {
  test(`${name} fails without replacing the retained model`, async () => {
    const validator = await createValidator(bytes);
    validator.loadModel(model);
    assert.throws(() => validator.loadModel(text), { code });
    assert.equal(validator.validate(valid).valid, true);
  });
}

for (const text of ["{", ""]) {
  test(`malformed instance ${JSON.stringify(text)} reports an API error`, async () => {
    const validator = await createValidator(bytes);
    validator.loadModel(model);
    assert.throws(() => validator.validate(text), { code: "InvalidJson" });
    assert.equal(validator.validate(valid).valid, true);
  });
}

test("reset releases the model and allows another load", async () => {
  const validator = await createValidator(bytes);
  validator.loadModel(model);
  validator.reset();
  validator.reset();
  assert.throws(() => validator.validate(valid), { code: "NoModel" });
  validator.loadModel(model);
  assert.equal(validator.validate(valid).valid, true);
});

test("instances retain independent models", async () => {
  const first = await createValidator(bytes);
  const second = await createValidator(bytes);
  first.loadModel(model);
  assert.throws(() => second.validate(valid), { code: "NoModel" });
  second.reset();
  assert.equal(first.validate(valid).valid, true);
});

test("memory growth and freed host buffers do not corrupt the retained model", async () => {
  const validator = await createValidator(bytes);
  const large = JSON.parse(model);
  large.description = "λ网络".repeat(100_000);
  validator.loadModel(JSON.stringify(large));
  for (let i = 0; i < 30; i++) {
    // Both input allocation and guest parsing can grow and reuse linear memory.
    assert.equal(validator.validate(` ${" ".repeat(100_000)}${valid}`).valid, true);
  }
});

test("ABI reclaims replaced-model memory", async () => {
  const { instance: { exports: wasm } } = await WebAssembly.instantiate(bytes, {});
  const encoded = new TextEncoder().encode(model);
  const ptr = wasm.xyang_alloc(encoded.length);
  new Uint8Array(wasm.memory.buffer, ptr, encoded.length).set(encoded);
  try {
    // Repeated replacement also exercises owned model strings after input reuse.
    for (let i = 0; i < 10; i++) assert.equal(wasm.xyang_load_model(ptr, encoded.length), 0);
    const baseline = wasm.memory.buffer.byteLength;
    for (let i = 0; i < 200; i++) assert.equal(wasm.xyang_load_model(ptr, encoded.length), 0);
    assert.equal(wasm.memory.buffer.byteLength, baseline);
  } finally {
    wasm.xyang_free(ptr, encoded.length);
    wasm.xyang_reset();
  }
});

test("ABI reclaims per-validation memory", async () => {
  const { instance: { exports: wasm } } = await WebAssembly.instantiate(bytes, {});
  const encoder = new TextEncoder();
  const load = encoder.encode(model);
  const data = encoder.encode(valid);
  const ptr = wasm.xyang_alloc(Math.max(load.length, data.length));
  try {
    new Uint8Array(wasm.memory.buffer, ptr, load.length).set(load);
    assert.equal(wasm.xyang_load_model(ptr, load.length), 0);
    // Overwrite the entire original model input before reusing it for validation.
    new Uint8Array(wasm.memory.buffer, ptr, load.length).fill(0);
    new Uint8Array(wasm.memory.buffer, ptr, data.length).set(data);
    for (let i = 0; i < 10; i++) assert.equal(wasm.xyang_validate(ptr, data.length), 0);
    const baseline = wasm.memory.buffer.byteLength;
    for (let i = 0; i < 200; i++) assert.equal(wasm.xyang_validate(ptr, data.length), 0);
    assert.equal(wasm.memory.buffer.byteLength, baseline);
    const result = JSON.parse(new TextDecoder().decode(new Uint8Array(
      wasm.memory.buffer, wasm.xyang_result_ptr(), wasm.xyang_result_len(),
    )));
    assert.equal(result.valid, true);
  } finally {
    wasm.xyang_free(ptr, Math.max(load.length, data.length));
    wasm.xyang_reset();
  }
});

function assertResult(result, item) {
  assert.equal(result.valid, item.valid);
  const pairs = (errors) => [...new Set(errors.map((e) => JSON.stringify([
    e.document ?? "data", e.pointer ?? e.path, e.code,
  ])))].sort();
  assert.deepEqual(pairs(result.errors), pairs(item.errors ?? []));
  for (const expected of item.errors ?? []) {
    if (expected.message) assert.ok(result.errors.some((e) =>
      e.document === (expected.document ?? "data") && e.pointer === expected.path
      && e.code === expected.code && e.message.includes(expected.message)));
  }
}

async function nativeForms(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const found = [];
  for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
    if (entry.isDirectory()) found.push(...await nativeForms(new URL(`${entry.name}/`, dir)));
    else if (entry.name === "expected.yang.json") found.push(dir);
  }
  return found;
}

for (const dir of await nativeForms(new URL("../../tests/cases/", import.meta.url))) {
  const spec = JSON.parse(await readFile(new URL("case.json", dir), "utf8"));
  // Feature selection remains outside the minimal ABI.
  assert.equal(spec.features, undefined, "Add feature-option support before using this fixture");
  const validator = await createValidator(bytes);
  validator.loadModel(await readFile(new URL("expected.yang.json", dir), "utf8"));
  for (const item of spec.instances) {
    test(`${dir.pathname.split("/").at(-2)}: ${item.name}`, () => {
      const options = {};
      for (const key of ["rpc", "action", "direction"]) {
        if (key in item) options[key] = item[key];
      }
      if ("context" in item) options.context = JSON.stringify(item.context);
      const result = validator.validate(JSON.stringify(item.data), options);
      assertResult(result, item);
    });
  }
}

// Generate operation models from their existing YANG sources; never hand-edit forms.
const temporary = await mkdtemp(join(tmpdir(), "xyang-wasm-"));
try {
  const cases = new URL("../../tests/cases/operations/", import.meta.url);
  for (const entry of (await readdir(cases)).sort()) {
    const dir = new URL(`${entry}/`, cases);
    const spec = JSON.parse(await readFile(new URL("case.json", dir), "utf8"));
    const validator = await createValidator(bytes);
    if (!spec.features) {
      const output = join(temporary, `${entry}.yang.json`);
      const binary = `../zig-out/bin/xyang-zig${process.platform === "win32" ? ".exe" : ""}`;
      execFileSync(fileURLToPath(new URL(binary, import.meta.url)), [
        "convert", fileURLToPath(new URL(spec.module, dir)), "-o", output,
      ]);
      validator.loadModel(await readFile(output, "utf8"));
    }
    for (const item of spec.instances) {
      const skip = spec.features ? "Feature selection is not exposed by the Wasm API"
        : item.encoding === "native" ? "Native instance encoding is not exposed by the Wasm API"
        : item.action?.includes("/aug:") ? "This fixture requires loading a separate augmenting YANG module"
        : false;
      test(`${entry}: ${item.name}`, { skip }, () => {
        const options = {};
        for (const key of ["rpc", "action", "direction"]) {
          if (key in item) options[key] = item[key];
        }
        if ("context" in item) options.context = JSON.stringify(item.context);
        const run = () => validator.validate(JSON.stringify(item.data), options);
        if (item.usage_error) {
          assert.throws(run, (error) => error.code === "Usage" && error.message.includes(item.usage_error));
        } else {
          assertResult(run(), item);
        }
      });
    }
    if (entry === "context-validation") {
      test("context JSON text preserves integers beyond JavaScript's safe range", () => {
        const result = validator.validate('{"m:input":{"node":"n1"}}', {
          rpc: "use",
          context: '{"m:net":{"node":[{"name":"n1","cap":9007199254740993}]}}',
        });
        assert.equal(result.valid, false);
        assert.ok(result.errors.some((e) => e.document === "context"
          && e.code === "range" && e.message.includes("9007199254740993")));
      });
    }
  }
} finally {
  await rm(temporary, { recursive: true, force: true });
}

for (const options of ["{", "[]", '{"unknown":true}', '{"context":{}}',
  '{"rpc":1}', '{"action":false}', '{"direction":null}']) {
  test(`raw options ABI rejects ${options}`, async () => {
    const { instance: { exports: wasm } } = await WebAssembly.instantiate(bytes, {});
    const text = new TextEncoder().encode(options);
    const ptr = wasm.xyang_alloc(text.length);
    new Uint8Array(wasm.memory.buffer, ptr, text.length).set(text);
    try {
      // Options are checked before model/data access, so the data buffer is unused.
      assert.equal(wasm.xyang_validate_with_options(0, 0, ptr, text.length), 1);
      const result = JSON.parse(new TextDecoder().decode(new Uint8Array(
        wasm.memory.buffer, wasm.xyang_result_ptr(), wasm.xyang_result_len(),
      )));
      assert.equal(result.err, options === "{" ? "InvalidJson" : "Usage");
    } finally {
      wasm.xyang_free(ptr, text.length);
      wasm.xyang_reset();
    }
  });
}

for (const [label, options, code] of [
  ["context JSON", { rpc: "x", context: "{" }, "InvalidJson"],
  ["context injection", { rpc: "x", context: '{},"rpc":"other"' }, "InvalidJson"],
]) {
  test(`option decoding rejects invalid ${label} and recovers`, async () => {
    const validator = await createValidator(bytes);
    validator.loadModel(model);
    assert.throws(() => validator.validate(valid, options), { code });
    assert.equal(validator.validate(valid, {}).valid, true);
  });
}

for (const [label, options] of [
  ["null options", null],
  ["array options", []],
  ["unknown option", { typo: true }],
  ["context object", { context: {} }],
  ["rpc type", { rpc: 1 }],
  ["action type", { action: false }],
  ["direction type", { direction: null }],
  ["function option", { rpc() {} }],
]) {
  test(`JavaScript API rejects ${label}`, async () => {
    const validator = await createValidator(bytes);
    validator.loadModel(model);
    assert.throws(() => validator.validate(valid, options), TypeError);
  });
}
