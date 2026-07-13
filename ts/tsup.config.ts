import { defineConfig } from "tsup";

export default defineConfig({
  entry: {
    index: "src/index.ts",
    cli: "src/cli.ts",
    "encoding-entry": "src/encoding-entry.ts",
    "types-entry": "src/types-entry.ts"
  },
  format: ["esm"],
  // Declaration bundling uses tsup's bundled rollup-plugin-dts, which is not
  // compatible with TypeScript 7 yet. Keep typescript on 6.x until tsup catches up.
  dts: true,
  sourcemap: true,
  clean: true,
  target: "node24",
  platform: "node",
  banner: {
    js: "#!/usr/bin/env node"
  }
});
