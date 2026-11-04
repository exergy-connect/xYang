import { defineConfig } from "tsdown";

export default defineConfig({
  entry: {
    index: "src/index.ts",
    cli: "src/cli.ts",
    "encoding-entry": "src/encoding-entry.ts",
    "types-entry": "src/types-entry.ts"
  },
  format: ["esm"],
  // Package exports and the CLI bin point at .js / .d.ts. With "type": "module"
  // those extensions are still ESM; skip tsdown's default .mjs / .d.mts names.
  fixedExtension: false,
  dts: true,
  sourcemap: true,
  clean: true,
  target: "node24",
  platform: "node",
  banner: {
    js: "#!/usr/bin/env node"
  }
});
