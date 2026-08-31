import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { discoverSources, groupSources, prepareSources, selectEndcardThumbnails } from "../scripts/source-prep.mjs";
import { browserLaunchOptions, loadPlaywright } from "../scripts/browser.mjs";

function run(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { shell: false, windowsHide: true });
    let stderr = "";
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", reject);
    child.on("close", (code) => code === 0 ? resolve() : reject(new Error(`${command} exited with ${code}: ${stderr}`)));
  });
}

async function assertPngSize(filePath) {
  const png = await fs.readFile(filePath);
  assert.equal(png.readUInt32BE(16), 1240);
  assert.equal(png.readUInt32BE(20), 1754);
}

test("same-name formats form one group with independent priorities", () => {
  const root = path.resolve("C:/example");
  const groups = groupSources([
    path.join(root, "报告.pdf"),
    path.join(root, "报告.docx"),
    path.join(root, "报告.html"),
    path.join(root, "补充.pdf")
  ]);
  assert.equal(groups.length, 2);
  const report = groups.find((group) => group.name === "报告");
  assert.equal(path.extname(report.contentSource).toLowerCase(), ".html");
  assert.equal(path.extname(report.thumbnailCandidates[0]).toLowerCase(), ".pdf");
});

test("multi-source endcard selection is round-robin and capped at four", () => {
  const selected = selectEndcardThumbnails([
    { thumbnails: ["a1", "a2", "a3", "a4"] },
    { thumbnails: ["b1", "b2"] },
    { thumbnails: ["c1", "c2"] }
  ]);
  assert.deepEqual(selected, ["a1", "b1", "c1", "a2"]);
});

test("source directory is created and workspace root is a fallback", async (context) => {
  const workspace = await fs.mkdtemp(path.join(os.tmpdir(), "carousel-source-discovery-"));
  context.after(() => fs.rm(workspace, { recursive: true, force: true }));
  await fs.writeFile(path.join(workspace, "article.html"), "<p>source</p>", "utf8");
  const sourceDirectory = path.join(workspace, "信源");
  const discovered = await discoverSources(workspace, sourceDirectory);
  assert.equal(discovered.mode, "workspace-root-fallback");
  assert.equal(discovered.files.length, 1);
  assert.equal((await fs.stat(sourceDirectory)).isDirectory(), true);
});

test("empty workspace writes an actionable source-required manifest", async (context) => {
  const workspace = await fs.mkdtemp(path.join(os.tmpdir(), "carousel-source-empty-"));
  context.after(() => fs.rm(workspace, { recursive: true, force: true }));
  const { manifest, manifestPath } = await prepareSources({ workspace });
  assert.equal(manifest.status, "source-required");
  assert.equal(manifest.errors[0].code, "E_SOURCE_REQUIRED");
  assert.equal(JSON.parse(await fs.readFile(manifestPath, "utf8")).errors[0].code, "E_SOURCE_REQUIRED");
});

test("local HTML produces two exact A4-ratio thumbnails", async (context) => {
  const workspace = await fs.mkdtemp(path.join(os.tmpdir(), "carousel-source-html-"));
  context.after(() => fs.rm(workspace, { recursive: true, force: true }));
  const sourceDirectory = path.join(workspace, "信源");
  await fs.mkdir(sourceDirectory, { recursive: true });
  await fs.writeFile(path.join(sourceDirectory, "article.html"), `<!doctype html><meta charset="utf-8"><style>body{font:32px sans-serif}section{height:1800px}</style><section>第一页</section><section>第二页</section>`, "utf8");
  const { manifest, cacheHit } = await prepareSources({ workspace });
  assert.equal(cacheHit, false);
  assert.equal(manifest.status, "ready");
  assert.match(manifest.groups[0].thumbnailSource, /article\.html$/i);
  assert.equal(manifest.groups[0].thumbnails.length, 2);
  assert.ok(manifest.thumbnailMarkdown.startsWith(":::thumbnails\n!["));
  assert.ok(manifest.thumbnailMarkdown.endsWith("\n:::"));
  assert.deepEqual(manifest.inkstoneInputs, [path.join(sourceDirectory, "article.html")]);
  for (const relative of manifest.groups[0].thumbnails) {
    await assertPngSize(path.join(workspace, relative));
  }
  const cached = await prepareSources({ workspace });
  assert.equal(cached.cacheHit, true);
  assert.equal(cached.manifest.sourceFingerprint, manifest.sourceFingerprint);
});

