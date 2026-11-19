import { createRequire } from 'node:module';
import { copyFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
const require = createRequire(resolve(root, 'ts/package.json'));
const { build } = require('esbuild');
if (process.argv[2]) {
  await copyFile(resolve(process.argv[2], 'yang/lab-net.yang'), resolve(here, 'lab-net.yang'));
}
const aliases = {
  'xyang': resolve(root, 'ts/src/index.ts'),
  'node:fs': resolve(root, 'ts/src/shims/node-fs-browser.ts'),
  'node:path': resolve(root, 'ts/src/shims/node-path-browser.ts'),
  'node:url': resolve(root, 'ts/src/shims/node-url-browser.ts'),
};
await build({ entryPoints: [resolve(here, 'app.js')], outfile: resolve(here, 'main.js'), bundle: true,
  platform: 'browser', format: 'esm', target: 'es2022', alias: aliases });
console.log(`Built browser bundle in ${here}.`);
