import { cpSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const destination = resolve(root, "ts/dist/shared");
mkdirSync(destination, { recursive: true });
cpSync(resolve(root, "shared"), destination, { recursive: true });
