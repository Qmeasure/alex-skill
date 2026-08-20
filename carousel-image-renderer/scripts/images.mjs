// 本地图片嵌入：渲染前把 Markdown 引用的本地图片读成 base64 data URI，
// 使注入浏览器的 HTML 自包含，不依赖文件路径。

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { normalizeDestination } from "./parser/text.mjs";

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

export async function embedLocalMarkdownImages(source, inputPath) {
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
