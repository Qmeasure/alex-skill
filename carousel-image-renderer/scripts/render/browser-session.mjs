import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { browserLaunchOptions, loadPlaywright } from "../browser.mjs";
import { diagnosticError } from "../diagnostics.mjs";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = path.resolve(SCRIPT_DIR, "../..");

export function qrAssetPathFor(endcard) {
  return endcard === "guided" ? path.join(SKILL_DIR, "assets/zhifujie-qr.png") : null;
}

export async function loadBrowserResources(document, { style, endcard }) {
  let assets;
  try {
    assets = await Promise.all([
      fs.readFile(path.join(SKILL_DIR, "assets/theme.css"), "utf8"),
      style === "new" ? fs.readFile(path.join(SKILL_DIR, "assets/theme-new.css"), "utf8") : Promise.resolve(""),
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

  const [baseCss, styleCss, coverScript, endcardScript, runtimeScript, playwright, authorAvatarBytes, qrBytes] = assets;
  document.meta.authorAvatar = `data:image/png;base64,${authorAvatarBytes.toString("base64")}`;
  if (qrBytes) document.meta.brandQr = `data:image/png;base64,${qrBytes.toString("base64")}`;
  document.meta.endcard = endcard;
  return {
    css: styleCss ? `${baseCss}\n${styleCss}` : baseCss,
    runtimeScripts: [coverScript, endcardScript, runtimeScript],
    playwright
  };
}

function buildHtml(document, css, runtimeScripts, pageWidth) {
  const payload = JSON.stringify(document).replace(/</g, "\\u003c").replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
  const scriptTags = runtimeScripts.map((source) => `<script>${source}</script>`).join("\n");
  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=${pageWidth}, initial-scale=1">
  <style>${css}</style>
</head>
<body>
  <main class="carousel" id="carousel"></main>
  <script>window.__CAROUSEL_DATA__ = ${payload};</script>
  ${scriptTags}
</body>
</html>`;
}

export async function withBrowserSession({ document, resources, dimensions }, task) {
  let browser;
  try {
    try {
      browser = await resources.playwright.chromium.launch({ ...(await browserLaunchOptions()), timeout: 15000 });
    } catch (error) {
      throw diagnosticError("E_BROWSER_LAUNCH", "Chromium could not be launched for rendering.", {
        actual: error.message,
        action: "Run preflight.py and repair the reported browser installation or PLAYWRIGHT_CHROMIUM_EXECUTABLE path."
      });
    }
    const page = await browser.newPage({
      viewport: { width: dimensions.pageWidth, height: dimensions.pageHeight },
      deviceScaleFactor: dimensions.renderScale
    });
    await page.setContent(buildHtml(document, resources.css, resources.runtimeScripts, dimensions.pageWidth), { waitUntil: "load" });
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
    const result = await task({ page, fontReport, report });
    await browser.close();
    browser = null;
    return result;
  } finally {
    if (browser) await browser.close();
  }
}
