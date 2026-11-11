import { resolve } from "node:path";

export type AnydataValidationCli = "off" | "complete" | "candidate";

export type CommonCliArgs = {
  includePaths: string[];
  positional: string[];
};

export type ValidateCliArgs = CommonCliArgs & {
  anydataValidation: AnydataValidationCli;
  anydataModulePaths: string[];
  format: "text" | "json";
  /** ``null`` enables every declared feature. */
  features: Record<string, string[]> | null;
  nativeJson: boolean;
  /** `--rpc NAME`: validate the data as an instance of that rpc. */
  rpc: string | undefined;
  /** `--action PATH`: validate the data as an instance of the action at that data resource identifier. */
  action: string | undefined;
  /** `--output`: with `--rpc` or `--action`, the output instead of the input. */
  output: boolean;
  /** `--context FILE`: server data next to the operation node. */
  contextFile: string | undefined;
};

/**
 * Usage error (unknown command, unknown flag, missing or invalid option value).
 * The CLI prints the message on stderr and exits 2.
 */
export class CliUsageError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CliUsageError";
  }
}

type IncludeState = { includePaths: string[] };

type ValidateState = Omit<ValidateCliArgs, "positional">;

export type CliOptionView = {
  name: string;
  metavar?: string;
  help: string;
  takesValue: boolean;
  repeatable?: boolean;
};

type CliOption<S> = CliOptionView & {
  apply: (state: S, value: string | undefined) => void;
};

export type CliCommandView = {
  name: string;
  summary: string;
  description: string;
  positionals: readonly { name: string; help: string }[];
  options: readonly CliOptionView[];
  examples: readonly string[];
  notes?: readonly string[];
};

type CliCommand<S> = Omit<CliCommandView, "options"> & {
  options: readonly CliOption<S>[];
};

/**
 * Single registry for `xyang-ts` commands and options.
 *
 * Help text and argv parsing both read this list. `-h` and `--help` are
 * handled before parsing and are not option entries.
 *
 * To add a flag:
 * 1. Add the field on that command's state (`ValidateCliArgs` for validate).
 * 2. Add one object to that command's `options` (`name`, `help`, `takesValue`, `apply`).
 * Help lists it, and the parser accepts it, with no second flag table.
 * Then pass the field from `runValidate` into the validator.
 */
function includePathOption<S extends IncludeState>(): CliOption<S> {
  return {
    name: "--include-path",
    metavar: "DIR",
    takesValue: true,
    repeatable: true,
    help: "Directory searched for imported modules after the module file's own directory. Repeatable. Default: none.",
    apply(state, value) {
      if (value === undefined) {
        throw new CliUsageError("Missing directory after --include-path");
      }
      state.includePaths.push(resolve(value));
    }
  };
}

function parseFeaturesArg(raw: string | undefined): Record<string, string[]> | null {
  if (raw === undefined) {
    throw new CliUsageError("Missing JSON after --features");
  }
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch (error) {
    throw new CliUsageError(`--features must be a JSON object or null: ${(error as Error).message}`);
  }
  if (value === null) {
    return null;
  }
  if (typeof value !== "object" || Array.isArray(value)) {
    throw new CliUsageError("--features must be a JSON object mapping module names to feature names, or null");
  }
  const features: Record<string, string[]> = {};
  for (const [name, feats] of Object.entries(value)) {
    if (!Array.isArray(feats) || feats.some((feature) => typeof feature !== "string")) {
      throw new CliUsageError(`--features[${name}] must be an array of feature name strings`);
    }
    features[name] = feats;
  }
  return features;
}

const parseCommand: CliCommand<IncludeState> = {
  name: "parse",
  summary: "Parse a YANG file and print the module name",
  description:
    "Parse a YANG file and print the module name. Imports are resolved from the file's directory, then each --include-path.",
  positionals: [{ name: "<file.yang>", help: "Path to the .yang file." }],
  options: [includePathOption()],
  examples: [
    "xyang-ts parse --help",
    "xyang-ts parse -h",
    "xyang-ts parse module.yang",
    "xyang-ts parse --include-path ./modules module.yang"
  ]
};

