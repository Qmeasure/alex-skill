#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = path.resolve(SCRIPT_DIR, "..");
const PAGE_WIDTH = 1080;
const PAGE_HEIGHT = 1440;
const SUPPORTED_THEMES = new Set(["classic", "finance", "editorial", "tech"]);

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[character]);
}

function escapeAttribute(value) {
  return escapeHtml(value).replace(/`/g, "&#96;");
}

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

function normalizeDestination(value) {
  const trimmed = String(value).trim();
  return trimmed.startsWith("<") && trimmed.endsWith(">") ? trimmed.slice(1, -1) : trimmed;
}

function safeUrl(value, kind = "link") {
  const url = normalizeDestination(value);
  if (/^(?:javascript|vbscript):/i.test(url)) return "";
  if (/^data:/i.test(url) && !(kind === "image" && /^data:image\//i.test(url))) return "";
  return url;
}

function parseInline(value, options = {}) {
  const tokens = [];
  const stash = (html) => `\uE000${tokens.push(html) - 1}\uE001`;
  let source = String(value);

  source = source.replace(/`([^`\n]+)`/g, (_, code) => stash(`<code class="inline-code">${escapeHtml(code)}</code>`));

  source = source.replace(/!\[([^\]]*)\]\((<[^>]+>|[^\s)]+)(?:\s+["']([^"']*)["'])?\)/g, (match, alt, destination, title) => {
    const url = safeUrl(destination, "image");
    if (!url) return match;
    const titleAttribute = title ? ` title="${escapeAttribute(title)}"` : "";
    return stash(`<img class="inline-markdown-image" src="${escapeAttribute(url)}" alt="${escapeAttribute(alt)}"${titleAttribute}>`);
  });

  source = source.replace(/\[([^\]]+)\]\((<[^>]+>|[^\s)]+)(?:\s+["']([^"']*)["'])?\)/g, (match, label, destination, title) => {
    const url = safeUrl(destination, "link");
    if (!url) return match;
    const titleAttribute = title ? ` title="${escapeAttribute(title)}"` : "";
    return stash(`<a class="markdown-link" href="${escapeAttribute(url)}"${titleAttribute}>${parseInline(label, options)}</a>`);
  });

  source = source.replace(/\[\^([^\]]+)\]/g, (match, id) => {
    const number = options.footnoteNumbers?.get(id);
    return number ? stash(`<sup class="footnote-ref">${number}</sup>`) : match;
  });

  source = source.replace(/<\/?(?:br|strong|b|em|i|u|mark|small|sub|sup|kbd|code|span)(?:\s+[^>]*)?\s*\/?>/gi, (tag) => {
    const match = tag.match(/^<(\/)?([a-z0-9]+)[^>]*>$/i);
    if (!match) return tag;
    const closing = Boolean(match[1]);
    const name = match[2].toLowerCase();
    if (name === "br") return stash("<br>");
    return stash(`<${closing ? "/" : ""}${name}>`);
  });

  let html = escapeHtml(source);
  html = html.replace(/\*\*([\s\S]+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/__([^_]+?)__/g, "<strong>$1</strong>");
  html = html.replace(/~~([\s\S]+?)~~/g, "<del>$1</del>");
  html = html.replace(/(^|[^*])\*([^*\n]+?)\*(?!\*)/g, "$1<em>$2</em>");
  html = html.replace(/(^|[^\w])_([^_\n]+?)_(?!\w)/g, "$1<em>$2</em>");
  html = html.replace(/==(.+?)==/g, '<span class="inline-highlight">$1</span>');
  html = html.replace(/\{accent\}([\s\S]+?)\{\/accent\}/g, '<span class="accent">$1</span>');
  html = html.replace(/\{circle\}([\s\S]+?)\{\/circle\}/g, '<span class="hand-circle">$1</span>');
  html = html.replace(/\{wavy\}([\s\S]+?)\{\/wavy\}/g, '<span class="hand-wavy">$1</span>');
  html = html.replace(/\n/g, "<br>");
  return html.replace(/\uE000(\d+)\uE001/g, (_, index) => tokens[Number(index)]);
}

