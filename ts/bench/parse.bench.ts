/**
 * Parse and validation timings for the TypeScript implementation. Not run in CI.
 *
 *   cd ts && npm run bench
 *   cd ts && npm run bench -- --cpu-prof   # writes a .cpuprofile per run to bench/profiles/
 *
 * Mirrors benchmarks/parse_bench.py: the same four modules (the largest both parsers load) and the same generated instance.
 */
import { dirname, resolve } from "node:path";
import { YangParser } from "../src/parser";
import { parseYangString } from "../src";
import { iterInstance } from "../src/encoding/instance";
import { YangValidator } from "../src/validator/yang-validator";

const repoRoot = process.env.XYANG_REPO_ROOT ?? resolve(process.cwd(), "..");

const PARSE_FILES = [
  "examples/ietf/ietf-alarms@2019-09-11.yang",
  "examples/ietf-yang-push/modules/ietf-subscribed-notifications@2019-09-09.yang",
  "examples/ietf-yang-push/modules/ietf-interfaces@2018-02-20.yang",
  "examples/meta-model.yang"
];

const INSTANCE_MODULE = `
module bench {
  yang-version 1.1;
  namespace "urn:bench";
  prefix b;
  container top {
    list interface {
      key name;
      leaf name { type string; }
      leaf mtu { type int64 { range "0..9000"; } }
      leaf speed { type uint64; }
      leaf enabled { type boolean; }
      leaf descr { type string { length "0..64"; } }
      leaf-list tags { type string; }
    }
    leaf marker { type empty; }
  }
}
`;

const ENTRIES = 10_000;

function rfcInstance(n: number): unknown {
  const rows = [];
  for (let i = 0; i < n; i += 1) {
    rows.push({ name: `eth${i}`, mtu: "1500", speed: String(1000 * i), enabled: i % 2 === 0, descr: `port ${i}`, tags: ["a", "b"] });
  }
  return { "bench:top": { interface: rows, marker: [null] } };
}

function nativeInstance(n: number): unknown {
  const rows: Record<string, unknown> = {};
  for (let i = 0; i < n; i += 1) {
    rows[`eth${i}`] = { mtu: 1500, speed: 1000 * i, enabled: i % 2 === 0, descr: `port ${i}`, tags: ["a", "b"] };
  }
  return { top: { interface: rows, marker: null } };
}

function median(samples: number[]): number {
  const sorted = [...samples].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)];
}

function time(fn: () => void, repeat: number): number {
  fn();
  const samples: number[] = [];
  for (let i = 0; i < repeat; i += 1) {
    const start = performance.now();
    fn();
    samples.push(performance.now() - start);
  }
  return median(samples);
}

function parseAll(): void {
  for (const rel of PARSE_FILES) {
    const path = resolve(repoRoot, rel);
    new YangParser({ include_path: [dirname(path)] }).parseFile(path);
  }
}

const module = parseYangString(INSTANCE_MODULE);
const rfc = rfcInstance(ENTRIES);
const native = nativeInstance(ENTRIES);
const validator = new YangValidator(module);

const phases: Array<[string, () => void]> = [
  ["parse (4 largest common modules, cold)", parseAll],
  [`iterInstance RFC (${ENTRIES} entries)`, () => void [...iterInstance(rfc, module, { nativeJson: false })]],
  [`iterInstance native (${ENTRIES} entries)`, () => void [...iterInstance(native, module, { nativeJson: true })]],
  [
    `validate RFC (${ENTRIES} entries)`,
    () => {
      const result = validator.validateDetailed(rfc);
      if (!result.valid) throw new Error(JSON.stringify(result.errors.slice(0, 3)));
    }
  ],
  [
    `validate native (${ENTRIES} entries)`,
    () => {
      const result = validator.validateDetailed(native, { nativeJson: true });
      if (!result.valid) throw new Error(JSON.stringify(result.errors.slice(0, 3)));
    }
  ]
];

const repeatArg = process.argv.indexOf("--repeat");
const repeat = repeatArg >= 0 ? Number(process.argv[repeatArg + 1]) : 7;
const originalWarn = console.warn;
console.warn = () => {};
for (const [name, fn] of phases) {
  process.stdout.write(`${name.padEnd(45)} ${time(fn, repeat).toFixed(1).padStart(9)} ms\n`);
}
console.warn = originalWarn;
