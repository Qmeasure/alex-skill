#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import sharp from "sharp";
import { diagnosticError, diagnosticsFromError, formatDiagnostic } from "./diagnostics.mjs";

const SCRIPT_PATH = fileURLToPath(import.meta.url);
const SKILL_DIR = path.resolve(path.dirname(SCRIPT_PATH), "..");

function parseArguments(argv) {
  const options = { input: "", workspace: "", json: false, debug: false, help: false };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--workspace") {
      options.workspace = argv[index + 1] || "";
      index += 1;
    } else if (value === "--json") options.json = true;
    else if (value === "--debug") options.debug = true;
    else if (value === "--help" || value === "-h") options.help = true;
    else if (value.startsWith("-")) throw new Error(`Unknown option: ${value}`);
    else if (!options.input) options.input = value;
    else throw new Error(`Unexpected positional argument: ${value}`);
  }
  return options;
}

async function readJson(filePath, code) {
  try {
    return JSON.parse(await fs.readFile(filePath, "utf8"));
  } catch (error) {
    throw diagnosticError(code, `Cannot read ${path.basename(filePath)}.`, {
      location: filePath,
      actual: error.message
    });
  }
}

export function sanitizeAuditMarkdown(source) {
  const lines = String(source).replace(/\r\n?/g, "\n").split("\n");
  if (lines[0] === "---") {
    const closing = lines.indexOf("---", 1);
    if (closing !== -1) {
      const frontMatter = lines.slice(1, closing).filter((line) => !/^\s*source_pages\s*:/i.test(line));
      lines.splice(1, closing - 1, ...frontMatter);
    }
  }
  const withoutSourcePages = lines.join("\n");
  const thumbnails = /(?:^|\n):::thumbnails[ \t]*\n[\s\S]*?\n:::[ \t]*(?:\n*)$/;
  if (!thumbnails.test(withoutSourcePages)) {
    throw diagnosticError("E_AUDIT_MARKDOWN", "The Markdown does not end with a thumbnails block.");
  }
  const cleaned = withoutSourcePages.replace(thumbnails, "").trimEnd() + "\n";
  if (/^\s*source_pages\s*:/im.test(cleaned) || /^:::thumbnails[ \t]*$/m.test(cleaned)) {
    throw diagnosticError("E_AUDIT_MARKDOWN", "Audit-only Markdown fields were not removed.");
  }
  return cleaned;
}

function buildPagesMarkdown(visiblePages) {
  const sections = visiblePages.map((page) => {
    const text = typeof page.text === "string" ? page.text.trim() : "";
    if (!text) {
      throw diagnosticError("E_AUDIT_PAGE_TEXT", "A rendered page has no extractable visible text.", {
        page: page.page,
        actual: page.file,
        expected: "Re-render with the current renderer before preparing audit packages"
      });
    }
    const kind = page.kind === "cover" ? "封面" : "正文";
    return `## 第 ${page.page} 页｜${kind}\n\n${text}`;
  });
  return `# 渲染后逐页文字\n\n${sections.join("\n\n")}\n`;
}

function identifyFixedComponents(checklist, visiblePages) {
  const methodologyPages = visiblePages
    .filter((page) => Array.isArray(page.features) && page.features.includes("methodology-3x4"))
    .map((page) => page.page);
  if (!methodologyPages.length) return checklist;
  return `${checklist.trimEnd()}\n\n## 审计包固定组件标识\n\n` +
    `第 ${methodologyPages.join("、")} 页包含渲染器生成的 \`methodology-3x4\` 固定组件；` +
    `按本清单对固定组件和具体映射的职责边界处理。\n`;
}

function buildVisualCrops(visiblePages, width, height) {
  const crops = [];
  for (const page of visiblePages) {
    const expectedKind = page.kind === "cover" ? "cover-content" : "content-image";
    const regions = Array.isArray(page.visualRegions)
      ? page.visualRegions.filter((region) => region.kind === expectedKind)
      : [];
    const needsRegions = page.kind === "cover" || (
      page.kind === "body" && Array.isArray(page.features) && page.features.includes("image")
    );
    if (needsRegions && !regions.length) {
      throw diagnosticError("E_AUDIT_VISUAL_REGION", "A visual audit target has no extractable content region.", {
        page: page.page,
        actual: page.file,
        expected: "Re-render with the current renderer before preparing audit packages"
      });
    }
    regions.forEach((region, index) => {
      const values = [region.x, region.y, region.width, region.height];
      const valid = values.every((value) => Number.isInteger(value) && value >= 0)
        && region.width > 0 && region.height > 0
        && region.x + region.width <= width && region.y + region.height <= height;
      if (!valid) {
        throw diagnosticError("E_AUDIT_VISUAL_REGION", "A visual audit region is outside the rendered page.", {
          page: page.page,
          actual: JSON.stringify(region),
          expected: `${width}x${height} page bounds`
        });
      }
      const pagePrefix = String(page.page).padStart(2, "0");
      const output = page.kind === "cover"
        ? `${pagePrefix}-cover-content.png`
        : `${pagePrefix}-image-${String(index + 1).padStart(2, "0")}.png`;
      crops.push({
        source: page.file,
        output,
        extract: { left: region.x, top: region.y, width: region.width, height: region.height },
        padding: page.kind === "cover" ? 24 : 0
      });
    });
  }
  return crops;
}