function plainText(value) {
  return String(value)
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/\[\^[^\]]+\]/g, "")
    .replace(/\{\/?(?:accent|circle|wavy)\}/g, "")
    .replace(/==|\*\*|__|~~|`|(?<!\*)\*(?!\*)|_/g, "")
    .replace(/<[^>]*>/g, "")
    .trim();
}

function parseFrontMatter(source) {
  const normalized = source.replace(/\r\n?/g, "\n");
  if (!normalized.startsWith("---\n")) return { meta: {}, body: normalized };

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
  return { meta, body: normalized.slice(closing + 5) };
}

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
    while (index + 1 < lines.length && /^(?: {2,}|\t)\S/.test(lines[index + 1])) {
      content.push(lines[index + 1].trim());
      index += 1;
    }
    definitions.push({ id: match[1], raw: content.join(" ").trim() });
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

function parseBlocks(body, meta, footnotes) {
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
      index += 1;
      while (index < lines.length && !new RegExp(`^\\s*${marker}{${minimumLength},}\\s*$`).test(lines[index])) {
        raw.push(lines[index]);
        index += 1;
      }
      if (index >= lines.length) throw new Error(`Code fence near line ${startLine} is not closed.`);
      blocks.push({ type: "code", language, raw: raw.join("\n") });
      index += 1;
      continue;
    }

    const directive = line.match(/^:::(\w[\w-]*)(?:\s+.*)?$/);
    if (directive) {
      const name = directive[1];
      if (name === "pagebreak") {
        blocks.push({ type: "pagebreak" });
        index += 1;
        continue;
      }
      const startLine = index + 1;
      index += 1;
      const content = [];
      while (index < lines.length && lines[index].trim() !== ":::") {
        content.push(lines[index]);
        index += 1;
      }
      if (index >= lines.length) throw new Error(`Directive :::${name} near line ${startLine} is not closed.`);
      blocks.push(parseDirective(name, content.join("\n"), startLine, inline));
      index += 1;
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      if (heading[1].length === 1 && !meta.title) {
        meta.title = plainText(heading[2]);
      } else {
        blocks.push({ type: "heading", level: heading[1].length, html: inline(heading[2]), raw: heading[2] });
      }
      index += 1;
      continue;
    }

    if (index + 1 < lines.length && line.includes("|") && isTableDelimiter(lines[index + 1])) {
      const parsed = parseTable(lines, index, inline);
      blocks.push(parsed.block);
      index = parsed.nextIndex;
      continue;
    }

    if (isHorizontalRule(line)) {
      blocks.push({ type: "hr" });
      index += 1;
      continue;
    }

    const image = parseImageLine(line);
    if (image) {
      blocks.push({ type: "image", ...image, captionHtml: inline(image.title || image.alt) });
      index += 1;
      continue;
    }

    if (isRawHtmlStart(line)) {
      const raw = [];
      while (index < lines.length && lines[index].trim()) {
        raw.push(lines[index]);
        index += 1;
      }
      blocks.push({ type: "html", html: sanitizeRawHtml(raw.join("\n")), raw: raw.join("\n") });
      continue;
    }

    if (/^>\s?/.test(line)) {
      const quote = [];
      while (index < lines.length && /^>\s?/.test(lines[index])) {
        quote.push(lines[index].replace(/^>\s?/, ""));
        index += 1;
      }
      const raw = quote.join("\n");
      blocks.push({ type: "quote", html: inline(raw), raw });
      continue;
    }

    if (matchListLine(line)) {
      const parsed = parseList(lines, index, inline);
      blocks.push(parsed.block);
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
    blocks.push({ type: "paragraph", html: inline(raw), raw });
  }
  if (footnotes.length) {
    blocks.push({
      type: "footnotes",
      items: footnotes.map((definition, index) => ({
        id: definition.id,
        number: index + 1,
        html: inline(definition.raw),
        raw: definition.raw
      }))
    });
  }
  return blocks;
}

function countWords(blocks) {
  const parts = [];
  function collect(block) {
    if (block.raw != null) parts.push(plainText(block.raw));
    if (block.type === "list") {
      block.items.forEach((item) => {
        parts.push(plainText(item.raw));
        if (item.children) item.children.forEach(collect);
      });
    }
    if (block.type === "metrics") {
      block.items.forEach((item) => { parts.push(item.label); parts.push(item.value); });
    }
    if (block.type === "table") {
      block.headers.forEach((h) => parts.push(h.raw));
      block.rows.forEach((row) => row.forEach((cell) => parts.push(cell.raw)));
    }
    if (block.type === "footnotes") {
      block.items.forEach((item) => parts.push(plainText(item.raw)));
    }
  }
  blocks.forEach(collect);
  const text = parts.join(" ");
  const chinese = (text.match(/[一-鿿㐀-䶿]/g) || []).length;
  const english = (text.replace(/[一-鿿㐀-䶿]/g, " ").match(/[a-zA-Z]+/g) || []).length;
  return chinese + english;
}

export function parseDocument(source) {
  const { meta: suppliedMeta, body } = parseFrontMatter(source);
  const meta = {
    title: "",
    subtitle: "",
    kicker: "图文报告",
    cover: true,
    theme: "classic",
    ...suppliedMeta
  };
  const extracted = extractFootnotes(body);
  const blocks = parseBlocks(extracted.body, meta, extracted.definitions);
  meta.title = String(meta.title || "").trim();
  meta.subtitle = String(meta.subtitle || "").trim();
  meta.kicker = String(meta.kicker || "图文报告").trim();
  meta.cover = meta.cover !== false;
  meta.theme = String(meta.theme || "classic").trim().toLowerCase();
  if (meta.callout_label != null) meta.callout_label = String(meta.callout_label).trim();
  meta.titleHtml = parseInline(meta.title);
  meta.subtitleHtml = parseInline(meta.subtitle);
  const wc = countWords(blocks);
  meta.wordCount = wc;
  meta.readingMinutes = Math.max(1, Math.ceil(wc / 400));
  return { meta, blocks };
}

export function validateDocument(document) {
  const errors = [];
  const warnings = [];
  if (!document.meta.title) errors.push("Missing title. Add front matter title or a level-one heading.");
  if (!SUPPORTED_THEMES.has(document.meta.theme)) {
    errors.push(`Unsupported theme "${document.meta.theme}". Use classic, finance, editorial, or tech.`);
  }
  const visibleBlocks = document.blocks.filter((block) => block.type !== "pagebreak");
  if (!visibleBlocks.length) errors.push("The article has no renderable content blocks.");
  document.blocks.forEach((block, index) => {
    if (block.type === "paragraph" && plainText(block.raw).length > 700) {
      warnings.push(`Paragraph block ${index + 1} is longer than 700 characters and may not fit on one page.`);
    }
    if (["circle", "wavy", "accent"].some((mark) => {
      const opens = (block.raw?.match(new RegExp(`\\{${mark}\\}`, "g")) || []).length;
      const closes = (block.raw?.match(new RegExp(`\\{\\/${mark}\\}`, "g")) || []).length;
      return opens !== closes;
    })) {
      errors.push(`Unbalanced inline mark in block ${index + 1}.`);
    }
    if (block.type === "table" && block.columnCount > 5) {
      warnings.push(`Table block ${index + 1} has ${block.columnCount} columns; 5 or fewer columns are recommended for a 1080px card.`);
    }
    if (block.type === "table" && block.rows.length > 10) {
      warnings.push(`Table block ${index + 1} has ${block.rows.length} body rows and may be too tall for one page.`);
    }
    if (block.type === "code" && block.raw.split("\n").length > 18) {
      warnings.push(`Code block ${index + 1} has more than 18 lines and may be too tall for one page.`);
    }
    if (block.type === "image" && !block.alt && !block.title) {
      warnings.push(`Image block ${index + 1} has no alt text or title, so it will render without a caption.`);
    }
  });
  return { errors, warnings };
}

const IMAGE_MIME_TYPES = new Map([
  [".png", "image/png"],
  [".jpg", "image/jpeg"],
  [".jpeg", "image/jpeg"],
  [".gif", "image/gif"],
  [".webp", "image/webp"],
  [".svg", "image/svg+xml"],
  [".avif", "image/avif"]
]);

async function resolveImageSource(destination, inputPath) {
  const source = normalizeDestination(destination);
  if (/^(?:https?:)?\/\//i.test(source) || /^data:image\//i.test(source)) return source;
  let imagePath;
  try {
    imagePath = source.startsWith("file:")
      ? fileURLToPath(source)
      : path.resolve(path.dirname(inputPath), decodeURIComponent(source));
  } catch (error) {
    throw new Error(`Invalid Markdown image path "${source}": ${error.message}`);
  }
  const extension = path.extname(imagePath).toLowerCase();
  const mimeType = IMAGE_MIME_TYPES.get(extension);
  if (!mimeType) throw new Error(`Unsupported Markdown image type "${extension || "unknown"}" for ${source}.`);
  try {
    const bytes = await fs.readFile(imagePath);
    return `data:${mimeType};base64,${bytes.toString("base64")}`;
  } catch (error) {
    throw new Error(`Markdown image could not be read: ${source} (${error.message})`);
  }
}

async function replaceAsync(source, expression, replacer) {
  const matches = [...source.matchAll(expression)];
  if (!matches.length) return source;
  const replacements = await Promise.all(matches.map((match) => replacer(...match)));
  let output = "";
  let cursor = 0;
  matches.forEach((match, index) => {
    output += source.slice(cursor, match.index) + replacements[index];
    cursor = match.index + match[0].length;
  });
  return output + source.slice(cursor);
}

async function embedLocalMarkdownImages(source, inputPath) {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  let fence = "";
  for (let index = 0; index < lines.length; index += 1) {
    const marker = lines[index].match(/^\s*(`{3,}|~{3,})/);
    if (marker) {
      if (!fence) fence = marker[1][0];
      else if (marker[1][0] === fence) fence = "";
      continue;
    }
    if (fence) continue;
    lines[index] = await replaceAsync(
      lines[index],
      /!\[([^\]]*)\]\((<[^>]+>|[^\s)]+)(\s+["'][^"']*["'])?\)/g,
      async (match, alt, destination, titleSuffix = "") => {
        const embedded = await resolveImageSource(destination, inputPath);
        return `![${alt}](${embedded}${titleSuffix})`;
      }
    );
  }
  return lines.join("\n");
}

