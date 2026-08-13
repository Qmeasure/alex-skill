#!/usr/bin/env node

// 渲染编排：参数解析、HTML 注入、渲染检查（溢出 / 填充率 / 内容量）、截图与 manifest。
// 解析逻辑在 parser.mjs，图片嵌入在 images.mjs，环境探测在 browser.mjs。

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { parseDocument, validateDocument, plainText } from "./parser.mjs";
import { embedLocalMarkdownImages } from "./images.mjs";
import { loadPlaywright, browserLaunchOptions, cleanOwnedOutputs } from "./browser.mjs";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = path.resolve(SCRIPT_DIR, "..");
const PAGE_WIDTH = 1080;
const PAGE_HEIGHT = 1440;
// 正文页填充率红线（面积法：各块实际高度之和 ÷ flow 高度）：
// 低于 FILL_ERROR_THRESHOLD 渲染失败，低于 FILL_WARNING_THRESHOLD 打警告（可能是不可拆块进位，需自查）。
const FILL_ERROR_THRESHOLD = 0.7;
const FILL_WARNING_THRESHOLD = 0.75;
// 内容量下限：封面与导流页固定占用 2 页，正文少于此值（总页数 ≤ 8）视为内容量不足。
const MIN_BODY_PAGES = 7;
const SUPPORTED_ENDCARD_VARIANTS = new Set(["guided", "legacy"]);

