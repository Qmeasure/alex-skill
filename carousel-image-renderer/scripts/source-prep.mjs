#!/usr/bin/env node

import crypto from "node:crypto";
import { spawn } from "node:child_process";
import fsSync from "node:fs";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";
import { loadPlaywright, browserLaunchOptions } from "./browser.mjs";
import { diagnostic, diagnosticError, diagnosticsFromError, formatDiagnostic } from "./diagnostics.mjs";

const SCRIPT_PATH = fileURLToPath(import.meta.url);
const SUPPORTED_EXTENSIONS = new Set([".html", ".htm", ".docx", ".pdf"]);
const CONTENT_PRIORITY = [".html", ".htm", ".docx", ".pdf"];
const THUMBNAIL_PRIORITY = [".pdf", ".docx", ".html", ".htm"];
const THUMBNAIL_WIDTH = 1240;
const THUMBNAIL_HEIGHT = 1754;

function parseArguments(argv) {
  const options = { workspace: process.cwd(), sourceDirectory: "", outputDirectory: "", debugLog: "", json: false, debug: false, help: false };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (["--workspace", "--source-dir", "--output", "--debug-log"].includes(value)) {
      const next = argv[index + 1];
      if (!next) throw new Error(`${value} requires a path.`);
      if (value === "--workspace") options.workspace = next;
      if (value === "--source-dir") options.sourceDirectory = next;
      if (value === "--output") options.outputDirectory = next;
      if (value === "--debug-log") options.debugLog = next;
      index += 1;
    } else if (value === "--json") options.json = true;
    else if (value === "--debug") options.debug = true;
    else if (value === "--help" || value === "-h") options.help = true;
    else throw new Error(`Unknown option: ${value}`);
  }
  return options;
}

async function listSupportedFiles(directory) {
  const entries = await fs.readdir(directory, { withFileTypes: true });
  return entries
    .filter((entry) => entry.isFile() && SUPPORTED_EXTENSIONS.has(path.extname(entry.name).toLowerCase()))
    .map((entry) => path.join(directory, entry.name))
    .sort((left, right) => left.localeCompare(right, "zh-CN"));
}

export async function discoverSources(workspace, sourceDirectory) {
  await fs.mkdir(sourceDirectory, { recursive: true });
  const organized = await listSupportedFiles(sourceDirectory);
  if (organized.length) return { mode: "source-directory", files: organized };
  const rootFiles = (await listSupportedFiles(workspace)).filter((file) => path.dirname(file) !== sourceDirectory);
  return { mode: rootFiles.length ? "workspace-root-fallback" : "empty", files: rootFiles };
}

function priorityPick(files, priority) {
  for (const extension of priority) {
    const match = files.find((file) => path.extname(file).toLowerCase() === extension);
    if (match) return match;
  }
  return "";
}

export function groupSources(files) {
  const groups = new Map();
  for (const file of files) {
    const stem = path.basename(file, path.extname(file));
    const key = stem.normalize("NFKC").toLocaleLowerCase("zh-CN");
    if (!groups.has(key)) groups.set(key, { name: stem, files: [] });
    groups.get(key).files.push(path.resolve(file));
  }
  return [...groups.values()]
    .map((group) => ({
      ...group,
      files: group.files.sort((left, right) => left.localeCompare(right, "zh-CN")),
      contentSource: priorityPick(group.files, CONTENT_PRIORITY),
      thumbnailCandidates: THUMBNAIL_PRIORITY.map((extension) => group.files.find((file) => path.extname(file).toLowerCase() === extension)).filter(Boolean)
    }))
    .sort((left, right) => left.name.localeCompare(right.name, "zh-CN"));
}

function commandResult(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { shell: false, windowsHide: true, ...options });
    let stdout = "";
    let stderr = "";
    child.stdout?.on("data", (chunk) => { stdout += chunk; });
    child.stderr?.on("data", (chunk) => { stderr += chunk; });
    child.on("error", (error) => reject(error));
    child.on("close", (code) => code === 0
      ? resolve({ stdout, stderr })
      : reject(new Error(`${command} exited with ${code}: ${(stderr || stdout).trim()}`)));
  });
}

