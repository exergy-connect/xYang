/**
 * Translate YANG `pattern` arguments (XSD regular expressions, RFC 7950 §9.4.5,
 * XML Schema Part 2 Appendix F) into anchored JavaScript `RegExp`s with the `u` flag.
 *
 * Supported beyond plain characters, classes, groups, `|` and quantifiers: `\p{X}` / `\P{X}`
 * for Unicode general categories, `\i` / `\I` / `\c` / `\C` (XML name characters), and the
 * XSD meanings of `.`, `\d`, `\s`, `\w` and their negations. Other XSD constructs (block
 * escapes such as `\p{IsBasicLatin}`, class subtraction `[a-z-[aeiou]]`) throw
 * {@link YangSemanticError}. Same rules as Python `xyang.xsd_regex`.
 */
import { YangSemanticError } from "./core/errors";

type Range = [number, number];

const MAX_CP = 0x10ffff;

const GENERAL_CATEGORIES: Record<string, string[]> = {
  L: ["Lu", "Ll", "Lt", "Lm", "Lo"],
  M: ["Mn", "Mc", "Me"],
  N: ["Nd", "Nl", "No"],
  P: ["Pc", "Pd", "Ps", "Pe", "Pi", "Pf", "Po"],
  Z: ["Zs", "Zl", "Zp"],
  S: ["Sm", "Sc", "Sk", "So"],
  C: ["Cc", "Cf", "Co", "Cn"]
};
const CATEGORY_NAMES = new Set<string>([
  ...Object.keys(GENERAL_CATEGORIES),
  ...Object.values(GENERAL_CATEGORIES).flat()
]);

// XML 1.0 (5th ed.) NameStartChar / NameChar.
const NAME_START: Range[] = [
  [0x3a, 0x3a], [0x41, 0x5a], [0x5f, 0x5f], [0x61, 0x7a], [0xc0, 0xd6], [0xd8, 0xf6],
  [0xf8, 0x2ff], [0x370, 0x37d], [0x37f, 0x1fff], [0x200c, 0x200d], [0x2070, 0x218f],
  [0x2c00, 0x2fef], [0x3001, 0xd7ff], [0xf900, 0xfdcf], [0xfdf0, 0xfffd], [0x10000, 0xeffff]
];
const NAME_CHAR: Range[] = [
  ...NAME_START,
  [0x2d, 0x2e], [0x30, 0x39], [0xb7, 0xb7], [0x300, 0x36f], [0x203f, 0x2040]
];
const XSD_SPACE: Range[] = [[0x9, 0xa], [0xd, 0xd], [0x20, 0x20]];
const XSD_DOT_EXCLUDED: Range[] = [[0xa, 0xa], [0xd, 0xd]];
const SINGLE_ESCAPES: Record<string, number> = { n: 0xa, r: 0xd, t: 0x9 };
const SINGLE_ESCAPE_LITERALS = new Set("\\|.-^?*+{}()[]".split(""));
const XSD_W_EXCLUDED = "\\p{P}\\p{Z}\\p{C}";

function normalize(ranges: Range[]): Range[] {
  const out: Range[] = [];
  for (const [lo, hi] of [...ranges].sort((a, b) => a[0] - b[0] || a[1] - b[1])) {
    const last = out[out.length - 1];
    if (last && lo <= last[1] + 1) {
      last[1] = Math.max(last[1], hi);
    } else {
      out.push([lo, hi]);
    }
  }
  return out;
}

function complement(ranges: Range[]): Range[] {
  const out: Range[] = [];
  let next = 0;
  for (const [lo, hi] of normalize(ranges)) {
    if (lo > next) {
      out.push([next, lo - 1]);
    }
    next = hi + 1;
  }
  if (next <= MAX_CP) {
    out.push([next, MAX_CP]);
  }
  return out;
}

const cp = (n: number): string => `\\u{${n.toString(16).toUpperCase()}}`;

function render(ranges: Range[]): string {
  return ranges.map(([lo, hi]) => (lo === hi ? cp(lo) : `${cp(lo)}-${cp(hi)}`)).join("");
}

/**
 * One parsed escape. `body` is class content (no brackets); `complementBody` is set when the
 * escape is "anything except `complementBody`" and cannot be written as class content.
 */
type Atom = { body: string; single?: number; complementBody?: string };

class Translator {
  private pos = 0;

  constructor(private readonly src: string) {}

  private unsupported(construct: string): YangSemanticError {
    return new YangSemanticError(
      `unsupported XSD regex construct '${construct}' in pattern '${this.src}'`
    );
  }

  private peek(offset = 0): string {
    return this.src[this.pos + offset] ?? "";
  }

