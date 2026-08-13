#!/usr/bin/env node

// 渲染编排：参数解析、HTML 注入、渲染检查（溢出 / 填充率 / 内容量）、截图与 manifest。
// 解析逻辑在 parser.mjs，图片嵌入在 images.mjs，环境探测在 browser.mjs。

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { parseDocument, validateDocument, plainText } from "./parser.mjs";
import { embedLocalMarkdownImages } from "./images.mjs";
import { loadPlaywright, browserLaunchOptions, createStagingDirectory, discardStagingDirectory, commitOwnedOutputs } from "./browser.mjs";
import { diagnostic, diagnosticError, diagnosticsError, diagnosticsFromError, formatDiagnostic, parseFailure } from "./diagnostics.mjs";

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

export function buildAuditTargets(pageDetails) {
  const body = pageDetails.filter((page) => page.kind === "body");
  const densestBody = body.reduce((best, page) => !best || (page.fill ?? -1) > (best.fill ?? -1) ? page : best, null);
  return {
    cover: pageDetails.find((page) => page.kind === "cover")?.file || "",
    densestBody: densestBody?.file || "",
    riskPages: body.filter((page) => page.features.includes("risk")).map((page) => page.file),
    calloutPages: body.filter((page) => page.features.includes("callout")).map((page) => page.file),
    fillWarningPages: body.filter((page) => !page.lastBody && page.fill < FILL_WARNING_THRESHOLD).map((page) => page.file),
    endcard: pageDetails.find((page) => page.kind === "endcard")?.file || ""
  };
}