function parseArguments(argv) {
  const options = { input: "", output: "", theme: "", endcard: "" };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--output" || value === "-o") {
      options.output = argv[index + 1] || "";
      index += 1;
    } else if (value === "--theme") {
      options.theme = argv[index + 1] || "";
      index += 1;
    } else if (value === "--endcard") {
      options.endcard = argv[index + 1] || "";
      index += 1;
    } else if (value === "--cover-only") {
      options.coverOnly = true;
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

function buildHtml(document, css, runtimeScripts) {
  const payload = JSON.stringify(document).replace(/</g, "\\u003c").replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
  const scriptTags = runtimeScripts.map((source) => `<script>${source}</script>`).join("\n");
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
  ${scriptTags}
</body>
</html>`;
}

async function render(inputPath, outputDirectory, themeOverride = "", endcardVariant = "", coverOnly = false) {
  const endcard = String(endcardVariant || "guided").trim().toLowerCase();
  if (!SUPPORTED_ENDCARD_VARIANTS.has(endcard)) {
    throw new Error(`Unsupported endcard variant "${endcardVariant}". Use guided or legacy.`);
  }
  const rawSource = await fs.readFile(inputPath, "utf8");
  const source = await embedLocalMarkdownImages(rawSource, inputPath);
  const document = parseDocument(source);
  if (themeOverride) document.meta.theme = String(themeOverride).trim().toLowerCase();
  if (coverOnly && !document.meta.cover) throw new Error("--cover-only requires a cover (front matter `cover: false` is set).");
  const validation = validateDocument(document);
  if (validation.errors.length) throw new Error(validation.errors.join("\n"));
  validation.warnings.forEach((warning) => process.stderr.write(`Warning: ${warning}\n`));

  const [css, coverScript, endcardScript, runtimeScript, playwright, qrBytes] = await Promise.all([
    fs.readFile(path.join(SKILL_DIR, "assets/theme.css"), "utf8"),
    fs.readFile(path.join(SKILL_DIR, "assets/cover.js"), "utf8"),
    fs.readFile(path.join(SKILL_DIR, "assets/endcard.js"), "utf8"),
    fs.readFile(path.join(SKILL_DIR, "assets/runtime.js"), "utf8"),
    loadPlaywright(),
    fs.readFile(path.join(SKILL_DIR, "assets/zhifujie-qr.png"))
  ]);
  document.meta.brandQr = `data:image/png;base64,${qrBytes.toString("base64")}`;
  document.meta.endcard = endcard;

  await cleanOwnedOutputs(outputDirectory);
  const browser = await playwright.chromium.launch(await browserLaunchOptions());
  try {
    const page = await browser.newPage({
      viewport: { width: PAGE_WIDTH, height: PAGE_HEIGHT },
      deviceScaleFactor: 1
    });
    await page.setContent(buildHtml(document, css, [coverScript, endcardScript, runtimeScript]), { waitUntil: "load" });
    await page.waitForFunction(() => document.body.dataset.renderReady === "true");
    await page.waitForFunction(() => [...document.images].every((image) => image.complete), null, { timeout: 15000 });
    await page.evaluate(() => document.fonts?.ready);

    const brokenImages = await page.evaluate(() => [...document.images]
      .filter((image) => image.naturalWidth === 0)
      .map((image) => image.alt || image.getAttribute("src")?.slice(0, 80) || "unknown image"));
    if (brokenImages.length) throw new Error(`Markdown image failed to load: ${brokenImages.join(", ")}`);

    const report = await page.evaluate(() => window.__renderReport);
    if (report.overflowPages.length && !coverOnly) {
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

    // 正文页填充率检查（导流页与最后一页正文页由 runtime 标记豁免）。--cover-only 只出封面预览，跳过正文检查。
    // 提示文案自带算法说明，避免调用方为了理解百分比含义去翻源码。
    const FILL_ALGO_NOTE = "Fill ratio is area-based: sum of each block's rendered height ÷ page flow height (gaps between blocks are layout rhythm and not counted). Per-page values are written to fillRatios in manifest.json. Do not guess a page's contents from a stale manifest — any content change shifts all later pagination; re-render, read the new fillRatios, then add or remove content so the total lands just above a whole number of pages.";
    const percent = (value) => `${Math.round(value * 100)}%`;
    const sparsePages = coverOnly ? [] : (report.fillRatios || []).filter((entry) => !entry.last && entry.fill < FILL_WARNING_THRESHOLD);
    sparsePages.filter((entry) => entry.fill >= FILL_ERROR_THRESHOLD).forEach((entry) => {
      const message = `Body page ${entry.page} is only ${percent(entry.fill)} full (warns below ${percent(FILL_WARNING_THRESHOLD)}, fails below ${percent(FILL_ERROR_THRESHOLD)}). Usually an unbreakable block rounding up or an unnecessary :::pagebreak — inspect the PNG and rebalance if the page looks visibly empty.`;
      validation.warnings.push(message);
      process.stderr.write(`Warning: ${message}\n`);
    });
    const sparseErrors = sparsePages.filter((entry) => entry.fill < FILL_ERROR_THRESHOLD);
    if (sparseErrors.length) {
      const detail = sparseErrors.map((entry) => `page ${entry.page} filled ${percent(entry.fill)}`).join(", ");
      throw new Error(`Sparse body page(s): ${detail} (minimum ${percent(FILL_ERROR_THRESHOLD)}). ${FILL_ALGO_NOTE} If the sparse page is a near-empty trailing page, trim earlier content instead of appending more.`);
    }

    // 内容量下限检查（--cover-only 跳过）：正文页数 = fillRatios 条数（导流页不计入）。
    const bodyPages = (report.fillRatios || []).length;
    if (!coverOnly && bodyPages < MIN_BODY_PAGES) {
      throw new Error(`Insufficient content: only ${bodyPages} body page(s) (${report.pageCount} total including cover and endcard); minimum is ${MIN_BODY_PAGES} body pages (${MIN_BODY_PAGES + 2} total). Go back to the source material for facts not yet used, or search the web for story material per references/narrative-style.md, then expand the Markdown and re-render.`);
    }

    const cards = page.locator(".page-card");
    const count = await cards.count();
    const files = [];
    for (let index = 0; index < count; index += 1) {
      const kind = await cards.nth(index).getAttribute("data-kind");
      if (coverOnly && kind !== "cover") continue;
      const fileName = `${String(index + 1).padStart(2, "0")}-${kind === "cover" ? "cover" : "page"}.png`;
      await cards.nth(index).screenshot({ path: path.join(outputDirectory, fileName), type: "png" });
      files.push(fileName);
    }

    const manifest = {
      title: plainText(document.meta.title),
      theme: document.meta.theme,
      endcard,
      coverOnly,
      pages: files.length,
      width: PAGE_WIDTH,
      height: PAGE_HEIGHT,
      files,
      fillRatios: report.fillRatios || [],
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
    process.stdout.write("Usage: node render.mjs <input.md> --output <output-dir> [--theme classic|finance|editorial|tech] [--endcard guided|legacy] [--cover-only]\n");
    return;
  }
  if (!options.input || !options.output) {
    throw new Error("Usage: node render.mjs <input.md> --output <output-dir>");
  }
  const inputPath = path.resolve(options.input);
  const outputDirectory = path.resolve(options.output);
  const manifest = await render(inputPath, outputDirectory, options.theme, options.endcard, options.coverOnly);
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
