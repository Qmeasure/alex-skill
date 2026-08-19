#!/usr/bin/env node

// 渲染编排：参数解析、HTML 注入、渲染检查（溢出 / 填充率 / 内容量）、截图与 manifest。
// 解析逻辑在 parser.mjs，图片嵌入在 images.mjs，环境探测在 browser.mjs。

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import sharp from "sharp";
import { parseDocument, validateDocument, plainText } from "./parser.mjs";
import { embedLocalMarkdownImages } from "./images.mjs";
import { loadPlaywright, browserLaunchOptions, createStagingDirectory, discardStagingDirectory, commitOwnedOutputs } from "./browser.mjs";
import { diagnostic, diagnosticError, diagnosticsError, diagnosticsFromError, formatDiagnostic, parseFailure } from "./diagnostics.mjs";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = path.resolve(SCRIPT_DIR, "..");
const PAGE_WIDTH = 1080;
const PAGE_HEIGHT = 1440;
const RENDER_SCALE = 2;
const RENDER_WIDTH = PAGE_WIDTH * RENDER_SCALE;
const RENDER_HEIGHT = PAGE_HEIGHT * RENDER_SCALE;
// 正文页填充率红线（面积法：各块实际高度之和 ÷ flow 高度）：
// 低于 FILL_ERROR_THRESHOLD 渲染失败，低于 FILL_WARNING_THRESHOLD 打警告（可能是不可拆块进位，需自查）。
const FILL_ERROR_THRESHOLD = 0.7;
const FILL_WARNING_THRESHOLD = 0.75;
// 页数硬约束：封面与导流页固定占用 2 页，正文必须落在允许区间内。
const MIN_BODY_PAGES = 7;
const MAX_BODY_PAGES = 16;
const SUPPORTED_ENDCARD_VARIANTS = new Set(["native", "guided"]);

export async function downsampleScreenshot(png) {
  const sourceWidth = png.readUInt32BE(16);
  const sourceHeight = png.readUInt32BE(20);
  if (sourceWidth !== RENDER_WIDTH || sourceHeight !== RENDER_HEIGHT) {
    throw diagnosticError("E_RENDER_DIMENSIONS", "The high-resolution screenshot has unexpected dimensions.", {
      actual: `${sourceWidth}×${sourceHeight}`,
      expected: `${RENDER_WIDTH}×${RENDER_HEIGHT}`,
      action: `Keep the browser viewport at ${PAGE_WIDTH}×${PAGE_HEIGHT}, deviceScaleFactor at ${RENDER_SCALE}, and screenshot scale at device.`
    });
  }
  try {
    const { data, info } = await sharp(png)
      .resize(PAGE_WIDTH, PAGE_HEIGHT, { fit: "fill", kernel: sharp.kernel.lanczos3 })
      .png({ compressionLevel: 9, adaptiveFiltering: true })
      .toBuffer({ resolveWithObject: true });
    if (info.width !== PAGE_WIDTH || info.height !== PAGE_HEIGHT) {
      throw new Error(`Sharp returned ${info.width}×${info.height}.`);
    }
    return data;
  } catch (error) {
    throw diagnosticError("E_OUTPUT_RESIZE", "The supersampled screenshot could not be resized to the delivery dimensions.", {
      actual: error.message,
      expected: `${PAGE_WIDTH}×${PAGE_HEIGHT} PNG output`,
      action: "Confirm sharp is installed and operational, then rerun render.mjs."
    });
  }
}