const validateCommand: CliCommand<ValidateState> = {
  name: "validate",
  summary: "Validate JSON instance data against a YANG module",
  description:
    "Validate JSON instance data against a YANG module. Exit 0 when valid, 1 when invalid, and 2 for usage or a module that does not parse.",
  positionals: [
    { name: "<file.yang>", help: "Path to the .yang module." },
    {
      name: "[data.json|-]",
      help: "JSON instance. A file path, '-' to read stdin, or omit to read JSON from stdin. Default: stdin."
    }
  ],
  options: [
    includePathOption(),
    {
      name: "--native-json",
      takesValue: false,
      help: "Accept native dict-style JSON (keyed lists, JSON numbers, null for empty) instead of strict RFC 7951. Default: off.",
      apply(state) {
        state.nativeJson = true;
      }
    },
    {
      name: "--format",
      metavar: "text|json",
      takesValue: true,
      help: 'Output format. text prints "Valid." or errors. json prints {"valid","errors":[{"path","code","message"}]} on stdout and warnings on stderr. Values: text | json. Default: text.',
      apply(state, value) {
        if (value !== "text" && value !== "json") {
          throw new CliUsageError("--format must be text or json");
        }
        state.format = value;
      }
    },
    {
      name: "--rpc",
      metavar: "NAME",
      takesValue: true,
      help: 'Validate the data as rpc NAME (RFC 7950 §7.14). RFC 7951 input is {"module:input": {...}}; with --output it is {"module:output": {...}}. --native-json takes the bare parameters. Default direction: input.',
      apply(state, value) {
        if (value === undefined) {
          throw new CliUsageError("Missing rpc name after --rpc");
        }
        state.rpc = value;
      }
    },
    {
      name: "--action",
      metavar: "PATH",
      takesValue: true,
      help: "Validate the data as the action at PATH (RFC 7950 §7.15): the RFC 8040 §3.5.3 data resource identifier /module:list=key/action. Mutually exclusive with --rpc. Needs --context containing that instance. Default direction: input.",
      apply(state, value) {
        if (value === undefined) {
          throw new CliUsageError("Missing data resource identifier after --action");
        }
        state.action = value;
      }
    },
    {
      name: "--output",
      takesValue: false,
      help: "With --rpc or --action, validate the output instead of the input. Does not write a file. Requires --rpc or --action. Default: input.",
      apply(state) {
        state.output = true;
      }
    },
    {
      name: "--context",
      metavar: "FILE",
      takesValue: true,
      help: 'With --rpc or --action, JSON server data. Validated against the module first (errors carry "document": "context"), then joined to the operation node (RFC 7950 §6.4.1) so must and leafref can reach it. Required with --action. Default: none.',
      apply(state, value) {
        if (value === undefined) {
          throw new CliUsageError("Missing file after --context");
        }
        state.contextFile = value;
      }
    },
    {
      name: "--features",
      metavar: "JSON",
      takesValue: true,
      help: 'Enabled features as JSON {"module": ["feature", ...]}, or null to enable every declared feature. Default: null (all features).',
      apply(state, value) {
        state.features = parseFeaturesArg(value);
      }
    },
    {
      name: "--anydata-validation",
      metavar: "off|complete|candidate",
      takesValue: true,
      help: "Validate JSON under anydata (draft-ietf-netmod-yang-anydata-validation). off skips it; complete validates the subtree; candidate is structural only. Values: off | complete | candidate. Default: off.",
      apply(state, value) {
        if (value !== "off" && value !== "complete" && value !== "candidate") {
          throw new CliUsageError("--anydata-validation must be off, complete, or candidate");
        }
        state.anydataValidation = value;
      }
    },
    {
      name: "--anydata-module",
      metavar: "PATH",
      takesValue: true,
      repeatable: true,
      help: "Extra .yang file for the anydata module map. Repeatable. When anydata validation is on and this is omitted, every *.yang file in --include-path and the host directory is loaded. Default: none.",
      apply(state, value) {
        if (value === undefined) {
          throw new CliUsageError("Missing path after --anydata-module");
        }
        state.anydataModulePaths.push(resolve(value));
      }
    }
  ],
  examples: [
    "xyang-ts validate --help",
    "xyang-ts validate -h",
    "xyang-ts validate --format json module.yang data.json",
    "xyang-ts validate --rpc add-link --output --context state.json module.yang output.json",
    "xyang-ts validate --native-json --rpc add-link module.yang params.json",
    "xyang-ts validate --action /ex:interfaces/interface=eth0/reset --context state.json module.yang in.json"
  ],
  notes: [
    "Python xyang validate accepts JSON or YAML (.yaml/.yml, needs PyYAML). This command accepts JSON only.",
    "--output selects the rpc or action output. It does not write a file."
  ]
};

const convertCommand: CliCommand<IncludeState> = {
  name: "convert",
  summary: "Print JSON Schema with x-yang to stdout",
  description: "Print JSON Schema (2020-12) with x-yang metadata to stdout. Does not write a file.",
  positionals: [{ name: "<file.yang>", help: "Path to the .yang file." }],
  options: [includePathOption()],
  examples: [
    "xyang-ts convert --help",
    "xyang-ts convert -h",
    "xyang-ts convert module.yang",
    "xyang-ts convert --include-path ./modules module.yang"
  ],
  notes: [
    "Python xyang convert writes <stem>.yang.json beside the input, or the path given by -o/--output (the name is forced to end with .yang.json). This command does not accept -o or --output."
  ]
};

const COMMAND_LIST: readonly CliCommandView[] = [parseCommand, validateCommand, convertCommand];

const BY_NAME = new Map<string, CliCommandView>(COMMAND_LIST.map((command) => [command.name, command]));

export function cliCommands(): readonly CliCommandView[] {
  return COMMAND_LIST;
}

export function commandByName(name: string): CliCommandView | undefined {
  return BY_NAME.get(name);
}

