import * as os from "qjs:os";
import * as std from "qjs:std";

function platformName() {
  return os.platform === "win32" ? "win32" : "posix";
}

function currentDir() {
  const [dir, err] = os.getcwd();
  if (err || !dir) {
    return platformName() === "win32" ? "C:\\" : "/";
  }
  return String(dir);
}

function environ() {
  try {
    return std.getenviron() || {};
  } catch {
    return {};
  }
}

function isSep(ch) {
  return ch === "/" || ch === "\\";
}

function isDriveLetter(ch) {
  return (ch >= "a" && ch <= "z") || (ch >= "A" && ch <= "Z");
}

function posixNormalize(p) {
  const abs = p.startsWith("/");
  const out = [];
  for (const seg of p.split("/")) {
    if (seg === "" || seg === ".") {
      continue;
    }
    if (seg === "..") {
      if (out.length && out[out.length - 1] !== "..") {
        out.pop();
      } else if (!abs) {
        out.push("..");
      }
      continue;
    }
    out.push(seg);
  }
  if (abs) {
    return `/${out.join("/")}` || "/";
  }
  return out.join("/") || ".";
}

function posixResolve(cwd, parts) {
  let resolved = "";
  for (let i = parts.length - 1; i >= 0 && !resolved.startsWith("/"); i--) {
    const part = parts[i];
    if (!part) {
      continue;
    }
    resolved = resolved ? `${part}/${resolved}` : part;
  }
  if (!resolved.startsWith("/")) {
    resolved = resolved ? `${cwd}/${resolved}` : cwd;
  }
  return posixNormalize(resolved);
}

function posixDirname(p) {
  if (p.length === 0) {
    return ".";
  }
  let end = p.length;
  while (end > 1 && p[end - 1] === "/") {
    end -= 1;
  }
  if (end === 1 && p[0] === "/") {
    return "/";
  }
  const slash = p.lastIndexOf("/", end - 1);
  if (slash < 0) {
    return ".";
  }
  if (slash === 0) {
    return "/";
  }
  return p.slice(0, slash);
}

function posixJoin(parts) {
  const kept = parts.filter((part) => part);
  if (kept.length === 0) {
    return ".";
  }
  return posixNormalize(kept.join("/"));
}

function winNormalizeTail(tail, allowAboveRoot) {
  const out = [];
  for (const seg of String(tail).split(/[\\/]+/)) {
    if (seg === "" || seg === ".") {
      continue;
    }
    if (seg === "..") {
      if (out.length && out[out.length - 1] !== "..") {
        out.pop();
      } else if (allowAboveRoot) {
        out.push("..");
      }
      continue;
    }
    out.push(seg);
  }
  return out.join("\\");
}

