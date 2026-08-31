function parseScalar(value) {
  const trimmed = value.trim();
  if ((trimmed.startsWith('"') && trimmed.endsWith('"')) ||
      (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
    return trimmed.slice(1, -1);
  }
  if (/^(true|false)$/i.test(trimmed)) return trimmed.toLowerCase() === "true";
  if (/^-?\d+(?:\.\d+)?$/.test(trimmed)) return Number(trimmed);
  return trimmed;
}

export function parseFrontMatter(source) {
  const normalized = source.replace(/\r\n?/g, "\n");
  if (!normalized.startsWith("---\n")) return { meta: {}, body: normalized, bodyLineOffset: 0 };

  const closing = normalized.indexOf("\n---\n", 4);
  if (closing === -1) throw new Error("Front matter starts with --- but has no closing --- line.");

  const frontMatter = normalized.slice(4, closing);
  const meta = {};
  frontMatter.split("\n").forEach((line, index) => {
    if (!line.trim() || line.trimStart().startsWith("#")) return;
    const separator = line.indexOf(":");
    if (separator === -1) {
      throw new Error(`Invalid front matter on line ${index + 2}: expected key: value.`);
    }
    const key = line.slice(0, separator).trim();
    if (!key) throw new Error(`Invalid empty front matter key on line ${index + 2}.`);
    meta[key] = parseScalar(line.slice(separator + 1));
  });
  const bodyStart = closing + 5;
  const bodyLineOffset = (normalized.slice(0, bodyStart).match(/\n/g) || []).length;
  return { meta, body: normalized.slice(bodyStart), bodyLineOffset };
}