function parseArguments(argv) {
  const options = { input: "", output: "", theme: "" };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--output" || value === "-o") {
      options.output = argv[index + 1] || "";
      index += 1;
    } else if (value === "--theme") {
      options.theme = argv[index + 1] || "";
      index += 1;
    } else if (value === "--help" || value === "-h") {
      options.help = true;
    } else if (value.startsWith("-")) {
      throw new Error(`Unknown option: ${value}`);
    } else if (!options.input) {
      options.input = value;
    } else {
      throw new Error(`Unexpected positional argument: ${value}`);
    }
  }
  return options;
}

async function loadPlaywright() {
  try {
    return await import("playwright");
  } catch (initialError) {
    const candidates = [
      process.env.PLAYWRIGHT_MODULE,
      process.env.CODEX_NODE_MODULES && path.join(process.env.CODEX_NODE_MODULES, "playwright/index.mjs"),
      path.join(process.cwd(), "node_modules/playwright/index.mjs"),
      path.resolve(SKILL_DIR, "../node_modules/playwright/index.mjs"),
      process.env.HOME && path.join(process.env.HOME, ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs")
    ].filter(Boolean);

    for (const candidate of candidates) {
      try {
        await fs.access(candidate);
        return await import(pathToFileURL(candidate).href);
      } catch {
        // Try the next deterministic local candidate.
      }
    }
    throw new Error(`Playwright is required but was not found. Install playwright in the current workspace. Original error: ${initialError.message}`);
  }
}

async function cleanOwnedOutputs(outputDirectory) {
  await fs.mkdir(outputDirectory, { recursive: true });
  const entries = await fs.readdir(outputDirectory, { withFileTypes: true });
  await Promise.all(entries.filter((entry) => entry.isFile() && (/^\d{2}-(?:cover|page)\.png$/.test(entry.name) || entry.name === "manifest.json"))
    .map((entry) => fs.unlink(path.join(outputDirectory, entry.name))));
}

async function browserLaunchOptions() {
  const candidates = [
    process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
    process.platform === "darwin" && "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    process.platform === "darwin" && "/Applications/Chromium.app/Contents/MacOS/Chromium",
    process.platform === "darwin" && "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    process.platform === "win32" && process.env.PROGRAMFILES && path.join(process.env.PROGRAMFILES, "Google/Chrome/Application/chrome.exe"),
    process.platform === "linux" && "/usr/bin/google-chrome",
    process.platform === "linux" && "/usr/bin/chromium"
  ].filter(Boolean);

  for (const candidate of candidates) {
    try {
      await fs.access(candidate);
      return { headless: true, executablePath: candidate };
    } catch {
      // Use Playwright's managed browser when no system browser is available.
    }
  }
  return { headless: true };
}

function buildHtml(document, css, runtime) {
  const payload = JSON.stringify(document).replace(/</g, "\\u003c").replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=${PAGE_WIDTH}, initial-scale=1">
  <style>${css}</style>
</head>
<body>
  <main class="carousel" id="carousel"></main>
  <script>window.__CAROUSEL_DATA__ = ${payload};</script>
  <script>${runtime}</script>
</body>
</html>`;
}

async function render(inputPath, outputDirectory, themeOverride = "") {
  const rawSource = await fs.readFile(inputPath, "utf8");
  const source = await embedLocalMarkdownImages(rawSource, inputPath);
  const document = parseDocument(source);
  if (themeOverride) document.meta.theme = String(themeOverride).trim().toLowerCase();
  const validation = validateDocument(document);
  if (validation.errors.length) throw new Error(validation.errors.join("\n"));
  validation.warnings.forEach((warning) => process.stderr.write(`Warning: ${warning}\n`));

  const [css, runtime, playwright, qrBytes] = await Promise.all([
    fs.readFile(path.join(SKILL_DIR, "assets/theme.css"), "utf8"),
    fs.readFile(path.join(SKILL_DIR, "assets/runtime.js"), "utf8"),
    loadPlaywright(),
    fs.readFile(path.join(SKILL_DIR, "assets/zhifujie-qr.png"))
  ]);
  document.meta.brandQr = `data:image/png;base64,${qrBytes.toString("base64")}`;

  await cleanOwnedOutputs(outputDirectory);
  const browser = await playwright.chromium.launch(await browserLaunchOptions());
  try {
    const page = await browser.newPage({
      viewport: { width: PAGE_WIDTH, height: PAGE_HEIGHT },
      deviceScaleFactor: 1
    });
    await page.setContent(buildHtml(document, css, runtime), { waitUntil: "load" });
    await page.waitForFunction(() => document.body.dataset.renderReady === "true");
    await page.waitForFunction(() => [...document.images].every((image) => image.complete), null, { timeout: 15000 });
    await page.evaluate(() => document.fonts?.ready);

    const brokenImages = await page.evaluate(() => [...document.images]
      .filter((image) => image.naturalWidth === 0)
      .map((image) => image.alt || image.getAttribute("src")?.slice(0, 80) || "unknown image"));
    if (brokenImages.length) throw new Error(`Markdown image failed to load: ${brokenImages.join(", ")}`);

    const report = await page.evaluate(() => window.__renderReport);
    if (report.overflowPages.length) {
      const debugCards = page.locator(".page-card");
      const cardCount = await debugCards.count();
      for (let index = 0; index < cardCount; index += 1) {
        const text = await debugCards.nth(index).innerText();
        const lines = text.split(/\n/).filter(Boolean);
        const head = lines.slice(0, 3).join(" | ").slice(0, 60);
        const tail = lines.slice(-3).join(" | ").slice(0, 80);
        const size = await debugCards.nth(index).evaluate((el) => {
          const flow = el.querySelector(".page-flow") || el;
          return { used: flow.scrollHeight, max: flow.clientHeight };
        });
        const marker = report.overflowPages.includes(index + 1) ? "OVERFLOW" : "ok";
        console.error(`  page ${index + 1} [${marker}] content ${size.used}px / limit ${size.max}px :: head: ${head} :: tail: ${tail}`);
      }
      throw new Error(`Content overflow on rendered page(s): ${report.overflowPages.join(", ")}. Shorten the oversized block or insert a page break.`);
    }

    const cards = page.locator(".page-card");
    const count = await cards.count();
    const files = [];
    for (let index = 0; index < count; index += 1) {
      const kind = await cards.nth(index).getAttribute("data-kind");
      const fileName = `${String(index + 1).padStart(2, "0")}-${kind === "cover" ? "cover" : "page"}.png`;
      await cards.nth(index).screenshot({ path: path.join(outputDirectory, fileName), type: "png" });
      files.push(fileName);
    }

    const manifest = {
      title: plainText(document.meta.title),
      theme: document.meta.theme,
      pages: count,
      width: PAGE_WIDTH,
      height: PAGE_HEIGHT,
      files,
      warnings: validation.warnings
    };
    await fs.writeFile(path.join(outputDirectory, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
    return manifest;
  } finally {
    await browser.close();
  }
}

async function main() {
  const options = parseArguments(process.argv.slice(2));
  if (options.help) {
    process.stdout.write("Usage: node render.mjs <input.md> --output <output-dir> [--theme classic|finance|editorial|tech]\n");
    return;
  }
  if (!options.input || !options.output) {
    throw new Error("Usage: node render.mjs <input.md> --output <output-dir>");
  }
  const inputPath = path.resolve(options.input);
  const outputDirectory = path.resolve(options.output);
  const manifest = await render(inputPath, outputDirectory, options.theme);
  process.stdout.write(`Rendered ${manifest.pages} page(s) to ${outputDirectory}\n`);
  manifest.files.forEach((file) => process.stdout.write(`${path.join(outputDirectory, file)}\n`));
}

const entryPointPath = process.argv[1] ? await fs.realpath(path.resolve(process.argv[1])).catch(() => path.resolve(process.argv[1])) : "";
if (fileURLToPath(import.meta.url) === entryPointPath) {
  main().catch((error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  });
}