export async function prepareAuditPackages({ inputPath, workspace, debug = false }) {
  const resolvedWorkspace = path.resolve(workspace);
  const resolvedInput = path.resolve(inputPath);
  const contentDirectory = path.join(resolvedWorkspace, "视频图");
  const renderDirectory = debug ? `${contentDirectory}.debug` : contentDirectory;
  const renderManifestPath = path.join(renderDirectory, "manifest.json");
  const sourceManifestPath = path.join(contentDirectory, "source-manifest.json");
  const inkstoneDirectory = path.join(contentDirectory, "inkstone-results");
  const webResearchPath = path.join(contentDirectory, "web-research.md");
  const outputRoot = path.join(resolvedWorkspace, "审计包");

  let source;
  try {
    source = await fs.readFile(resolvedInput, "utf8");
  } catch (error) {
    throw diagnosticError("E_AUDIT_INPUT", "Cannot read the carousel Markdown.", {
      location: resolvedInput,
      actual: error.message
    });
  }
  const article = sanitizeAuditMarkdown(source);
  const renderManifest = await readJson(renderManifestPath, "E_AUDIT_RENDER_MANIFEST");
  const expectedMode = debug ? "debug" : "formal";
  const expectedDeliveryReady = !debug;
  if (renderManifest.mode !== expectedMode || renderManifest.deliveryReady !== expectedDeliveryReady) {
    throw diagnosticError("E_AUDIT_RENDER_MANIFEST", debug
      ? "Debug audit packages require a non-delivery debug render."
      : "Audit packages require a delivery-ready formal render.", {
      location: renderManifestPath,
      actual: `mode=${renderManifest.mode}, deliveryReady=${renderManifest.deliveryReady}`,
      expected: `mode=${expectedMode}, deliveryReady=${expectedDeliveryReady}`
    });
  }
  const pageDetails = Array.isArray(renderManifest.pageDetails) ? renderManifest.pageDetails : [];
  const covers = pageDetails.filter((page) => page.kind === "cover");
  const bodies = pageDetails.filter((page) => page.kind === "body");
  const endcards = pageDetails.filter((page) => page.kind === "endcard");
  if (covers.length !== 1 || !bodies.length || endcards.length !== 1 || pageDetails.length !== covers.length + bodies.length + endcards.length) {
    throw diagnosticError("E_AUDIT_RENDER_MANIFEST", "The render manifest must identify one cover, body pages, and one endcard.", {
      location: renderManifestPath,
      actual: `${covers.length} cover, ${bodies.length} body, ${endcards.length} endcard`
    });
  }
  const visiblePages = pageDetails.filter((page) => page.kind !== "endcard");
  for (const page of visiblePages) {
    if (typeof page.file !== "string" || path.basename(page.file) !== page.file) {
      throw diagnosticError("E_AUDIT_PAGE", "The render manifest contains an invalid page file.", { actual: page.file });
    }
    try {
      await fs.access(path.join(renderDirectory, page.file));
    } catch {
      throw diagnosticError("E_AUDIT_PAGE", "A rendered audit page is missing.", {
        location: path.join(renderDirectory, page.file)
      });
    }
  }
  const pagesMarkdown = buildPagesMarkdown(visiblePages);
  const visualCrops = buildVisualCrops(visiblePages, renderManifest.width, renderManifest.height);

  const sourceManifest = await readJson(sourceManifestPath, "E_AUDIT_SOURCE_MANIFEST");
  const inkstoneInputs = Array.isArray(sourceManifest.inkstoneInputs) ? sourceManifest.inkstoneInputs : [];
  if (sourceManifest.status !== "ready" || !inkstoneInputs.length) {
    throw diagnosticError("E_AUDIT_SOURCE_MANIFEST", "The source manifest has no ready Inkstone inputs.", {
      location: sourceManifestPath
    });
  }
  let resultFiles;
  try {
    resultFiles = (await fs.readdir(inkstoneDirectory, { withFileTypes: true }))
      .filter((entry) => entry.isFile() && /^\d+\.md$/.test(entry.name))
      .map((entry) => entry.name)
      .sort((left, right) => left.localeCompare(right, "en", { numeric: true }));
  } catch (error) {
    throw diagnosticError("E_AUDIT_SOURCES", "Cannot read Inkstone results.", {
      location: inkstoneDirectory,
      actual: error.message
    });
  }
  const expectedResults = inkstoneInputs.map((_, index) => `${String(index + 1).padStart(2, "0")}.md`);
  if (JSON.stringify(resultFiles) !== JSON.stringify(expectedResults)) {
    throw diagnosticError("E_AUDIT_SOURCES", "Inkstone results do not match source-manifest.json.", {
      location: inkstoneDirectory,
      actual: resultFiles.join(", ") || "none",
      expected: expectedResults.join(", ")
    });
  }
  const sourceIndex = expectedResults.map((result, index) => ({
    input: path.basename(String(inkstoneInputs[index])),
    result
  }));

  const [contextChecklist, evidenceChecklist] = await Promise.all([
    fs.readFile(path.join(SKILL_DIR, "references/context-audit-checklist.md"), "utf8"),
    fs.readFile(path.join(SKILL_DIR, "references/audit-checklist.md"), "utf8")
  ]);
  const identifiedContextChecklist = identifyFixedComponents(contextChecklist, visiblePages);
  const identifiedEvidenceChecklist = identifyFixedComponents(evidenceChecklist, visiblePages);
  await fs.mkdir(resolvedWorkspace, { recursive: true });
  const stagingRoot = await fs.mkdtemp(path.join(resolvedWorkspace, ".audit-packages-staging-"));
  let committed = false;
  let webResearch = false;
  try {
    const contextDirectory = path.join(stagingRoot, "context");
    const evidenceDirectory = path.join(stagingRoot, "evidence");
    const sourcesDirectory = path.join(evidenceDirectory, "sources");
    const visualDirectory = path.join(evidenceDirectory, "visual");
    await Promise.all([
      fs.mkdir(contextDirectory, { recursive: true }),
      fs.mkdir(sourcesDirectory, { recursive: true }),
      fs.mkdir(visualDirectory, { recursive: true })
    ]);
    await Promise.all([
      fs.writeFile(path.join(contextDirectory, "AUDIT.md"), identifiedContextChecklist, "utf8"),
      fs.writeFile(path.join(contextDirectory, "pages.md"), pagesMarkdown, "utf8"),
      fs.writeFile(path.join(evidenceDirectory, "AUDIT.md"), identifiedEvidenceChecklist, "utf8"),
      fs.writeFile(path.join(evidenceDirectory, "article.md"), article, "utf8"),
      fs.writeFile(path.join(evidenceDirectory, "pages.md"), pagesMarkdown, "utf8"),
      fs.writeFile(path.join(sourcesDirectory, "index.json"), `${JSON.stringify(sourceIndex, null, 2)}\n`, "utf8"),
      ...expectedResults.map((file) => fs.copyFile(path.join(inkstoneDirectory, file), path.join(sourcesDirectory, file))),
      ...visualCrops.map((crop) => {
        let pipeline = sharp(path.join(renderDirectory, crop.source)).extract(crop.extract);
        if (crop.padding) {
          pipeline = pipeline.extend({
            top: crop.padding,
            bottom: crop.padding,
            left: crop.padding,
            right: crop.padding,
            background: "#f5f7fa"
          });
        }
        return pipeline.png().toFile(path.join(visualDirectory, crop.output));
      })
    ]);
    try {
      await fs.copyFile(webResearchPath, path.join(evidenceDirectory, "web-research.md"));
      webResearch = true;
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
    }

    await fs.rm(outputRoot, { recursive: true, force: true });
    await fs.rename(stagingRoot, outputRoot);
    committed = true;
  } finally {
    if (!committed) await fs.rm(stagingRoot, { recursive: true, force: true });
  }

  return {
    contextDirectory: path.join(outputRoot, "context"),
    evidenceDirectory: path.join(outputRoot, "evidence"),
    pages: visiblePages.length,
    sources: inkstoneInputs.length,
    visualFiles: visualCrops.map((crop) => crop.output),
    webResearch
  };
}

