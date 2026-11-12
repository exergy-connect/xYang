/** Create an independent validator from the bytes of xyang.wasm (no WASI needed).
 * Model and instance arguments are JSON text, preserving exact numeric literals.
 */
export async function createValidator(bytes) {
  const { instance } = await WebAssembly.instantiate(bytes, {});
  const wasm = instance.exports;
  const encoder = new TextEncoder();
  const decoder = new TextDecoder();

  function allocate(json) {
    if (typeof json !== "string") throw new TypeError("Expected JSON text");
    const input = encoder.encode(json);
    // Even an empty input needs a valid address for the guest's zero-length slice.
    const size = Math.max(1, input.length);
    const ptr = wasm.xyang_alloc(size);
    if (!ptr) throw new Error("Wasm input allocation failed");
    new Uint8Array(wasm.memory.buffer, ptr, input.length).set(input);
    return { ptr, size, length: input.length };
  }

  function call(fn, json, options) {
    const input = allocate(json);
    let extra;
    try {
      if (options !== undefined) extra = allocate(options);
      const status = extra
        ? fn(input.ptr, input.length, extra.ptr, extra.length)
        : fn(input.ptr, input.length);
      // Guest calls can grow memory; always acquire a fresh view afterwards.
      const result = JSON.parse(decoder.decode(new Uint8Array(
        wasm.memory.buffer, wasm.xyang_result_ptr(), wasm.xyang_result_len(),
      )));
      if (status !== 0) {
        const error = new Error(result.message);
        error.code = result.err;
        throw error;
      }
      return result;
    } finally {
      if (extra) wasm.xyang_free(extra.ptr, extra.size);
      wasm.xyang_free(input.ptr, input.size);
    }
  }

  return {
    loadModel: (json) => call(wasm.xyang_load_model, json),
    validate(json, options) {
      if (options === undefined) return call(wasm.xyang_validate, json);
      if (options === null || typeof options !== "object" || Array.isArray(options)) {
        throw new TypeError("Expected a validation options object");
      }
      for (const key of Object.keys(options)) {
        if (!["rpc", "action", "direction", "context"].includes(key)) {
          throw new TypeError(`Unknown validation option: ${key}`);
        }
      }
      const encoded = {};
      for (const key of ["rpc", "action", "direction", "context"]) {
        const value = options[key];
        if (value === undefined) continue;
        if (typeof value !== "string") {
          throw new TypeError(key === "context" ? "Expected context as JSON text" : `Expected ${key} as a string`);
        }
        encoded[key] = value;
      }
      // The guest parses context text, preserving exact numeric literals.
      return call(wasm.xyang_validate_with_options, json, JSON.stringify(encoded));
    },
    reset: () => wasm.xyang_reset(),
  };
}
