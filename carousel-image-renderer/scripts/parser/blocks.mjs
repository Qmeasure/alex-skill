import { METHODOLOGY_3X4 } from "../../assets/methodology-3x4.mjs";
import { escapeHtml, parseInline, safeUrl } from "./text.mjs";

function parseDirective(name, content, lineNumber, inline) {
  const raw = content.trim();
  if (name === "section" || name === "marker" || name === "callout" || name === "risk" || name === "lead" || name === "source") {
    if (!raw) throw new Error(`Empty :::${name} directive near line ${lineNumber}.`);
    return { type: name, html: inline(raw.replace(/\n+/g, " ")), raw };
  }
  if (name === "thumbnails") {
    const images = content.split("\n").map((line) => line.trim()).filter(Boolean).map((line, index) => {
      const match = line.match(/^!\[([^\]]*)\]\((<[^>]+>|[^\s)]+)(?:\s+["']([^"']*)["'])?\)$/);
      if (!match) throw new Error(`Invalid thumbnail near line ${lineNumber + index + 1}: use ![alt](path) syntax.`);
      const src = safeUrl(match[2], "image");
      if (!src) throw new Error(`Invalid thumbnail image URL near line ${lineNumber + index + 1}.`);
      return { alt: match[1], src };
    });
    if (!images.length) throw new Error(`Empty :::thumbnails directive near line ${lineNumber}.`);
    return { type: "thumbnails", images };
  }
  if (name === "metrics") {
    const items = content.split("\n").map((line) => line.trim()).filter(Boolean).map((line) => {
      const withoutBullet = line.replace(/^[-*]\s+/, "");
      const separator = withoutBullet.indexOf("|");
      if (separator === -1) {
        throw new Error(`Invalid metric near line ${lineNumber}: use - label | value.`);
      }
      const label = withoutBullet.slice(0, separator).trim();
      const value = withoutBullet.slice(separator + 1).trim();
      if (!label || !value) throw new Error(`Metric label and value must both be present near line ${lineNumber}.`);
      return { labelHtml: inline(label), valueHtml: inline(value), label, value };
    });
    if (!items.length) throw new Error(`Empty :::metrics directive near line ${lineNumber}.`);
    return { type: "metrics", items };
  }
  throw new Error(`Unsupported directive :::${name} near line ${lineNumber}.`);
}

function fixedMethodology3x4Block(inline) {
  const scenes = METHODOLOGY_3X4.scenes.map((value) => ({ raw: value, html: inline(value) }));
  const entryPaths = METHODOLOGY_3X4.entryPaths.map((value) => ({ raw: value, html: inline(value) }));
  const raw = [
    METHODOLOGY_3X4.title,
    METHODOLOGY_3X4.identity,
    METHODOLOGY_3X4.scenesLabel,
    ...METHODOLOGY_3X4.scenes,
    METHODOLOGY_3X4.entryPathsLabel,
    ...METHODOLOGY_3X4.entryPaths
  ].join("\n");
  return {
    type: "methodology-3x4",
    titleHtml: inline(METHODOLOGY_3X4.title),
    identityHtml: inline(METHODOLOGY_3X4.identity),
    scenesLabelHtml: inline(METHODOLOGY_3X4.scenesLabel),
    scenes,
    entryPathsLabelHtml: inline(METHODOLOGY_3X4.entryPathsLabel),
    entryPaths,
    raw
  };
}

function extractFootnotes(body) {
  const lines = body.split("\n");
  const kept = [];
  const definitions = [];
  for (let index = 0; index < lines.length; index += 1) {
    const match = lines[index].match(/^ {0,3}\[\^([^\]]+)\]:\s*(.*)$/);
    if (!match) {
      kept.push(lines[index]);
      continue;
    }
    const content = [match[2]];
    kept.push("");
    while (index + 1 < lines.length && /^(?: {2,}|\t)\S/.test(lines[index + 1])) {
      content.push(lines[index + 1].trim());
      kept.push("");
      index += 1;
    }
    definitions.push({ id: match[1], raw: content.join(" ").trim(), line: index - content.length + 2 });
  }
  return { body: kept.join("\n"), definitions };
}

function splitTableRow(line) {
  let source = line.trim();
  if (source.startsWith("|")) source = source.slice(1);
  if (source.endsWith("|") && !source.endsWith("\\|")) source = source.slice(0, -1);
  const cells = [];
  let current = "";
  for (let index = 0; index < source.length; index += 1) {
    if (source[index] === "\\" && source[index + 1] === "|") {
      current += "|";
      index += 1;
    } else if (source[index] === "|") {
      cells.push(current.trim());
      current = "";
    } else {
      current += source[index];
    }
  }
  cells.push(current.trim());
  return cells;
}

