/**
 * TypeScript benchmark worker: one phase per process, spawned by benchmarks/release_bench.py.
 * Mirrors benchmarks/worker.py. argv[2] is the JSON spec; prints one JSON line
 * {"samples_ms", "check", "peak_rss_bytes", "rss_source"}. Node startup, bundle load,
 * file reads, JSON.parse, and validator construction happen before the timed loop.
 */
import { readFileSync } from "node:fs";
import { parseYangFile, YangValidator } from "../src";

type ModuleSpec = { path: string; include: string[] };
type Spec = {
  phase: "startup" | "parse" | "validate";
  warmup: number;
  iterations: number;
  parse: ModuleSpec[];
  validate: { module: ModuleSpec; instance: string };
};

function timed(fn: () => void, warmup: number, iterations: number): number[] {
  for (let i = 0; i < warmup; i += 1) fn();
  const samples: number[] = [];
  for (let i = 0; i < iterations; i += 1) {
    const start = process.hrtime.bigint();
    fn();
    samples.push(Number(process.hrtime.bigint() - start) / 1e6);
  }
  return samples;
}

/** Peak RSS of this process: VmHWM on Linux; getrusage maxRSS (which can include the pre-exec parent) elsewhere. */
function peakRss(): [number, string] {
  try {
    const match = /^VmHWM:\s+(\d+)\s+kB/m.exec(readFileSync("/proc/self/status", "utf8"));
    if (match) return [Number(match[1]) * 1024, "VmHWM"];
  } catch {
    // not Linux
  }
  return [process.resourceUsage().maxRSS * 1024, "ru_maxrss"];
}

function emit(samples: number[], check: Record<string, unknown>): void {
  const [rss, source] = peakRss();
  process.stdout.write(`${JSON.stringify({ samples_ms: samples, check, peak_rss_bytes: rss, rss_source: source })}\n`);
}

const spec = JSON.parse(process.argv[2]) as Spec;
console.warn = () => {};

if (spec.phase === "startup") {
  emit([], {});
} else {
  let run: () => void;
  let check: Record<string, unknown>;
  if (spec.phase === "parse") {
    run = () => {
      for (const m of spec.parse) parseYangFile(m.path, { includePath: m.include });
    };
    check = { modules: spec.parse.length };
  } else if (spec.phase === "validate") {
    const target = spec.validate;
    const module = parseYangFile(target.module.path, { includePath: target.module.include });
    const data = JSON.parse(readFileSync(target.instance, "utf8")) as unknown;
    const validator = new YangValidator(module);
    run = () => {
      const result = validator.validateDetailed(data);
      if (!result.valid) throw new Error(`workload instance is invalid: ${JSON.stringify(result.errors.slice(0, 3))}`);
    };
    check = { valid: true };
  } else {
    throw new Error(`unknown phase ${String(spec.phase)}`);
  }
  emit(timed(run, spec.warmup, spec.iterations), check);
}
