#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { parseDocument, validateDocument } from "./parser.mjs";
import { formatDiagnostic, parseFailure } from "./diagnostics.mjs";

function parseArguments(argv) {
  const options = { input: "", json: false, help: false };
  for (const value of argv) {
    if (value === "--json") options.json = true;
    else if (value === "--help" || value === "-h") options.help = true;
    else if (value.startsWith("-")) throw new Error(`Unknown option: ${value}`);
    else if (!options.input) options.input = value;
    else throw new Error(`Unexpected positional argument: ${value}`);
  }
  return options;
}

export async function validateFile(input) {
  try {
    const source = await fs.readFile(path.resolve(input), "utf8");
    const document = parseDocument(source);
    const result = validateDocument(document);
    const renderable = document.blocks.filter((block) => block.type !== "pagebreak").length;
    return {
      valid: result.errors.length === 0,
      errors: result.errors,
      warnings: result.warnings,
      stats: { renderableBlocks: renderable, cover: document.meta.cover }
    };
  } catch (error) {
    return { valid: false, errors: [parseFailure(error)], warnings: [], stats: {} };
  }
}

async function main() {
  const options = parseArguments(process.argv.slice(2));
  if (options.help || !options.input) {
    process.stdout.write("Usage: node validate.mjs <input.md> [--json]\n");
    process.exitCode = options.help ? 0 : 1;
    return;
  }
  const result = await validateFile(options.input);
  if (options.json) {
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  } else {
    result.warnings.forEach((warning) => process.stderr.write(`${formatDiagnostic(warning, "Warning")}\n`));
    result.errors.forEach((error) => process.stderr.write(`${formatDiagnostic(error)}\n`));
    if (result.valid) {
      process.stdout.write(`Valid: ${result.stats.renderableBlocks} content block(s), cover ${result.stats.cover ? "enabled" : "disabled"}.\n`);
    }
  }
  if (!result.valid) process.exitCode = 1;
}

const entryPointPath = process.argv[1] ? await fs.realpath(path.resolve(process.argv[1])).catch(() => path.resolve(process.argv[1])) : "";
if (fileURLToPath(import.meta.url) === entryPointPath) {
  main().catch((error) => {
    process.stderr.write(`${formatDiagnostic(parseFailure(error))}\n`);
    process.exitCode = 1;
  });
}