function parseArguments(argv) {
  const options = { input: "", output: "", theme: "", endcard: "", json: false };
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
    throw diagnosticError("E_ENDCARD_UNSUPPORTED", `Unsupported endcard variant "${endcardVariant}".`, {
      actual: endcardVariant,
      expected: "guided or legacy",
      action: "Use --endcard guided or --endcard legacy."
    });
  }
  let rawSource;
  try {
    rawSource = await fs.readFile(inputPath, "utf8");
  } catch (error) {
    throw diagnosticError("E_INPUT_READ", "The input Markdown file could not be read.", {
      location: inputPath,
      actual: error.message,
      action: "Confirm the file exists and is readable UTF-8 text, then rerun render.mjs."
    });
  }
  let source;
  try {
    source = await embedLocalMarkdownImages(rawSource, inputPath);
  } catch (error) {
    throw diagnosticError("E_IMAGE_READ", "A local Markdown image could not be embedded.", {
      actual: error.message,
      expected: "Every local image path resolves from the Markdown file directory",
      action: "Fix the reported image path or regenerate the source thumbnails, then rerun render.mjs."
    });
  }
  let document;
  try {
    document = parseDocument(source);
  } catch (error) {
    throw diagnosticsError([parseFailure(error)]);
  }
  if (themeOverride) document.meta.theme = String(themeOverride).trim().toLowerCase();
  if (coverOnly && !document.meta.cover) {
    throw diagnosticError("E_COVER_REQUIRED", "--cover-only cannot run when front matter sets cover: false.", {
      action: "Enable the cover or remove --cover-only."
    });
  }
  const validation = validateDocument(document);
  if (validation.errors.length) throw diagnosticsError(validation.errors);
  validation.warnings.forEach((warning) => process.stderr.write(`${formatDiagnostic(warning, "Warning")}\n`));

  let assets;
  try {
    assets = await Promise.all([
      fs.readFile(path.join(SKILL_DIR, "assets/theme.css"), "utf8"),
      fs.readFile(path.join(SKILL_DIR, "assets/cover.js"), "utf8"),
      fs.readFile(path.join(SKILL_DIR, "assets/endcard.js"), "utf8"),
      fs.readFile(path.join(SKILL_DIR, "assets/runtime.js"), "utf8"),
      loadPlaywright(),
      fs.readFile(path.join(SKILL_DIR, "assets/zhifujie-qr.png"))
    ]);
  } catch (error) {
    throw diagnosticError("E_RENDER_DEPENDENCY", "A renderer dependency or bundled asset could not be loaded.", {
      actual: error.message,
      action: "Run preflight.py. Restore missing assets or install the reported dependency, then rerun render.mjs."
    });
  }
  const [css, coverScript, endcardScript, runtimeScript, playwright, qrBytes] = assets;
  document.meta.brandQr = `data:image/png;base64,${qrBytes.toString("base64")}`;
  document.meta.endcard = endcard;

  const stagingDirectory = await createStagingDirectory(outputDirectory);
  let browser;
  try {
    try {
      browser = await playwright.chromium.launch({ ...(await browserLaunchOptions()), timeout: 15000 });
    } catch (error) {
      throw diagnosticError("E_BROWSER_LAUNCH", "Chromium could not be launched for rendering.", {
        actual: error.message,
        action: "Run preflight.py and repair the reported browser installation or PLAYWRIGHT_CHROMIUM_EXECUTABLE path."
      });
    }
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
    if (brokenImages.length) {
      throw diagnosticError("E_IMAGE_LOAD", "One or more Markdown images failed to load.", {
        actual: brokenImages.join(", "),
        expected: "Every referenced image loads successfully",
        action: "Fix the image path or regenerate the missing source thumbnail."
      });
    }

    const report = await page.evaluate(() => window.__renderReport);
    const renderErrors = [];
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
      report.overflowPages.forEach((pageNumber) => renderErrors.push(diagnostic("E_PAGE_OVERFLOW", `Content overflows rendered page ${pageNumber}.`, {
        page: pageNumber,
        expected: "All blocks fit inside the 1080×1440 page flow",
        action: "Shorten the oversized unbreakable block; use a page break only between complete ideas."
      })));
    }

    // 正文页填充率检查（导流页与最后一页正文页由 runtime 标记豁免）。--cover-only 只出封面预览，跳过正文检查。
    // 提示文案自带算法说明，避免调用方为了理解百分比含义去翻源码。
    const FILL_ALGO_NOTE = "Fill ratio is area-based: sum of each block's rendered height ÷ page flow height (gaps between blocks are layout rhythm and not counted). Per-page values are written to fillRatios in manifest.json. Do not guess a page's contents from a stale manifest — any content change shifts all later pagination; re-render, read the new fillRatios, then add or remove content so the total lands just above a whole number of pages.";
    const percent = (value) => `${Math.round(value * 100)}%`;
    const sparsePages = coverOnly ? [] : (report.fillRatios || []).filter((entry) => !entry.last && entry.fill < FILL_WARNING_THRESHOLD);
    sparsePages.filter((entry) => entry.fill >= FILL_ERROR_THRESHOLD).forEach((entry) => {
      const message = `Body page ${entry.page} is only ${percent(entry.fill)} full (warns below ${percent(FILL_WARNING_THRESHOLD)}, fails below ${percent(FILL_ERROR_THRESHOLD)}). Usually an unbreakable block rounding up or an unnecessary :::pagebreak — inspect the PNG and rebalance if the page looks visibly empty.`;
      const warning = diagnostic("W_PAGE_FILL_LOW", message, {
        page: entry.page,
        actual: percent(entry.fill),
        expected: `At least ${percent(FILL_WARNING_THRESHOLD)}`,
        action: "Inspect the new PNG and rebalance nearby content only if the page looks visibly empty."
      });
      validation.warnings.push(warning);
      process.stderr.write(`${formatDiagnostic(warning, "Warning")}\n`);
    });
    const sparseErrors = sparsePages.filter((entry) => entry.fill < FILL_ERROR_THRESHOLD);
    if (sparseErrors.length) {
      renderErrors.push(...sparseErrors.map((entry) => diagnostic("E_PAGE_FILL_LOW", `Body page ${entry.page} is below the minimum fill ratio.`, {
        page: entry.page,
        actual: percent(entry.fill),
        expected: `At least ${percent(FILL_ERROR_THRESHOLD)}`,
        action: `Re-render and inspect the current page. Rebalance nearby source-grounded content; if it is a trailing near-empty page, trim earlier content. ${FILL_ALGO_NOTE}`
      })));
    }

    // 内容量下限检查（--cover-only 跳过）：正文页数 = fillRatios 条数（导流页不计入）。
    const bodyPages = (report.fillRatios || []).length;
    if (!coverOnly && bodyPages < MIN_BODY_PAGES) {
      renderErrors.push(diagnostic("E_BODY_PAGES_MIN", "The carousel does not meet the required body-page count.", {
        actual: `${bodyPages} body page(s), ${report.pageCount} total page(s)`,
        expected: `${MIN_BODY_PAGES} body pages, ${MIN_BODY_PAGES + 2} total pages`,
        action: "Use unused source facts first, then add audited web research if needed; expand and re-render without padding or repetition."
      }));
    }
    if (renderErrors.length) throw diagnosticsError(renderErrors);

    const cards = page.locator(".page-card");
    const count = await cards.count();
    const files = [];
    for (let index = 0; index < count; index += 1) {
      const kind = await cards.nth(index).getAttribute("data-kind");
      if (coverOnly && kind !== "cover") continue;
      const fileName = `${String(index + 1).padStart(2, "0")}-${kind === "cover" ? "cover" : "page"}.png`;
      await cards.nth(index).screenshot({ path: path.join(stagingDirectory, fileName), type: "png" });
      files.push(fileName);
    }

    const rawPageDetails = await page.evaluate(() => [...document.querySelectorAll(".page-card")].map((card, index) => {
      const kind = card.classList.contains("endcard-page") ? "endcard" : (card.dataset.kind || "body");
      const labelNode = card.querySelector(".cover-title, .section-text, .subheading, .lead-block, .body-paragraph, .thumbnails-heading");
      const features = [
        ["risk", ".risk-block"],
        ["callout", ".callout-block"],
        ["table", ".markdown-table"],
        ["image", ".markdown-image"],
        ["metrics", ".metrics"]
      ].filter(([, selector]) => card.querySelector(selector)).map(([name]) => name);
      return {
        page: index + 1,
        kind,
        label: (labelNode?.textContent || "").replace(/\s+/g, " ").trim().slice(0, 120),
        features
      };
    }));
    const fills = new Map((report.fillRatios || []).map((entry) => [entry.page, entry]));
    const pageDetails = rawPageDetails
      .filter((detail) => !coverOnly || detail.kind === "cover")
      .map((detail) => {
        const fill = fills.get(detail.page);
        return {
          ...detail,
          file: `${String(detail.page).padStart(2, "0")}-${detail.kind === "cover" ? "cover" : "page"}.png`,
          ...(fill ? { fill: fill.fill, lastBody: fill.last } : {})
        };
      });

    const manifest = {
      title: plainText(document.meta.title),
      theme: document.meta.theme,
      endcard,
      coverOnly,
      pages: files.length,
      bodyPages: pageDetails.filter((detail) => detail.kind === "body").length,
      totalPages: files.length,
      width: PAGE_WIDTH,
      height: PAGE_HEIGHT,
      files,
      pageDetails,
      auditTargets: buildAuditTargets(pageDetails),
      fillRatios: report.fillRatios || [],
      warnings: validation.warnings
    };
    await fs.writeFile(path.join(stagingDirectory, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
    await browser.close();
    browser = null;
    await commitOwnedOutputs(stagingDirectory, outputDirectory);
    return manifest;
  } finally {
    if (browser) await browser.close();
    await discardStagingDirectory(stagingDirectory);
  }
}

async function main() {
  const options = parseArguments(process.argv.slice(2));
  if (options.help) {
    process.stdout.write("Usage: node render.mjs <input.md> --output <output-dir> [--theme classic|finance|editorial|tech] [--endcard guided|legacy] [--cover-only] [--json]\n");
    return;
  }
  if (!options.input || !options.output) {
    throw new Error("Usage: node render.mjs <input.md> --output <output-dir>");
  }
  const inputPath = path.resolve(options.input);
  const outputDirectory = path.resolve(options.output);
  const manifest = await render(inputPath, outputDirectory, options.theme, options.endcard, options.coverOnly);
  if (options.json) {
    process.stdout.write(`${JSON.stringify({ ok: true, outputDirectory, manifest }, null, 2)}\n`);
  } else {
    process.stdout.write(`Rendered ${manifest.pages} page(s) to ${outputDirectory}\n`);
    manifest.files.forEach((file) => process.stdout.write(`${path.join(outputDirectory, file)}\n`));
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