export function resolveEndcardVariant(value = "") {
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

export function qrAssetPathFor(endcard) {
  return endcard === "guided" ? path.join(SKILL_DIR, "assets/zhifujie-qr.png") : null;
}

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

export function debugOutputDirectoryFor(outputDirectory) {
  return `${path.resolve(outputDirectory)}.debug`;
}

export function buildBodyPageCountDiagnostics(bodyPages, totalPages, { coverOnly = false, debugAction = "" } = {}) {
  if (coverOnly) return [];
  const debugSuffix = debugAction ? ` ${debugAction}` : "";
  const errors = [];
  if (bodyPages < MIN_BODY_PAGES) {
    errors.push(diagnostic("E_BODY_PAGES_MIN", "The carousel does not meet the minimum body-page count.", {
      actual: `${bodyPages} body page(s), ${totalPages} total page(s)`,
      expected: `At least ${MIN_BODY_PAGES} body pages, ${MIN_BODY_PAGES + 2} total pages`,
      action: `Use unused source facts first, then add audited web research if needed; expand and re-render without padding or repetition.${debugSuffix}`
    }));
  }
  if (bodyPages > MAX_BODY_PAGES) {
    errors.push(diagnostic("E_BODY_PAGES_MAX", "The carousel exceeds the maximum body-page count.", {
      actual: `${bodyPages} body page(s), ${totalPages} total page(s)`,
      expected: `At most ${MAX_BODY_PAGES} body pages, ${MAX_BODY_PAGES + 2} total pages`,
      action: `Remove redundant or lower-priority material, combine adjacent complete ideas, and re-render; do not shrink text or remove the cover or endcard.${debugSuffix}`
    }));
  }
  return errors;
}

export function buildDebugTargets(pageDetails, diagnostics) {
  const pagesByNumber = new Map(pageDetails.map((page) => [page.page, page.file]));
  const pagesFor = (code) => [...new Set(diagnostics
    .filter((item) => item.code === code && item.page != null)
    .map((item) => item.page))]
    .sort((left, right) => left - right)
    .map((pageNumber) => pagesByNumber.get(pageNumber))
    .filter(Boolean);
  const failingPageNumbers = new Set(diagnostics
    .filter((item) => item.page != null)
    .map((item) => item.page));
  const adjacentPageNumbers = new Set();
  for (const pageNumber of failingPageNumbers) {
    if (pagesByNumber.has(pageNumber - 1) && !failingPageNumbers.has(pageNumber - 1)) adjacentPageNumbers.add(pageNumber - 1);
    if (pagesByNumber.has(pageNumber + 1) && !failingPageNumbers.has(pageNumber + 1)) adjacentPageNumbers.add(pageNumber + 1);
  }
  return {
    fillErrorPages: pagesFor("E_PAGE_FILL_LOW"),
    overflowPages: pagesFor("E_PAGE_OVERFLOW"),
    adjacentPages: [...adjacentPageNumbers].sort((left, right) => left - right).map((pageNumber) => pagesByNumber.get(pageNumber))
  };
}

function parseArguments(argv) {
  const options = { input: "", output: "", endcard: "", json: false, debug: false };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--output" || value === "-o") {
      options.output = argv[index + 1] || "";
      index += 1;
    } else if (value === "--endcard") {
      options.endcard = argv[index + 1] || "";
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

async function render(inputPath, outputDirectory, endcardVariant = "", coverOnly = false, debug = false) {
  const endcard = resolveEndcardVariant(endcardVariant);
  const renderedOutputDirectory = debug ? debugOutputDirectoryFor(outputDirectory) : outputDirectory;
  const debugOutputDirectory = debugOutputDirectoryFor(outputDirectory);
  const debugAction = debug
    ? `Inspect the diagnostic PNGs in "${renderedOutputDirectory}", including the failing page and adjacent pages.`
    : `Run the same render command with --debug; diagnostic PNGs will be written to "${debugOutputDirectory}" without replacing formal output.`;
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
      fs.readFile(path.join(SKILL_DIR, "assets/li-feite-avatar.png")),
      qrAssetPathFor(endcard) ? fs.readFile(qrAssetPathFor(endcard)) : Promise.resolve(null)
    ]);
  } catch (error) {
    throw diagnosticError("E_RENDER_DEPENDENCY", "A renderer dependency or bundled asset could not be loaded.", {
      actual: error.message,
      action: "Run preflight.py. Restore missing assets or install the reported dependency, then rerun render.mjs."
    });
  }
  const [css, coverScript, endcardScript, runtimeScript, playwright, authorAvatarBytes, qrBytes] = assets;
  document.meta.authorAvatar = `data:image/png;base64,${authorAvatarBytes.toString("base64")}`;
  if (qrBytes) document.meta.brandQr = `data:image/png;base64,${qrBytes.toString("base64")}`;
  document.meta.endcard = endcard;

  const stagingDirectory = await createStagingDirectory(renderedOutputDirectory);
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
      deviceScaleFactor: RENDER_SCALE
    });
    await page.setContent(buildHtml(document, css, [coverScript, endcardScript, runtimeScript]), { waitUntil: "load" });
    await page.waitForFunction(() => ["true", "error"].includes(document.body.dataset.renderReady));
    const fontReport = await page.evaluate(() => window.__fontReport || null);
    if (!fontReport?.ok) {
      throw diagnosticError("E_FONT_LOAD", "The required Source Han font faces are not installed or could not be loaded.", {
        actual: (fontReport?.missingFonts || []).map((font) => font.source).join(", ") || "Font loader did not return a success report",
        expected: "Source Han Sans SC and Source Han Serif SC with Regular, Medium/SemiBold, Bold, and Heavy faces",
        action: "Install the official Source Han Sans SC and Source Han Serif SC font families, restart the browser process, and rerun render.mjs."
      });
    }
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
        action: `Shorten the oversized unbreakable block; use a page break only between complete ideas. ${debugAction}`
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
        action: `Rebalance nearby source-grounded content; if it is a trailing near-empty page, trim earlier content. ${debugAction} ${FILL_ALGO_NOTE}`
      })));
    }

    // 页数范围检查（--cover-only 跳过）：正文页数 = fillRatios 条数（封面与导流页不计入）。
    const bodyPages = (report.fillRatios || []).length;
    renderErrors.push(...buildBodyPageCountDiagnostics(bodyPages, report.pageCount, { coverOnly, debugAction }));
    if (renderErrors.length && !debug) throw diagnosticsError(renderErrors);

    const cards = page.locator(".page-card");
    const count = await cards.count();
    const files = [];
    for (let index = 0; index < count; index += 1) {
      const kind = await cards.nth(index).getAttribute("data-kind");
      if (coverOnly && kind !== "cover") continue;
      const fileName = `${String(index + 1).padStart(2, "0")}-${kind === "cover" ? "cover" : "page"}.png`;
      const supersampled = await cards.nth(index).screenshot({ type: "png", scale: "device" });
      const delivered = await downsampleScreenshot(supersampled);
      await fs.writeFile(path.join(stagingDirectory, fileName), delivered);
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
      endcard,
      coverOnly,
      mode: debug ? "debug" : "formal",
      deliveryReady: !debug && !coverOnly,
      pages: files.length,
      bodyPages: pageDetails.filter((detail) => detail.kind === "body").length,
      totalPages: files.length,
      width: PAGE_WIDTH,
      height: PAGE_HEIGHT,
      renderScale: RENDER_SCALE,
      renderWidth: RENDER_WIDTH,
      renderHeight: RENDER_HEIGHT,
      resizeKernel: "lanczos3",
      fonts: {
        sans: "Source Han Sans SC",
        serif: "Source Han Serif SC",
        loadedFaces: fontReport.loadedFonts
      },
      files,
      pageDetails,
      auditTargets: buildAuditTargets(pageDetails),
      ...(debug ? { debugTargets: buildDebugTargets(pageDetails, renderErrors) } : {}),
      fillRatios: report.fillRatios || [],
      warnings: validation.warnings,
      blockingDiagnostics: debug ? renderErrors : []
    };
    await fs.writeFile(path.join(stagingDirectory, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
    await browser.close();
    browser = null;
    await commitOwnedOutputs(stagingDirectory, renderedOutputDirectory);
    return manifest;
  } finally {
    if (browser) await browser.close();
    await discardStagingDirectory(stagingDirectory);
  }
}

async function main() {
  const options = parseArguments(process.argv.slice(2));
  if (options.help) {
    process.stdout.write("Usage: node render.mjs <input.md> --output <output-dir> [--endcard native|guided] [--cover-only] [--debug] [--json]\n");
    return;
  }
  if (!options.input || !options.output) {
    throw new Error("Usage: node render.mjs <input.md> --output <output-dir>");
  }
  const inputPath = path.resolve(options.input);
  const outputDirectory = path.resolve(options.output);
  const renderedOutputDirectory = options.debug ? debugOutputDirectoryFor(outputDirectory) : outputDirectory;
  const manifest = await render(inputPath, outputDirectory, options.endcard, options.coverOnly, options.debug);
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
