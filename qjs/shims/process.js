import * as std from "qjs:std";
import * as os from "qjs:os";

const scriptArgs = globalThis.scriptArgs || ["xyang-ts"];
const argv = [scriptArgs[0] || "xyang-ts", "xyang-ts", ...scriptArgs.slice(1)];

function writeTo(file, value) {
  file.puts(String(value));
  file.flush();
  return true;
}

const stdout = {
  write(value) {
    return writeTo(std.out, value);
  }
};

const stderr = {
  write(value) {
    return writeTo(std.err, value);
  }
};

function exit(code) {
  try {
    std.out.flush();
  } catch {
    /* already closed */
  }
  try {
    std.err.flush();
  } catch {
    /* already closed */
  }
  std.exit(code ?? 0);
}

const proc = {
  argv,
  stdout,
  stderr,
  exit,
  env: std.getenviron(),
  platform: os.platform
};

export default proc;
export { argv, stdout, stderr, exit };
