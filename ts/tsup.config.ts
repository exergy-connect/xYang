import { defineConfig } from "tsup";

export default defineConfig([
  {
    entry: {
      index: "src/index.ts",
      cli: "src/cli.ts",
      "encoding-entry": "src/encoding-entry.ts",
      "types-entry": "src/types-entry.ts"
    },
    format: ["esm"],
    dts: true,
    sourcemap: true,
    clean: true,
    target: "node24",
    platform: "node",
    banner: {
      js: "#!/usr/bin/env node"
    }
  },
  {
    entry: {
      "index.umd.min": "src/index.ts"
    },
    format: ["iife"],
    globalName: "xYang",
    minify: true,
    dts: false,
    sourcemap: true,
    clean: false,
    target: "es2022",
    platform: "browser"
  }
]);