function safeGroupDirectory(group) {
  const slug = group.name.normalize("NFKC").replace(/[<>:"/\\|?*\x00-\x1f]/g, "-").replace(/\s+/g, "-").replace(/-+/g, "-").replace(/^[.-]+|[.-]+$/g, "").slice(0, 64) || "source";
  const hash = crypto.createHash("sha1").update(group.files.join("\n")).digest("hex").slice(0, 8);
  return `${slug}-${hash}`;
}

async function renderScrollableDocument(browser, documentPath, outputDirectory, count, log = () => {}) {
  await fs.mkdir(outputDirectory, { recursive: true });
  log(`open ${documentPath}`);
  const page = await browser.newPage({
    viewport: { width: THUMBNAIL_WIDTH, height: THUMBNAIL_HEIGHT },
    deviceScaleFactor: 1,
    colorScheme: "light"
  });
  try {
    log(`navigate ${documentPath}`);
    await page.goto(pathToFileURL(documentPath).href, { waitUntil: "load", timeout: 30000 });
    log(`style ${documentPath}`);
    await page.addStyleTag({ content: `
      html, body { background: #fff !important; }
      body { margin: 0 !important; min-width: ${THUMBNAIL_WIDTH}px; }
      img { max-width: 100% !important; }
      video, iframe { display: none !important; }
    ` });
    await Promise.race([
      page.evaluate(() => document.fonts?.ready),
      new Promise((resolve) => setTimeout(resolve, 5000))
    ]);
    log(`images ${documentPath}`);
    await page.waitForFunction(() => [...document.images].every((image) => image.complete), null, { timeout: 10000 }).catch(() => {});
    const documentHeight = await page.evaluate(() => Math.max(document.documentElement.scrollHeight, document.body?.scrollHeight || 0));
    const maxScroll = Math.max(0, documentHeight - THUMBNAIL_HEIGHT);
    const files = [];
    for (let index = 0; index < count; index += 1) {
      const y = count === 1 ? 0 : Math.round(maxScroll * index / (count - 1));
      const fileName = `page-${String(index + 1).padStart(2, "0")}.png`;
      log(`screenshot ${index + 1}/${count} ${documentPath}`);
      await page.evaluate((scrollTop) => window.scrollTo(0, scrollTop), y);
      await page.screenshot({
        path: path.join(outputDirectory, fileName),
        type: "png",
        fullPage: false,
        captureBeyondViewport: false,
        timeout: 10000
      });
      files.push(path.join(outputDirectory, fileName));
    }
    return files;
  } finally {
    await page.close();
  }
}

async function renderPdf(pdfPath, outputDirectory) {
  await fs.mkdir(outputDirectory, { recursive: true });
  const tempDirectory = await fs.mkdtemp(path.join(os.tmpdir(), "carousel-pdf-thumbs-"));
  try {
    const prefix = path.join(tempDirectory, "page");
    await commandResult("pdftoppm", ["-f", "1", "-l", "4", "-png", "-scale-to-x", String(THUMBNAIL_WIDTH), "-scale-to-y", String(THUMBNAIL_HEIGHT), pdfPath, prefix]);
    const rendered = (await fs.readdir(tempDirectory))
      .filter((name) => /^page-\d+\.png$/i.test(name))
      .sort((left, right) => left.localeCompare(right, "en", { numeric: true }));
    if (!rendered.length) throw new Error("pdftoppm produced no PNG files.");
    const files = [];
    for (let index = 0; index < Math.min(4, rendered.length); index += 1) {
      const fileName = `page-${String(index + 1).padStart(2, "0")}.png`;
      await fs.copyFile(path.join(tempDirectory, rendered[index]), path.join(outputDirectory, fileName));
      files.push(path.join(outputDirectory, fileName));
    }
    return files;
  } finally {
    await fs.rm(tempDirectory, { recursive: true, force: true });
  }
}

async function renderDocx(browser, docxPath, outputDirectory, log) {
  const tempDirectory = await fs.mkdtemp(path.join(os.tmpdir(), "carousel-docx-thumbs-"));
  try {
    const htmlPath = path.join(tempDirectory, "document.html");
    await commandResult("pandoc", [docxPath, "--standalone", "--to", "html5", `--extract-media=${path.join(tempDirectory, "media")}`, "--output", htmlPath]);
    return await renderScrollableDocument(browser, htmlPath, outputDirectory, 4, log);
  } finally {
    await fs.rm(tempDirectory, { recursive: true, force: true });
  }
}

async function renderCandidate(browser, candidate, outputDirectory, log) {
  const extension = path.extname(candidate).toLowerCase();
  if (extension === ".pdf") return renderPdf(candidate, outputDirectory);
  if (extension === ".docx") return renderDocx(browser, candidate, outputDirectory, log);
  if (extension === ".html" || extension === ".htm") return renderScrollableDocument(browser, candidate, outputDirectory, 2, log);
  throw new Error(`Unsupported thumbnail source: ${candidate}`);
}

function candidateFailure(candidate, error) {
  const extension = path.extname(candidate).toLowerCase();
  const message = error?.message || String(error);
  const missing = /ENOENT|not found|cannot find/i.test(message);
  if (extension === ".pdf") {
    return diagnostic(missing ? "E_PDF_RENDERER_MISSING" : "E_PDF_THUMBNAIL_FAILED", missing ? "pdftoppm is required to render PDF thumbnails." : "PDF thumbnail rendering failed.", {
      actual: message,
      expected: "The first four PDF pages rendered as PNG",
      action: missing ? "Install Poppler/pdftoppm and ensure it is on PATH, then rerun preflight.py and source-prep.mjs." : "Open the PDF to confirm it is readable; repair or replace it, then rerun source-prep.mjs."
    });
  }
  if (extension === ".docx") {
    return diagnostic(missing ? "E_DOCX_CONVERTER_MISSING" : "E_DOCX_THUMBNAIL_FAILED", missing ? "pandoc is required to render DOCX thumbnails." : "DOCX thumbnail rendering failed.", {
      actual: message,
      expected: "DOCX converted to local HTML and rendered as four PNG previews",
      action: missing ? "Install Pandoc and ensure it is on PATH, then rerun preflight.py and source-prep.mjs." : "Open the DOCX to confirm it is readable; repair or replace it, then rerun source-prep.mjs."
    });
  }
  return diagnostic("E_HTML_THUMBNAIL_FAILED", "Local HTML thumbnail rendering failed.", {
    actual: message,
    expected: "Two 1240×1754 PNG previews",
    action: "Open the local HTML to confirm it renders, fix missing local assets if needed, then rerun source-prep.mjs."
  });
}

function relativeForManifest(workspace, value) {
  return path.relative(workspace, value).split(path.sep).join("/");
}

export function selectEndcardThumbnails(groups, limit = 4) {
  const selected = [];
  const maxLength = Math.max(0, ...groups.map((group) => group.thumbnails.length));
  for (let index = 0; index < maxLength && selected.length < limit; index += 1) {
    for (const group of groups) {
      if (group.thumbnails[index]) selected.push(group.thumbnails[index]);
      if (selected.length === limit) break;
    }
  }
  return selected;
}

export async function prepareSources(options = {}) {
  const workspace = path.resolve(options.workspace || process.cwd());
  const sourceDirectory = path.resolve(options.sourceDirectory || path.join(workspace, "信源"));
  const outputRoot = path.resolve(options.outputDirectory || path.join(workspace, "视频图"));
  const thumbnailRoot = path.join(outputRoot, "信源缩略图");
  const manifestPath = path.join(outputRoot, "source-manifest.json");
  await fs.mkdir(outputRoot, { recursive: true });
  const debugLog = options.debugLog ? path.resolve(options.debugLog) : "";
  if (debugLog) await fs.writeFile(debugLog, "", "utf8");
  const log = options.debug ? (message) => {
    const line = `[source-prep] ${message}\n`;
    process.stderr.write(line);
    if (debugLog) fsSync.appendFileSync(debugLog, line, "utf8");
  } : () => {};

  const discovered = await discoverSources(workspace, sourceDirectory);
  const groups = groupSources(discovered.files);
  if (!groups.length) {
    const manifest = {
      version: 1,
      status: "source-required",
      workspace,
      sourceDirectory,
      discoveryMode: discovered.mode,
      groups: [],
      errors: [diagnostic("E_SOURCE_REQUIRED", "No local HTML, DOCX, or PDF source was found.", {
        location: sourceDirectory,
        expected: "At least one supported source file",
        action: `Place source files in ${sourceDirectory}, then rerun source-prep.mjs.`
      })]
    };
    await fs.writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
    return { manifest, manifestPath };
  }

  log("load Playwright");
  const playwright = await loadPlaywright();
  log("launch browser");
  const browser = await playwright.chromium.launch({ ...(await browserLaunchOptions()), timeout: 15000 });
  log("browser ready");
  const preparedGroups = [];
  try {
    for (const group of groups) {
      const groupOutput = path.join(thumbnailRoot, safeGroupDirectory(group));
      const attempts = [];
      let selected = "";
      let thumbnails = [];
      for (const candidate of group.thumbnailCandidates) {
        try {
          log(`try ${candidate}`);
          thumbnails = await renderCandidate(browser, candidate, groupOutput, log);
          selected = candidate;
          attempts.push({ source: relativeForManifest(workspace, candidate), status: "selected" });
          break;
        } catch (error) {
          attempts.push({ source: relativeForManifest(workspace, candidate), status: "failed", error: candidateFailure(candidate, error) });
        }
      }
      preparedGroups.push({
        name: group.name,
        files: group.files.map((file) => relativeForManifest(workspace, file)),
        contentSource: relativeForManifest(workspace, group.contentSource),
        thumbnailSource: selected ? relativeForManifest(workspace, selected) : "",
        thumbnails: thumbnails.map((file) => relativeForManifest(workspace, file)),
        thumbnailAttempts: attempts,
        ...(selected ? {} : { error: diagnostic("E_THUMBNAILS_GENERATION", `No thumbnail candidate succeeded for source group “${group.name}”.`, {
          actual: attempts.map((attempt) => `${attempt.source}: ${attempt.error?.code || attempt.status}`).join(" | "),
          expected: "At least one PDF, DOCX, or HTML thumbnail source renders successfully",
          action: "Fix the first candidate or provide another same-name format, then rerun source-prep.mjs."
        }) })
      });
    }
  } finally {
    await browser.close();
  }

  const errors = preparedGroups.flatMap((group) => group.error ? [group.error] : []);
  const endcardThumbnails = selectEndcardThumbnails(preparedGroups);
  const manifest = {
    version: 1,
    status: errors.length ? "failed" : "ready",
    workspace,
    sourceDirectory,
    discoveryMode: discovered.mode,
    priorities: { content: "HTML > DOCX > PDF", thumbnails: "PDF > DOCX > HTML" },
    thumbnailSize: { width: THUMBNAIL_WIDTH, height: THUMBNAIL_HEIGHT },
    inkstoneInputs: preparedGroups.map((group) => path.resolve(workspace, group.contentSource)),
    thumbnailMarkdown: [
      ":::thumbnails",
      ...endcardThumbnails.map((thumbnail) => {
        const relative = relativeForManifest(outputRoot, path.resolve(workspace, thumbnail));
        return `![](${relative.startsWith(".") ? relative : `./${relative}`})`;
      }),
      ":::"
    ].join("\n"),
    groups: preparedGroups,
    errors
  };
  await fs.writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  return { manifest, manifestPath };
}

async function main() {
  const options = parseArguments(process.argv.slice(2));
  if (options.help) {
    process.stdout.write("Usage: node source-prep.mjs [--workspace <dir>] [--source-dir <dir>] [--output <dir>] [--json] [--debug] [--debug-log <file>]\n");
    return;
  }
  const { manifest, manifestPath } = await prepareSources(options);
  if (options.json) {
    process.stdout.write(`${JSON.stringify({ ...manifest, manifestPath }, null, 2)}\n`);
  } else {
    process.stdout.write(`Source manifest: ${manifestPath}\n`);
    manifest.groups.forEach((group) => {
      process.stdout.write(`- ${group.name}: Inkstone <- ${group.contentSource}; thumbnails <- ${group.thumbnailSource || "FAILED"}\n`);
    });
    manifest.errors.forEach((item) => process.stderr.write(`${formatDiagnostic(item)}\n`));
  }
  if (manifest.status !== "ready") process.exitCode = 1;
}

const entryPointPath = process.argv[1] ? await fs.realpath(path.resolve(process.argv[1])).catch(() => path.resolve(process.argv[1])) : "";
if (SCRIPT_PATH === entryPointPath) {
  main().catch((error) => {
    const diagnostics = diagnosticsFromError(error, "E_SOURCE_PREP_FAILED");
    if (process.argv.includes("--json")) process.stdout.write(`${JSON.stringify({ status: "failed", errors: diagnostics }, null, 2)}\n`);
    else diagnostics.forEach((item) => process.stderr.write(`${formatDiagnostic(item)}\n`));
    process.exitCode = 1;
  });
}