  /** Escape at `pos` (after the backslash). */
  private escape(): Atom {
    const ch = this.peek();
    if (!ch) {
      throw this.unsupported("\\");
    }
    this.pos += 1;
    if (ch === "p" || ch === "P") {
      if (this.peek() !== "{") {
        throw this.unsupported(`\\${ch}`);
      }
      const end = this.src.indexOf("}", this.pos);
      if (end < 0) {
        throw this.unsupported(this.src.slice(this.pos - 2));
      }
      const name = this.src.slice(this.pos + 1, end);
      this.pos = end + 1;
      if (!CATEGORY_NAMES.has(name)) {
        throw this.unsupported(`\\${ch}{${name}}`);
      }
      return { body: `\\${ch}{${name}}` };
    }
    if (ch in SINGLE_ESCAPES) {
      const n = SINGLE_ESCAPES[ch]!;
      return { body: cp(n), single: n };
    }
    if (SINGLE_ESCAPE_LITERALS.has(ch)) {
      const n = ch.codePointAt(0)!;
      return { body: cp(n), single: n };
    }
    switch (ch) {
      case "d":
        return { body: "\\p{Nd}" };
      case "D":
        return { body: "\\P{Nd}" };
      case "s":
        return { body: render(XSD_SPACE) };
      case "S":
        return { body: render(complement(XSD_SPACE)) };
      case "w":
        return { body: "", complementBody: XSD_W_EXCLUDED };
      case "W":
        return { body: XSD_W_EXCLUDED };
      case "i":
        return { body: render(NAME_START) };
      case "I":
        return { body: render(complement(NAME_START)) };
      case "c":
        return { body: render(NAME_CHAR) };
      case "C":
        return { body: render(complement(NAME_CHAR)) };
      default:
        throw this.unsupported(`\\${ch}`);
    }
  }

  private classAtom(): Atom {
    const ch = this.peek();
    if (ch === "\\") {
      this.pos += 1;
      return this.escape();
    }
    if (ch === "[") {
      throw this.unsupported("[");
    }
    const n = this.src.codePointAt(this.pos)!;
    this.pos += String.fromCodePoint(n).length;
    return { body: cp(n), single: n };
  }

  /** `[...]` at `pos` (after `[`). */
  private charClass(): string {
    const start = this.pos - 1;
    const negated = this.peek() === "^";
    if (negated) {
      this.pos += 1;
    }
    let body = "";
    const extra: string[] = [];
    let first = true;
    for (;;) {
      const ch = this.peek();
      if (!ch) {
        throw new YangSemanticError(`unterminated character class in pattern ${JSON.stringify(this.src)}`);
      }
      if (ch === "]" && !first) {
        this.pos += 1;
        break;
      }
      if (ch === "-" && this.peek(1) === "[") {
        const end = this.src.indexOf("]", this.pos);
        throw this.unsupported(this.src.slice(start, end >= 0 ? end + 2 : this.src.length));
      }
      first = false;
      const lo = this.classAtom();
      if (lo.single !== undefined && this.peek() === "-" && this.peek(1) !== "]" && this.peek(1) !== "[") {
        this.pos += 1;
        const hi = this.classAtom();
        if (hi.single === undefined) {
          throw this.unsupported(this.src.slice(start, this.pos));
        }
        if (hi.single < lo.single) {
          throw new YangSemanticError(`invalid character range in pattern ${JSON.stringify(this.src)}`);
        }
        body += `${cp(lo.single)}-${cp(hi.single)}`;
      } else if (lo.complementBody !== undefined) {
        extra.push(`[^${lo.complementBody}]`);
      } else {
        body += lo.body;
      }
    }
    if (extra.length === 0) {
      return `[${negated ? "^" : ""}${body}]`;
    }
    const positive = `(?:${[...(body ? [`[${body}]`] : []), ...extra].join("|")})`;
    return negated ? `(?:(?!${positive})[\\s\\S])` : positive;
  }

  translate(): string {
    let out = "";
    while (this.pos < this.src.length) {
      const ch = this.peek();
      if (ch === "\\") {
        this.pos += 1;
        const atom = this.escape();
        out += atom.complementBody !== undefined ? `[^${atom.complementBody}]` : `[${atom.body}]`;
      } else if (ch === "[") {
        this.pos += 1;
        out += this.charClass();
      } else if (ch === ".") {
        this.pos += 1;
        out += `[^${render(XSD_DOT_EXCLUDED)}]`;
      } else if (ch === "(") {
        if (this.peek(1) === "?") {
          throw this.unsupported("(?");
        }
        this.pos += 1;
        out += "(?:";
      } else if ("|)*+?".includes(ch)) {
        this.pos += 1;
        out += ch;
      } else if (ch === "{") {
        const m = /\{\d+(,\d*)?\}/y;
        m.lastIndex = this.pos;
        const hit = m.exec(this.src);
        if (!hit) {
          throw this.unsupported("{");
        }
        this.pos += hit[0].length;
        out += hit[0];
      } else {
        const n = this.src.codePointAt(this.pos)!;
        this.pos += String.fromCodePoint(n).length;
        out += /[A-Za-z0-9]/.test(ch) ? ch : cp(n);
      }
    }
    return out;
  }
}

const cache = new Map<string, RegExp>();

/** Compile an XSD regex to an anchored `RegExp` (`u` flag). Throws {@link YangSemanticError}. */
export function translateXsdRegex(pattern: string): RegExp {
  const hit = cache.get(pattern);
  if (hit) {
    return hit;
  }
  const body = new Translator(pattern).translate();
  let rx: RegExp;
  try {
    rx = new RegExp(`^(?:${body})$`, "u");
  } catch (e) {
    throw new YangSemanticError(`invalid pattern ${JSON.stringify(pattern)}: ${e instanceof Error ? e.message : String(e)}`);
  }
  cache.set(pattern, rx);
  return rx;
}
