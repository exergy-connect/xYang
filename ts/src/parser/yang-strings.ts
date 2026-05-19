/**
 * RFC 7950 §6.2 quoted string decoding for YANG source text.
 */

export function unescapeYangQuotedString(content: string, quote: "'" | '"'): string {
  if (quote !== "'" && quote !== '"') {
    throw new Error(`quote must be "'" or '"', got ${JSON.stringify(quote)}`);
  }

  const out: string[] = [];
  let i = 0;
  const n = content.length;
  while (i < n) {
    const ch = content[i];
    if (ch !== "\\" || i + 1 >= n) {
      out.push(ch);
      i += 1;
      continue;
    }
    const nxt = content[i + 1];
    if (nxt === "\\") {
      out.push("\\");
      i += 2;
      continue;
    }
    if (nxt === "n") {
      out.push("\n");
      i += 2;
      continue;
    }
    if (nxt === "t") {
      out.push("\t");
      i += 2;
      continue;
    }
    if (quote === '"' && nxt === '"') {
      out.push('"');
      i += 2;
      continue;
    }
    if (quote === "'" && nxt === "'") {
      out.push("'");
      i += 2;
      continue;
    }
    if (nxt === "\r" || nxt === "\n") {
      i += 2;
      if (nxt === "\r" && i < n && content[i] === "\n") {
        i += 1;
      }
      while (i < n && (content[i] === " " || content[i] === "\t")) {
        i += 1;
      }
      continue;
    }
    out.push("\\", nxt);
    i += 2;
  }
  return out.join("");
}