function collectPositionals<S>(command: CliCommand<S>, rest: readonly string[], state: S): string[] {
  const byName = new Map(command.options.map((option) => [option.name, option]));
  const positional: string[] = [];
  for (let i = 0; i < rest.length; i += 1) {
    const arg = rest[i]!;
    const option = byName.get(arg);
    if (option) {
      if (option.takesValue) {
        const value = rest[i + 1];
        if (value === undefined) {
          option.apply(state, undefined);
          continue;
        }
        i += 1;
        option.apply(state, value);
        continue;
      }
      option.apply(state, undefined);
      continue;
    }
    if (arg.startsWith("-") && arg !== "-") {
      throw new CliUsageError(`unrecognized argument: ${arg}`);
    }
    positional.push(arg);
  }
  return positional;
}

/**
 * True when `-h` or `--help` appears as its own flag.
 * The token after a value-taking option is that option's value, so
 * `validate --format json --help` is help and `validate --format --help` is not.
 */
export function requestsHelp(
  options: readonly Pick<CliOptionView, "name" | "takesValue">[],
  rest: readonly string[]
): boolean {
  const takesValue = new Set(options.filter((option) => option.takesValue).map((option) => option.name));
  for (let i = 0; i < rest.length; i += 1) {
    const arg = rest[i];
    if (arg === "--help" || arg === "-h") {
      return true;
    }
    if (arg !== undefined && takesValue.has(arg)) {
      i += 1;
    }
  }
  return false;
}

export function parseCommonArgs(rest: string[], commandName: "parse" | "convert" = "parse"): CommonCliArgs {
  const command = commandName === "convert" ? convertCommand : parseCommand;
  const state: IncludeState = { includePaths: [] };
  const positional = collectPositionals(command, rest, state);
  return { includePaths: state.includePaths, positional };
}

export function parseValidateArgs(rest: string[]): ValidateCliArgs {
  const state: ValidateState = {
    includePaths: [],
    anydataModulePaths: [],
    anydataValidation: "off",
    format: "text",
    features: null,
    nativeJson: false,
    rpc: undefined,
    action: undefined,
    output: false,
    contextFile: undefined
  };
  const positional = collectPositionals(validateCommand, rest, state);
  if (state.rpc !== undefined && state.action !== undefined) {
    throw new CliUsageError("--rpc and --action are mutually exclusive");
  }
  if (state.rpc === undefined && state.action === undefined && (state.output || state.contextFile !== undefined)) {
    throw new CliUsageError("--output and --context apply only together with --rpc or --action");
  }
  return { ...state, positional };
}

function formatUsageOption(option: CliOptionView): string {
  const value = option.takesValue ? ` ${option.metavar ?? "VALUE"}` : "";
  const repeat = option.repeatable ? "..." : "";
  return `[${option.name}${value}]${repeat}`;
}

function formatOptionLines(options: readonly CliOptionView[]): string[] {
  const lines = ["  -h, --help", "        Show this help and exit"];
  for (const option of options) {
    const value = option.takesValue ? ` ${option.metavar ?? "VALUE"}` : "";
    const repeat = option.repeatable ? " (repeatable)" : "";
    lines.push(`  ${option.name}${value}${repeat}`);
    lines.push(`        ${option.help}`);
  }
  return lines;
}

export function formatGlobalHelp(): string {
  const lines = [
    "usage: xyang-ts [-h] <command>",
    "",
    "Parse YANG modules, validate RFC 7951 JSON instance data, and export JSON Schema.",
    "",
    "commands:"
  ];
  for (const command of COMMAND_LIST) {
    lines.push(`  ${command.name.padEnd(10)} ${command.summary}`);
  }
  lines.push("", "options:", "  -h, --help  Show this help and exit", "", "examples:");
  for (const example of [
    "xyang-ts --help",
    "xyang-ts -h",
    "xyang-ts parse module.yang",
    "xyang-ts validate --format json module.yang data.json",
    "xyang-ts convert module.yang"
  ]) {
    lines.push(`  ${example}`);
  }
  lines.push(
    "",
    "notes:",
    "  There is no --version flag. Python xyang -V prints the installed package version.",
    "  Python xyang convert writes <stem>.yang.json beside the input, or the path given by -o/--output. xyang-ts convert prints JSON Schema to stdout.",
    ""
  );
  return lines.join("\n");
}

export function formatCommandHelp(command: CliCommandView): string {
  const usageOptions = command.options.map(formatUsageOption).join(" ");
  const positionals = command.positionals.map((positional) => positional.name).join(" ");
  const lines = [
    `usage: xyang-ts ${command.name} [-h]${usageOptions ? ` ${usageOptions}` : ""}${positionals ? ` ${positionals}` : ""}`,
    "",
    command.description,
    "",
    "positionals:"
  ];
  for (const positional of command.positionals) {
    lines.push(`  ${positional.name}`);
    lines.push(`        ${positional.help}`);
  }
  lines.push("", "options:", ...formatOptionLines(command.options), "", "examples:");
  for (const example of command.examples) {
    lines.push(`  ${example}`);
  }
  if (command.notes?.length) {
    lines.push("", "notes:");
    for (const note of command.notes) {
      lines.push(`  ${note}`);
    }
  }
  lines.push("");
  return lines.join("\n");
}
