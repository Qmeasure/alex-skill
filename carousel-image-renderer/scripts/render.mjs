#!/usr/bin/env node

// 渲染入口：style/endcard 选择、CLI 协议与文档 → 浏览器 → 布局 → 输出的顶层编排。
// 领域实现位于 render/，共享 Playwright 定位与启动能力位于 browser.mjs。

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { diagnosticError, diagnosticsFromError, formatDiagnostic } from "./diagnostics.mjs";
import { loadBrowserResources, withBrowserSession } from "./render/browser-session.mjs";
import { loadRenderDocument } from "./render/document.mjs";
import { inspectLayout } from "./render/layout.mjs";
import { buildManifest, collectPageDetails } from "./render/manifest.mjs";
import { captureScreenshots, commitOwnedOutputs, createStagingDirectory, discardStagingDirectory, writeManifest } from "./render/output.mjs";

const PAGE_WIDTH = 1080;
const PAGE_HEIGHT = 1440;
const RENDER_SCALE = 2;
const RENDER_WIDTH = PAGE_WIDTH * RENDER_SCALE;
const RENDER_HEIGHT = PAGE_HEIGHT * RENDER_SCALE;
const SUPPORTED_ENDCARD_VARIANTS = new Set(["native", "guided"]);
const SUPPORTED_STYLE_VARIANTS = new Set(["new", "old"]);

function resolveEndcardVariant(value = "") {
  const endcard = String(value || "native").trim().toLowerCase();
  if (!SUPPORTED_ENDCARD_VARIANTS.has(endcard)) {
    throw diagnosticError("E_ENDCARD_UNSUPPORTED", `Unsupported endcard variant "${value}".`, {
      actual: value,
      expected: "native or guided",
      action: "Use --endcard native or --endcard guided."
    });
  }
  return endcard;
}

function resolveStyleVariant(value = "") {
  const style = String(value || "new").trim().toLowerCase();
  if (!SUPPORTED_STYLE_VARIANTS.has(style)) {
    throw diagnosticError("E_STYLE_UNSUPPORTED", `Unsupported render style "${value}".`, {
      actual: value,
      expected: "new or old",
      action: "Use --style new or --style old."
    });
  }
  return style;
}

function debugOutputDirectoryFor(outputDirectory) {
  return `${path.resolve(outputDirectory)}.debug`;
}

function parseArguments(argv) {
  const options = { input: "", output: "", endcard: "", style: "", json: false, debug: false };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--output" || value === "-o") {
      options.output = argv[index + 1] || "";
      index += 1;
    } else if (value === "--endcard") {
      options.endcard = argv[index + 1] || "";
      index += 1;
    } else if (value === "--style") {
      options.style = argv[index + 1] || "";
      index += 1;
    } else if (value === "--cover-only") {
      options.coverOnly = true;
    } else if (value === "--debug") {
      options.debug = true;
    } else if (value === "--json") {
      options.json = true;
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

async function render(inputPath, outputDirectory, endcardVariant = "", coverOnly = false, debug = false, styleVariant = "") {
  const endcard = resolveEndcardVariant(endcardVariant);
  const style = resolveStyleVariant(styleVariant);
  const renderedOutputDirectory = debug ? debugOutputDirectoryFor(outputDirectory) : outputDirectory;
  const debugOutputDirectory = debugOutputDirectoryFor(outputDirectory);
  const debugAction = debug
    ? `Inspect the diagnostic PNGs in "${renderedOutputDirectory}", including the failing page and adjacent pages.`
    : `Run the same render command with --debug; diagnostic PNGs will be written to "${debugOutputDirectory}" without replacing formal output.`;
  const { document, validation } = await loadRenderDocument(inputPath, { coverOnly });

  const resources = await loadBrowserResources(document, { style, endcard });

  const stagingDirectory = await createStagingDirectory(renderedOutputDirectory);
  try {
    const dimensions = {
      pageWidth: PAGE_WIDTH,
      pageHeight: PAGE_HEIGHT,
      renderScale: RENDER_SCALE,
      renderWidth: RENDER_WIDTH,
      renderHeight: RENDER_HEIGHT
    };
    const manifest = await withBrowserSession({ document, resources, dimensions }, async ({ page, fontReport, report }) => {
      const renderErrors = await inspectLayout({
        page,
        report,
        coverOnly,
        debug,
        debugAction,
        warnings: validation.warnings
      });
      const files = await captureScreenshots({ page, coverOnly, stagingDirectory, dimensions });
      const pageDetails = await collectPageDetails(page, report, coverOnly);
      const result = buildManifest({
        document,
        endcard,
        style,
        coverOnly,
        debug,
        files,
        pageDetails,
        fontReport,
        report,
        warnings: validation.warnings,
        renderErrors,
        dimensions
      });
      await writeManifest(stagingDirectory, result);
      return result;
    });
    await commitOwnedOutputs(stagingDirectory, renderedOutputDirectory);
    return manifest;
  } finally {
    await discardStagingDirectory(stagingDirectory);
  }
}

async function main() {
  const options = parseArguments(process.argv.slice(2));
  if (options.help) {
    process.stdout.write("Usage: node render.mjs <input.md> --output <output-dir> [--style new|old] [--endcard native|guided] [--cover-only] [--debug] [--json]\n");
    return;
  }
  if (!options.input || !options.output) {
    throw new Error("Usage: node render.mjs <input.md> --output <output-dir>");
  }
  const inputPath = path.resolve(options.input);
  const outputDirectory = path.resolve(options.output);
  const renderedOutputDirectory = options.debug ? debugOutputDirectoryFor(outputDirectory) : outputDirectory;
  const manifest = await render(inputPath, outputDirectory, options.endcard, options.coverOnly, options.debug, options.style);
  if (options.json) {
    process.stdout.write(`${JSON.stringify({ ok: true, outputDirectory: renderedOutputDirectory, manifest }, null, 2)}\n`);
  } else {
    const label = options.debug ? "debug page(s)" : "page(s)";
    process.stdout.write(`Rendered ${manifest.pages} ${label} to ${renderedOutputDirectory}\n`);
    manifest.files.forEach((file) => process.stdout.write(`${path.join(renderedOutputDirectory, file)}\n`));
  }
}

const entryPointPath = process.argv[1] ? await fs.realpath(path.resolve(process.argv[1])).catch(() => path.resolve(process.argv[1])) : "";
if (fileURLToPath(import.meta.url) === entryPointPath) {
  main().catch((error) => {
    const diagnostics = diagnosticsFromError(error);
    if (process.argv.includes("--json")) {
      process.stdout.write(`${JSON.stringify({ ok: false, errors: diagnostics }, null, 2)}\n`);
    } else {
      diagnostics.forEach((item) => process.stderr.write(`${formatDiagnostic(item)}\n`));
    }
    process.exitCode = 1;
  });
}
