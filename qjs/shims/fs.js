import * as std from "qjs:std";
import * as os from "qjs:os";

export function existsSync(p) {
  const [, err] = os.stat(String(p));
  return err === 0;
}

export function readFileSync(p, _enc) {
  if (p === 0) {
    return std.in.readAsString();
  }
  const text = std.loadFile(String(p));
  if (text === null) {
    const error = new Error(`ENOENT: no such file or directory, open '${p}'`);
    error.code = "ENOENT";
    throw error;
  }
  return text;
}

export function readdirSync(p) {
  const [names, err] = os.readdir(String(p));
  if (err !== 0) {
    const error = new Error(`ENOENT: no such file or directory, scandir '${p}'`);
    error.code = "ENOENT";
    throw error;
  }
  return names.filter((name) => name !== "." && name !== "..");
}

export default { existsSync, readFileSync, readdirSync };
