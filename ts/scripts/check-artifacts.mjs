import { existsSync } from "node:fs";
import { resolve } from "node:path";

const required = ["dist/index.js", "dist/index.d.ts", "dist/index.browser.js", "dist/index.umd.min.global.js"];
const missing = required.filter((path) => !existsSync(resolve(process.cwd(), path)));

if (missing.length > 0) {
  console.error("Missing build artifacts:");
  for (const file of missing) {
    console.error(`- ${file}`);
  }
  process.exit(1);
}

console.log("All expected build artifacts are present.");


// Exercise the public package export rather than an internal dist filename.
const { parseYangString, YangValidator } = await import("@exergy-connect/xyang/browser");
const validator = new YangValidator(parseYangString(
  'module browser-smoke { namespace "urn:browser-smoke"; prefix b; leaf name { type string; } }'
));
if (!validator.validate({ name: "ok" }).isValid || validator.validate({ typo: true }).isValid) {
  throw new Error("Browser ESM validation smoke test failed");
}
console.log("Browser ESM export passed validation smoke test.");