async function main() {
  const options = parseArguments(process.argv.slice(2));
  if (options.help) {
    process.stdout.write("Usage: node prepare-audit.mjs <input.md> --workspace <workspace> [--debug] [--json]\n");
    return;
  }
  if (!options.input || !options.workspace) throw new Error("Input Markdown and --workspace are required.");
  const result = await prepareAuditPackages({ inputPath: options.input, workspace: options.workspace, debug: options.debug });
  if (options.json) process.stdout.write(`${JSON.stringify({ ok: true, ...result }, null, 2)}\n`);
  else {
    process.stdout.write(`Context audit package: ${result.contextDirectory}\n`);
    process.stdout.write(`Evidence audit package: ${result.evidenceDirectory}\n`);
  }
}

const entryPointPath = process.argv[1] ? await fs.realpath(path.resolve(process.argv[1])).catch(() => path.resolve(process.argv[1])) : "";
if (SCRIPT_PATH === entryPointPath) {
  main().catch((error) => {
    const diagnostics = diagnosticsFromError(error, "E_AUDIT_PACKAGE_FAILED");
    if (process.argv.includes("--json")) process.stdout.write(`${JSON.stringify({ ok: false, errors: diagnostics }, null, 2)}\n`);
    else diagnostics.forEach((item) => process.stderr.write(`${formatDiagnostic(item)}\n`));
    process.exitCode = 1;
  });
}