function winResolve(cwd, env, args) {
  let resolvedDevice = "";
  let resolvedTail = "";
  let resolvedAbsolute = false;

  for (let i = args.length - 1; i >= -1; i--) {
    let p;
    if (i >= 0) {
      p = args[i];
      if (p == null || p === "") {
        continue;
      }
      p = String(p);
    } else if (resolvedDevice.length === 0) {
      p = cwd;
      const onlyDot = args.length === 0 || (args.length === 1 && (args[0] === "" || args[0] === "."));
      if (onlyDot && (cwd[0] === "/" || cwd[0] === "\\")) {
        return cwd.replace(/\//g, "\\");
      }
    } else {
      p = (env && env[`=${resolvedDevice}`]) || cwd;
      const head = p.length >= 2 ? p.slice(0, 2).toLowerCase() : "";
      const third = p.length > 2 ? p.charCodeAt(2) : -1;
      if (head !== resolvedDevice.toLowerCase() && third === 92) {
        p = `${resolvedDevice}\\`;
      }
    }

    const len = p.length;
    let rootEnd = 0;
    let device = "";
    let isAbsolute = false;

    if (len === 1) {
      if (isSep(p[0])) {
        rootEnd = 1;
        isAbsolute = true;
      }
    } else if (isSep(p[0])) {
      isAbsolute = true;
      if (isSep(p[1])) {
        let j = 2;
        let last = j;
        while (j < len && !isSep(p[j])) {
          j += 1;
        }
        if (j < len && j !== last) {
          const firstPart = p.slice(last, j);
          last = j;
          while (j < len && isSep(p[j])) {
            j += 1;
          }
          if (j < len && j !== last) {
            last = j;
            while (j < len && !isSep(p[j])) {
              j += 1;
            }
            if (j === len || j !== last) {
              if (firstPart !== "." && firstPart !== "?") {
                device = `\\\\${firstPart}\\${p.slice(last, j)}`;
                rootEnd = j;
              } else {
                device = `\\\\${firstPart}`;
                rootEnd = 4;
              }
            }
          }
        }
      } else {
        rootEnd = 1;
      }
    } else if (isDriveLetter(p[0]) && p[1] === ":") {
      device = p.slice(0, 2);
      rootEnd = 2;
      if (len > 2 && isSep(p[2])) {
        isAbsolute = true;
        rootEnd = 3;
      }
    }

    if (device.length > 0) {
      if (resolvedDevice.length > 0) {
        if (device.toLowerCase() !== resolvedDevice.toLowerCase()) {
          continue;
        }
      } else {
        resolvedDevice = device;
      }
    }

    if (resolvedAbsolute) {
      if (resolvedDevice.length > 0) {
        break;
      }
    } else {
      resolvedTail = `${p.slice(rootEnd)}\\${resolvedTail}`;
      resolvedAbsolute = isAbsolute;
      if (isAbsolute && resolvedDevice.length > 0) {
        break;
      }
    }
  }

  resolvedTail = winNormalizeTail(resolvedTail, !resolvedAbsolute);
  if (resolvedAbsolute) {
    return `${resolvedDevice}\\${resolvedTail}`;
  }
  return `${resolvedDevice}${resolvedTail}` || ".";
}

function winRootLength(p) {
  const len = p.length;
  if (len === 0) {
    return 0;
  }
  if (isSep(p[0])) {
    if (len > 1 && isSep(p[1])) {
      let j = 2;
      while (j < len && !isSep(p[j])) {
        j += 1;
      }
      if (j > 2 && j < len && isSep(p[j])) {
        j += 1;
        const share = j;
        while (j < len && !isSep(p[j])) {
          j += 1;
        }
        if (j > share) {
          if (j < len && isSep(p[j])) {
            return j + 1;
          }
          return j;
        }
      }
      return 2;
    }
    return 1;
  }
  if (len >= 2 && isDriveLetter(p[0]) && p[1] === ":") {
    if (len > 2 && isSep(p[2])) {
      return 3;
    }
    return 2;
  }
  return 0;
}

function winDirname(p) {
  if (p.length === 0) {
    return ".";
  }
  if (p.length === 1) {
    return isSep(p[0]) ? p : ".";
  }
  const root = winRootLength(p);
  let end = p.length;
  while (end > root && isSep(p[end - 1])) {
    end -= 1;
  }
  if (end <= root) {
    return root === 0 ? "." : p.slice(0, root);
  }
  let i = end - 1;
  while (i >= root && !isSep(p[i])) {
    i -= 1;
  }
  if (i < root) {
    return root === 0 ? "." : p.slice(0, root);
  }
  return p.slice(0, i);
}

function winJoin(parts) {
  const kept = parts.filter((part) => part);
  if (kept.length === 0) {
    return ".";
  }
  const first = kept[0];
  let joined = kept.join("\\");
  if (isSep(first[0]) && first.length > 1 && isSep(first[1])) {
    joined = `\\\\${joined.replace(/^[/\\]+/, "")}`;
  }
  const absolute = isSep(joined[0]) || (joined.length > 2 && isDriveLetter(joined[0]) && joined[1] === ":" && isSep(joined[2]));
  if (joined.startsWith("\\\\")) {
    const rest = joined.slice(2);
    const slash = rest.indexOf("\\");
    if (slash < 0) {
      return `\\\\${rest}`;
    }
    const server = rest.slice(0, slash);
    const tail = winNormalizeTail(rest.slice(slash + 1), false);
    // Node's win32.join('//server', 'share') is '\\server\share\' — a UNC
    // root keeps the trailing separator when nothing follows the share.
    if (!tail.includes("\\")) {
      return `\\\\${server}\\${tail}${tail ? "\\" : ""}`;
    }
    return `\\\\${server}\\${tail}`;
  }
  if (joined.length >= 2 && isDriveLetter(joined[0]) && joined[1] === ":") {
    const drive = joined.slice(0, 2);
    const rooted = joined.length > 2 && isSep(joined[2]);
    const tail = winNormalizeTail(joined.slice(rooted ? 3 : 2), !rooted);
    if (rooted) {
      return `${drive}\\${tail}`;
    }
    return tail ? `${drive}${tail}` : drive;
  }
  const tail = winNormalizeTail(joined, true);
  if (absolute) {
    return `\\${tail}`;
  }
  return tail || ".";
}

export function resolve(...parts) {
  if (platformName() === "win32") {
    return winResolve(currentDir(), environ(), parts);
  }
  return posixResolve(currentDir(), parts);
}

export function dirname(p) {
  const text = String(p);
  if (platformName() === "win32") {
    return winDirname(text);
  }
  return posixDirname(text);
}

export function join(...parts) {
  if (platformName() === "win32") {
    return winJoin(parts.map((part) => String(part)));
  }
  return posixJoin(parts.map((part) => String(part)));
}

export default { resolve, dirname, join };
