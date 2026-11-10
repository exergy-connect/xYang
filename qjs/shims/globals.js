import * as std from "qjs:std";

const B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

function b64decode(input) {
  const clean = String(input).replace(/[\r\n\t ]/g, "").replace(/=+$/, "");
  const out = new Uint8Array(Math.floor((clean.length * 3) / 4));
  let bits = 0;
  let acc = 0;
  let j = 0;
  for (const ch of clean) {
    const v = B64.indexOf(ch);
    if (v < 0) {
      throw new Error("invalid base64");
    }
    acc = (acc << 6) | v;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      out[j++] = (acc >> bits) & 0xff;
    }
  }
  return out.subarray(0, j);
}

if (typeof globalThis.Buffer === "undefined") {
  globalThis.Buffer = {
    from(value, encoding) {
      if (encoding === "base64") {
        return b64decode(value);
      }
      throw new Error("Buffer shim: only base64");
    }
  };
}

function format(args) {
  return args
    .map((value) => {
      if (typeof value === "string") {
        return value;
      }
      if (value instanceof Error) {
        return value.message;
      }
      try {
        return JSON.stringify(value);
      } catch {
        return String(value);
      }
    })
    .join(" ");
}

function writeLine(file, args) {
  file.puts(format(args) + "\n");
  file.flush();
}

const stderrLine = (...args) => writeLine(std.err, args);
const stdoutLine = (...args) => writeLine(std.out, args);

globalThis.console = globalThis.console || {};
console.warn = stderrLine;
console.error = stderrLine;
console.debug = stdoutLine;
