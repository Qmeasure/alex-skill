#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { diagnosticError, diagnosticsFromError, formatDiagnostic } from "./diagnostics.mjs";

const SCRIPT_PATH = fileURLToPath(import.meta.url);
const SKILL_DIR = path.resolve(path.dirname(SCRIPT_PATH), "..");

function parseArguments(argv) {
  const options = { input: "", workspace: "", json: false, help: false };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--workspace") {
      options.workspace = argv[index + 1] || "";
      index += 1;
    } else if (value === "--json") options.json = true;
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

function auditPageDetail(detail) {
  return {
    page: detail.page,
    kind: detail.kind,
    label: detail.label || "",
    features: Array.isArray(detail.features) ? detail.features : [],
    file: detail.file,
    ...(detail.fill != null ? { fill: detail.fill } : {}),
    ...(detail.lastBody != null ? { lastBody: detail.lastBody } : {})
  };
}

function auditTargets(targets = {}, visibleFiles) {
  const keepOne = (value) => typeof value === "string" && visibleFiles.has(value) ? value : "";
  const keepMany = (value) => Array.isArray(value) ? value.filter((file) => visibleFiles.has(file)) : [];
  return {
    cover: keepOne(targets.cover),
    densestBody: keepOne(targets.densestBody),
    riskPages: keepMany(targets.riskPages),
    calloutPages: keepMany(targets.calloutPages),
    fillWarningPages: keepMany(targets.fillWarningPages)
  };
}

function buildAuditManifest(renderManifest, visiblePages) {
  const pageDetails = visiblePages.map(auditPageDetail);
  const files = pageDetails.map((detail) => detail.file);
  const visibleFiles = new Set(files);
  return {
    title: renderManifest.title || "",
    mode: "formal",
    deliveryReady: true,
    pages: files.length,
    bodyPages: pageDetails.filter((detail) => detail.kind === "body").length,
    files,
    pageDetails,
    auditTargets: auditTargets(renderManifest.auditTargets, visibleFiles)
  };
}

async function writeCommonPackage(directory, checklist, article, manifest, pages, renderDirectory) {
  const pagesDirectory = path.join(directory, "pages");
  await fs.mkdir(pagesDirectory, { recursive: true });
  await Promise.all([
    fs.writeFile(path.join(directory, "AUDIT.md"), checklist, "utf8"),
    fs.writeFile(path.join(directory, "article.md"), article, "utf8"),
    fs.writeFile(path.join(directory, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8"),
    ...pages.map((page) => fs.copyFile(path.join(renderDirectory, page.file), path.join(pagesDirectory, page.file)))
  ]);
}

export async function prepareAuditPackages({ inputPath, workspace }) {
  const resolvedWorkspace = path.resolve(workspace);
  const resolvedInput = path.resolve(inputPath);
  const renderDirectory = path.join(resolvedWorkspace, "视频图");
  const renderManifestPath = path.join(renderDirectory, "manifest.json");
  const sourceManifestPath = path.join(renderDirectory, "source-manifest.json");
  const inkstoneDirectory = path.join(renderDirectory, "inkstone-results");
  const webResearchPath = path.join(renderDirectory, "web-research.md");
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
  if (renderManifest.mode !== "formal" || renderManifest.deliveryReady !== true) {
    throw diagnosticError("E_AUDIT_RENDER_MANIFEST", "Audit packages require a delivery-ready formal render.", {
      location: renderManifestPath,
      actual: `mode=${renderManifest.mode}, deliveryReady=${renderManifest.deliveryReady}`
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

  const [contextChecklist, evidenceChecklist] = await Promise.all([
    fs.readFile(path.join(SKILL_DIR, "references/context-audit-checklist.md"), "utf8"),
    fs.readFile(path.join(SKILL_DIR, "references/audit-checklist.md"), "utf8")
  ]);
  const auditManifest = buildAuditManifest(renderManifest, visiblePages);
  await fs.mkdir(resolvedWorkspace, { recursive: true });
  const stagingRoot = await fs.mkdtemp(path.join(resolvedWorkspace, ".audit-packages-staging-"));
  let committed = false;
  let webResearch = false;
  try {
    const contextDirectory = path.join(stagingRoot, "context");
    const evidenceDirectory = path.join(stagingRoot, "evidence");
    await Promise.all([
      writeCommonPackage(contextDirectory, contextChecklist, article, auditManifest, visiblePages, renderDirectory),
      writeCommonPackage(evidenceDirectory, evidenceChecklist, article, auditManifest, visiblePages, renderDirectory)
    ]);

    const sourcesDirectory = path.join(evidenceDirectory, "sources");
    await fs.mkdir(sourcesDirectory, { recursive: true });
    const sourceIndex = expectedResults.map((result, index) => ({
      input: path.basename(String(inkstoneInputs[index])),
      result
    }));
    await Promise.all([
      fs.writeFile(path.join(sourcesDirectory, "index.json"), `${JSON.stringify(sourceIndex, null, 2)}\n`, "utf8"),
      ...expectedResults.map((file) => fs.copyFile(path.join(inkstoneDirectory, file), path.join(sourcesDirectory, file)))
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
    webResearch
  };
}

async function main() {
  const options = parseArguments(process.argv.slice(2));
  if (options.help) {
    process.stdout.write("Usage: node prepare-audit.mjs <input.md> --workspace <workspace> [--json]\n");
    return;
  }
  if (!options.input || !options.workspace) throw new Error("Input Markdown and --workspace are required.");
  const result = await prepareAuditPackages({ inputPath: options.input, workspace: options.workspace });
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
