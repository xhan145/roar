// Byte-exact port of license.canonical_bytes (Python):
//   json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
// with json.dumps' default ensure_ascii=True. The fixture test proves parity —
// touch this file only with that test green.

function escapeString(s) {
  let out = "";
  for (const ch of s) {
    const code = ch.codePointAt(0);
    if (ch === '"') out += '\\"';
    else if (ch === "\\") out += "\\\\";
    else if (code === 0x08) out += "\\b";
    else if (code === 0x09) out += "\\t";
    else if (code === 0x0a) out += "\\n";
    else if (code === 0x0c) out += "\\f";
    else if (code === 0x0d) out += "\\r";
    else if (code < 0x20) out += "\\u" + code.toString(16).padStart(4, "0");
    else if (code < 0x7f) out += ch;
    else if (code <= 0xffff) out += "\\u" + code.toString(16).padStart(4, "0");
    else {
      // astral plane: Python emits the surrogate pair, escaped
      const c = code - 0x10000;
      const hi = 0xd800 + (c >> 10);
      const lo = 0xdc00 + (c & 0x3ff);
      out += "\\u" + hi.toString(16).padStart(4, "0")
           + "\\u" + lo.toString(16).padStart(4, "0");
    }
  }
  return out;
}

function encodeValue(v) {
  if (v === null) return "null";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "number") {
    if (!Number.isInteger(v)) {
      throw new Error("only integers are allowed in licence payloads");
    }
    return String(v);
  }
  if (typeof v === "string") return '"' + escapeString(v) + '"';
  throw new Error(`unsupported payload value type: ${typeof v}`);
}

export function canonicalBytes(payload) {
  const keys = Object.keys(payload).filter((k) => k !== "signature").sort();
  const parts = keys.map(
    (k) => '"' + escapeString(k) + '":' + encodeValue(payload[k]));
  return Buffer.from("{" + parts.join(",") + "}", "utf-8");
}