test("same-name HTML and PDF use HTML for content and PDF for four thumbnails", { timeout: 60000 }, async (context) => {
  const workspace = await fs.mkdtemp(path.join(os.tmpdir(), "carousel-source-pdf-"));
  context.after(() => fs.rm(workspace, { recursive: true, force: true }));
  const sourceDirectory = path.join(workspace, "信源");
  await fs.mkdir(sourceDirectory, { recursive: true });
  const htmlPath = path.join(sourceDirectory, "report.html");
  const pdfPath = path.join(sourceDirectory, "report.pdf");
  await fs.writeFile(htmlPath, "<!doctype html><meta charset=\"utf-8\"><h1>HTML 正文</h1>", "utf8");
  const playwright = await loadPlaywright();
  const browser = await playwright.chromium.launch(await browserLaunchOptions());
  try {
    const page = await browser.newPage();
    await page.setContent("<style>article{page-break-after:always;height:900px;font:40px sans-serif}</style>" + [1, 2, 3, 4, 5].map((number) => `<article>PDF ${number}</article>`).join(""));
    await page.pdf({ path: pdfPath, format: "A4", printBackground: true });
  } finally {
    await browser.close();
  }
  const { manifest } = await prepareSources({ workspace });
  const group = manifest.groups[0];
  assert.match(group.contentSource, /report\.html$/i);
  assert.match(group.thumbnailSource, /report\.pdf$/i);
  assert.equal(group.thumbnails.length, 4);
  for (const relative of group.thumbnails) await assertPngSize(path.join(workspace, relative));
});

test("DOCX source produces four exact-size thumbnails", { timeout: 60000 }, async (context) => {
  const workspace = await fs.mkdtemp(path.join(os.tmpdir(), "carousel-source-docx-"));
  context.after(() => fs.rm(workspace, { recursive: true, force: true }));
  const sourceDirectory = path.join(workspace, "信源");
  await fs.mkdir(sourceDirectory, { recursive: true });
  const markdownPath = path.join(workspace, "document.md");
  const docxPath = path.join(sourceDirectory, "document.docx");
  await fs.writeFile(markdownPath, "# DOCX 预览\n\n" + "这是用于缩略图的内容。\n\n".repeat(80), "utf8");
  try {
    await run("pandoc", [markdownPath, "--output", docxPath]);
  } catch (error) {
    if (error.code === "ENOENT") return context.skip("pandoc is unavailable");
    throw error;
  }
  const { manifest } = await prepareSources({ workspace });
  const group = manifest.groups[0];
  assert.equal(manifest.status, "ready");
  assert.match(group.contentSource, /document\.docx$/i);
  assert.match(group.thumbnailSource, /document\.docx$/i);
  assert.equal(group.thumbnails.length, 4);
  for (const relative of group.thumbnails) await assertPngSize(path.join(workspace, relative));
});

test("broken higher-priority thumbnail source records a code and falls back", { timeout: 60000 }, async (context) => {
  const workspace = await fs.mkdtemp(path.join(os.tmpdir(), "carousel-source-fallback-"));
  context.after(() => fs.rm(workspace, { recursive: true, force: true }));
  const sourceDirectory = path.join(workspace, "信源");
  await fs.mkdir(sourceDirectory, { recursive: true });
  await fs.writeFile(path.join(sourceDirectory, "report.pdf"), "not a pdf", "utf8");
  await fs.writeFile(path.join(sourceDirectory, "report.html"), "<!doctype html><meta charset=\"utf-8\"><p>HTML fallback</p>", "utf8");
  const { manifest } = await prepareSources({ workspace });
  const group = manifest.groups[0];
  assert.equal(manifest.status, "ready");
  assert.match(group.thumbnailSource, /report\.html$/i);
  assert.equal(group.thumbnailAttempts[0].status, "failed");
  assert.ok(["E_PDF_THUMBNAIL_FAILED", "E_PDF_RENDERER_MISSING"].includes(group.thumbnailAttempts[0].error.code));
  assert.equal(group.thumbnailAttempts[1].status, "selected");
});