function isTableDelimiter(line) {
  if (!line.includes("|")) return false;
  const cells = splitTableRow(line);
  return cells.length >= 2 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function parseTable(lines, startIndex, inline) {
  const headerCells = splitTableRow(lines[startIndex]);
  const delimiterCells = splitTableRow(lines[startIndex + 1]);
  const alignments = delimiterCells.map((cell) => cell.startsWith(":") && cell.endsWith(":") ? "center" : cell.endsWith(":") ? "right" : "left");
  const rows = [];
  let index = startIndex + 2;
  while (index < lines.length && lines[index].trim() && lines[index].includes("|")) {
    const cells = splitTableRow(lines[index]);
    while (cells.length < headerCells.length) cells.push("");
    rows.push(cells.slice(0, headerCells.length).map((cell) => ({ html: inline(cell), raw: cell })));
    index += 1;
  }
  return {
    block: {
      type: "table",
      headers: headerCells.map((cell) => ({ html: inline(cell), raw: cell })),
      rows,
      alignments: alignments.slice(0, headerCells.length),
      columnCount: headerCells.length
    },
    nextIndex: index
  };
}

function matchListLine(line) {
  const match = line.match(/^(\s*)([-+*]|\d+\.)\s+(.+)$/);
  if (!match) return null;
  return {
    indent: match[1].replace(/\t/g, "    ").length,
    ordered: /^\d/.test(match[2]),
    text: match[3]
  };
}

function parseList(lines, startIndex, inline, baseIndent = matchListLine(lines[startIndex]).indent) {
  const first = matchListLine(lines[startIndex]);
  const ordered = first.ordered;
  const items = [];
  let index = startIndex;
  while (index < lines.length) {
    const match = matchListLine(lines[index]);
    if (!match || match.indent !== baseIndent || match.ordered !== ordered) break;
    let raw = match.text;
    const children = [];
    index += 1;
    while (index < lines.length) {
      const nested = matchListLine(lines[index]);
      if (nested && nested.indent > baseIndent) {
        const parsed = parseList(lines, index, inline, nested.indent);
        children.push(parsed.block);
        index = parsed.nextIndex;
        continue;
      }
      if (!lines[index].trim()) break;
      const indentation = (lines[index].match(/^(\s*)/)?.[1] || "").replace(/\t/g, "    ").length;
      if (indentation > baseIndent) {
        raw += `\n${lines[index].trim()}`;
        index += 1;
        continue;
      }
      break;
    }
    const task = raw.match(/^\[([ xX])\]\s+([\s\S]+)$/);
    items.push({
      html: inline(task ? task[2] : raw),
      raw: task ? task[2] : raw,
      task: Boolean(task),
      checked: task ? task[1].toLowerCase() === "x" : false,
      children
    });
  }
  return { block: { type: "list", ordered, items }, nextIndex: index };
}

function parseImageLine(line) {
  const match = line.trim().match(/^!\[([^\]]*)\]\((<[^>]+>|[^\s)]+)(?:\s+["']([^"']*)["'])?\)$/);
  if (!match) return null;
  const src = safeUrl(match[2], "image");
  return src ? { alt: match[1], src, title: match[3] || "" } : null;
}

function isHorizontalRule(line) {
  return /^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line);
}

function isRawHtmlStart(line) {
  return /^\s*<(?:div|p|aside|section|blockquote|h[1-6]|ul|ol|li|strong|em|mark)\b/i.test(line);
}

function sanitizeRawHtml(source) {
  let html = escapeHtml(source);
  html = html.replace(/&lt;br\s*\/?&gt;/gi, "<br>");
  html = html.replace(/&lt;(\/)?(div|p|aside|section|blockquote|h[1-6]|ul|ol|li|strong|b|em|i|u|mark|small|sub|sup|kbd|code|span)(?:\s+[\s\S]*?)?&gt;/gi,
    (_, closing, name) => `<${closing ? "/" : ""}${name.toLowerCase()}>`);
  return html;
}

