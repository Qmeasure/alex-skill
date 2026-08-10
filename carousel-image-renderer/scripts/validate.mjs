#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { parseDocument, validateDocument } from "./render.mjs";

async function main() {
  const input = process.argv[2];
  if (!input || input === "--help" || input === "-h") {
    process.stdout.write("Usage: node validate.mjs <input.md>\n");
    process.exitCode = input ? 0 : 1;
    return;
  }

  const source = await fs.readFile(path.resolve(input), "utf8");
  const document = parseDocument(source);
  const result = validateDocument(document);
  result.warnings.forEach((warning) => process.stderr.write(`Warning: ${warning}\n`));
  if (result.errors.length) {
    result.errors.forEach((error) => process.stderr.write(`Error: ${error}\n`));
    process.exitCode = 1;
    return;
  }
  const hasThumbnails = document.blocks.some((block) => block.type === "thumbnails") || /^:::thumbnails\s*$/m.test(source);
  if (!hasThumbnails) {
    process.stderr.write("Error: missing :::thumbnails block. Every carousel must end with source thumbnails.\n");
    process.exitCode = 1;
    return;
  }
  const renderable = document.blocks.filter((block) => block.type !== "pagebreak").length;
  process.stdout.write(`Valid: ${renderable} content block(s), cover ${document.meta.cover ? "enabled" : "disabled"}.\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.message}\n`);
  process.exitCode = 1;
});