function isBlockStart(lines, index) {
  const line = lines[index] || "";
  if (/^:::\w/.test(line) || /^\s*(?:`{3,}|~{3,})/.test(line) || /^(#{1,6})\s+/.test(line)) return true;
  if (/^>\s?/.test(line) || matchListLine(line) || isHorizontalRule(line) || parseImageLine(line) || isRawHtmlStart(line)) return true;
  return index + 1 < lines.length && line.includes("|") && isTableDelimiter(lines[index + 1]);
}

function parseBlockLines(body, footnotes, lineOffset = 0) {
  const lines = body.split("\n");
  const blocks = [];
  const footnoteNumbers = new Map(footnotes.map((definition, index) => [definition.id, index + 1]));
  const inline = (value) => parseInline(value, { footnoteNumbers });
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    const fence = line.match(/^\s*(`{3,}|~{3,})\s*([\w+-]*)\s*$/);
    if (fence) {
      const marker = fence[1][0];
      const minimumLength = fence[1].length;
      const language = fence[2] || "";
      const raw = [];
      const startLine = index + 1;
      const sourceLine = lineOffset + startLine;
      index += 1;
      while (index < lines.length && !new RegExp(`^\\s*${marker}{${minimumLength},}\\s*$`).test(lines[index])) {
        raw.push(lines[index]);
        index += 1;
      }
      if (index >= lines.length) throw new Error(`Code fence near line ${sourceLine} is not closed.`);
      blocks.push({ type: "code", language, raw: raw.join("\n") });
      index += 1;
      continue;
    }

    const directive = line.match(/^:::(\w[\w-]*)(?:\s+(.*))?$/);
    if (directive) {
      const name = directive[1];
      if (name === "pagebreak") {
        blocks.push({ type: "pagebreak" });
        index += 1;
        continue;
      }
      if (name === "methodology-3x4") {
        if (directive[2]?.trim()) {
          throw new Error(`:::methodology-3x4 does not accept parameters near line ${lineOffset + index + 1}.`);
        }
        blocks.push({ ...fixedMethodology3x4Block(inline), line: index + 1 });
        index += 1;
        continue;
      }
      const startLine = index + 1;
      const sourceLine = lineOffset + startLine;
      index += 1;
      const content = [];
      while (index < lines.length && lines[index].trim() !== ":::") {
        content.push(lines[index]);
        index += 1;
      }
      if (index >= lines.length) throw new Error(`Directive :::${name} near line ${sourceLine} is not closed.`);
      blocks.push({ ...parseDirective(name, content.join("\n"), sourceLine, inline), line: startLine });
      index += 1;
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      blocks.push({ type: "heading", level: heading[1].length, html: inline(heading[2]), raw: heading[2], line: index + 1 });
      index += 1;
      continue;
    }

    if (index + 1 < lines.length && line.includes("|") && isTableDelimiter(lines[index + 1])) {
      const startLine = index + 1;
      const parsed = parseTable(lines, index, inline);
      blocks.push({ ...parsed.block, line: startLine });
      index = parsed.nextIndex;
      continue;
    }

    if (isHorizontalRule(line)) {
      blocks.push({ type: "hr", line: index + 1 });
      index += 1;
      continue;
    }

    const image = parseImageLine(line);
    if (image) {
      blocks.push({ type: "image", ...image, captionHtml: inline(image.title || image.alt), line: index + 1 });
      index += 1;
      continue;
    }

    if (isRawHtmlStart(line)) {
      const raw = [];
      while (index < lines.length && lines[index].trim()) {
        raw.push(lines[index]);
        index += 1;
      }
      blocks.push({ type: "html", html: sanitizeRawHtml(raw.join("\n")), raw: raw.join("\n"), line: index - raw.length + 1 });
      continue;
    }

    if (/^>\s?/.test(line)) {
      const quote = [];
      while (index < lines.length && /^>\s?/.test(lines[index])) {
        quote.push(lines[index].replace(/^>\s?/, ""));
        index += 1;
      }
      const raw = quote.join("\n");
      blocks.push({ type: "quote", html: inline(raw), raw, line: index - quote.length + 1 });
      continue;
    }

    if (matchListLine(line)) {
      const startLine = index + 1;
      const parsed = parseList(lines, index, inline);
      blocks.push({ ...parsed.block, line: startLine });
      index = parsed.nextIndex;
      continue;
    }

    const paragraph = [];
    while (index < lines.length && lines[index].trim()) {
      if (paragraph.length > 0 && isBlockStart(lines, index)) break;
      paragraph.push(lines[index].trim());
      index += 1;
    }
    const raw = paragraph.join("\n");
    blocks.push({ type: "paragraph", html: inline(raw), raw, line: index - paragraph.length + 1 });
  }
  if (footnotes.length) {
    blocks.push({
      type: "footnotes",
      line: footnotes[0].line,
      items: footnotes.map((definition, index) => ({
        id: definition.id,
        number: index + 1,
        html: inline(definition.raw),
        raw: definition.raw,
        line: definition.line
      }))
    });
  }
  return blocks;
}

export function parseBlocks(body, lineOffset = 0) {
  const extracted = extractFootnotes(body);
  return parseBlockLines(extracted.body, extracted.definitions, lineOffset);
}
