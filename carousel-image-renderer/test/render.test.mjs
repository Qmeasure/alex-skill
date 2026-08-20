import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { qrAssetPathFor } from "../scripts/render/browser-session.mjs";
import { buildBodyPageCountDiagnostics } from "../scripts/render/layout.mjs";
import { commitOwnedOutputs, createStagingDirectory } from "../scripts/render/output.mjs";

function runNode(args, cwd) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, args, { cwd, shell: false, windowsHide: true });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", reject);
    child.on("close", (code) => resolve({ code, stdout, stderr }));
  });
}

test("body-page limits accept the inclusive range and reject both boundaries", () => {
  assert.equal(buildBodyPageCountDiagnostics(6, 8)[0]?.code, "E_BODY_PAGES_MIN");
  assert.deepEqual(buildBodyPageCountDiagnostics(7, 9), []);
  assert.deepEqual(buildBodyPageCountDiagnostics(16, 18), []);
  const maximum = buildBodyPageCountDiagnostics(17, 19);
  assert.equal(maximum[0]?.code, "E_BODY_PAGES_MAX");
  assert.match(maximum[0]?.expected || "", /At most 16 body pages, 18 total pages/);
  assert.deepEqual(buildBodyPageCountDiagnostics(0, 1, { coverOnly: true }), []);
});

test("native and guided endcards preserve the same brand introduction", async () => {
  const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const source = await fs.readFile(path.join(projectRoot, "assets/endcard.js"), "utf8");
  assert.match(
    source,
    /const __BRAND_INTRO = "智富界是一个聚焦AI产业、创业与投资的研究社群，帮助企业及用户看懂AI、用好AI、投资AI。";/
  );
  assert.equal(source.match(/intro: __BRAND_INTRO/g)?.length, 2);
  assert.match(source, /introBreakAfter: "研究社群，"/);
  assert.match(source, /guide: "关注视频号 · 主页查看更多内容"/);
});

test("fixed author identity uses the bundled square avatar", async () => {
  const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const runtime = await fs.readFile(path.join(projectRoot, "assets/runtime.js"), "utf8");
  const avatar = await fs.readFile(path.join(projectRoot, "assets/li-feite-avatar.png"));
  const width = avatar.readUInt32BE(16);
  const height = avatar.readUInt32BE(20);
  assert.match(runtime, /const AUTHOR_NAME = "李菲特";/);
  assert.match(runtime, /avatar\.alt = `\$\{AUTHOR_NAME\}头像`;/);
  assert.equal(width, height);
  assert.ok(width >= 512);
});

test("callout and risk labels are fixed by the renderer", async () => {
  const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const runtime = await fs.readFile(path.join(projectRoot, "assets/runtime.js"), "utf8");
  assert.match(runtime, /const CALLOUT_LABEL = "AI观点：";/);
  assert.match(runtime, /const RISK_LABEL = "AI提示风险：";/);
  assert.doesNotMatch(runtime, /callout_label/);
});

test("old and new styles keep their fixed palette contracts", async () => {
  const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const oldCss = await fs.readFile(path.join(projectRoot, "assets/theme.css"), "utf8");
  const newCss = await fs.readFile(path.join(projectRoot, "assets/theme-new.css"), "utf8");
  const runtime = await fs.readFile(path.join(projectRoot, "assets/runtime.js"), "utf8");
  const renderer = await fs.readFile(path.join(projectRoot, "scripts/render.mjs"), "utf8");
  assert.match(oldCss, /--accent:\s*#185fa9;/i);
  assert.match(oldCss, /--body-strong-ink:\s*#006aef;/i);
  assert.match(oldCss, /\.metric-value\s*\{[^}]*color:\s*var\(--accent\);/is);
  assert.match(oldCss, /\.callout-label\s*\{[^}]*color:\s*var\(--accent\);/is);
  assert.match(oldCss, /\.risk-block\s*\{[^}]*border-left:\s*5px solid var\(--accent\);/is);
  assert.match(oldCss, /\.risk-label\s*\{[^}]*color:\s*var\(--accent\);/is);
  assert.match(newCss, /--accent:\s*#9fe600;/i);
  assert.match(newCss, /--accent-deep:\s*#416500;/i);
  assert.match(newCss, /\.metric-value\s*\{[^}]*color:\s*var\(--accent-deep\);[^}]*font-size:\s*var\(--body-font-size\);/is);
  assert.match(newCss, /\.body-paragraph strong[\s\S]*?color:\s*var\(--accent-deep\);/i);
  assert.match(newCss, /\.callout-block,\s*\.risk-block\s*\{[^}]*background:\s*linear-gradient\(135deg,\s*#070907/is);
  assert.match(newCss, /\.brand-card-title,\s*\.brand-card-guide\s*\{[^}]*color:\s*var\(--accent\);/is);
  assert.match(newCss, /\.cover-page\s*\{[^}]*box-shadow:\s*inset 0 10px 0 var\(--accent\);/is);
  assert.doesNotMatch(`${oldCss}\n${newCss}`, /--gold|--warm-red|data-theme/i);
  assert.doesNotMatch(`${oldCss}\n${newCss}`, /#ba8d32|#9c701c|#d5ad59|#ff8a68|rgba\(210,\s*90,\s*50/i);
  assert.doesNotMatch(runtime, /dataset\.theme/);
  assert.doesNotMatch(renderer, /--theme/);
});

test("unsupported render styles are rejected with a stable diagnostic", async () => {
  const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const result = await runNode([
    "scripts/render.mjs",
    "missing.md",
    "--output",
    "unused",
    "--style",
    "lime",
    "--json"
  ], projectRoot);
  assert.equal(result.code, 1, result.stderr || result.stdout);
  assert.equal(JSON.parse(result.stdout).errors[0]?.code, "E_STYLE_UNSUPPORTED");
});

test("endcard variants keep native QR-free, guided QR, and legacy rejection contracts", async () => {
  assert.equal(qrAssetPathFor("native"), null);
  assert.match(qrAssetPathFor("guided"), /zhifujie-qr\.png$/);
  const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const result = await runNode([
    "scripts/render.mjs",
    "missing.md",
    "--output",
    "unused",
    "--endcard",
    "legacy",
    "--json"
  ], projectRoot);
  assert.equal(result.code, 1, result.stderr || result.stdout);
  assert.equal(JSON.parse(result.stdout).errors[0]?.code, "E_ENDCARD_UNSUPPORTED");
});

test("output transaction replaces only owned files and rejects incomplete staging", async (context) => {
  const workspace = await fs.mkdtemp(path.join(os.tmpdir(), "carousel-output-transaction-"));
  context.after(() => fs.rm(workspace, { recursive: true, force: true }));
  const outputDirectory = path.join(workspace, "视频图");
  await fs.mkdir(outputDirectory, { recursive: true });
  await fs.writeFile(path.join(outputDirectory, "01-cover.png"), "old-cover", "utf8");
  await fs.writeFile(path.join(outputDirectory, "02-page.png"), "old-page", "utf8");
  await fs.writeFile(path.join(outputDirectory, "manifest.json"), "old-manifest", "utf8");
  await fs.writeFile(path.join(outputDirectory, "notes.txt"), "keep-me", "utf8");

  const completeStaging = await createStagingDirectory(outputDirectory);
  await fs.writeFile(path.join(completeStaging, "01-cover.png"), "new-cover", "utf8");
  await fs.writeFile(path.join(completeStaging, "manifest.json"), "new-manifest", "utf8");
  await commitOwnedOutputs(completeStaging, outputDirectory);
  assert.equal(await fs.readFile(path.join(outputDirectory, "01-cover.png"), "utf8"), "new-cover");
  assert.equal(await fs.readFile(path.join(outputDirectory, "manifest.json"), "utf8"), "new-manifest");
  await assert.rejects(fs.access(path.join(outputDirectory, "02-page.png")));
  assert.equal(await fs.readFile(path.join(outputDirectory, "notes.txt"), "utf8"), "keep-me");

  const incompleteStaging = await createStagingDirectory(outputDirectory);
  await fs.writeFile(path.join(incompleteStaging, "01-cover.png"), "incomplete-cover", "utf8");
  await assert.rejects(
    commitOwnedOutputs(incompleteStaging, outputDirectory),
    /Staged render has no manifest\.json/
  );
  assert.equal(await fs.readFile(path.join(outputDirectory, "01-cover.png"), "utf8"), "new-cover");
  assert.equal(await fs.readFile(path.join(outputDirectory, "manifest.json"), "utf8"), "new-manifest");
  assert.equal(await fs.readFile(path.join(outputDirectory, "notes.txt"), "utf8"), "keep-me");
});

test("debug render exposes blocking layout pages without replacing formal output", { timeout: 60000 }, async (context) => {
  const workspace = await fs.mkdtemp(path.join(os.tmpdir(), "carousel-render-transaction-"));
  context.after(() => fs.rm(workspace, { recursive: true, force: true }));
  const inputPath = path.join(workspace, "input.md");
  const outputDirectory = path.join(workspace, "视频图");
  await fs.mkdir(outputDirectory, { recursive: true });
  await fs.writeFile(path.join(outputDirectory, "01-cover.png"), "previous-image", "utf8");
  await fs.writeFile(path.join(outputDirectory, "manifest.json"), "{\"previous\":true}\n", "utf8");
  await fs.writeFile(inputPath, `---
title: 事务输出测试
---

第一页内容很短，包含 ![示意图](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAEAQH/XPWsWQAAAABJRU5ErkJggg==)。

:::pagebreak

:::methodology-3x4

AI 基建对应当前场景，主体对应投资龙头。

:::pagebreak

第三页内容很短。

:::pagebreak

第四页内容很短。

:::pagebreak

第五页内容很短。

:::pagebreak

第六页内容很短。

:::pagebreak

第七页是自然结束的末页。

:::callout
样本仍可用于观察页面诊断行为。
:::

:::risk
样本过短，结论可能失真。
:::

:::thumbnails
![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAEAQH/XPWsWQAAAABJRU5ErkJggg==)
:::
`, "utf8");

  const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const result = await runNode(["scripts/render.mjs", inputPath, "--output", outputDirectory, "--json"], projectRoot);
  assert.equal(result.code, 1, result.stderr || result.stdout);
  const response = JSON.parse(result.stdout);
  assert.equal(response.errors[0].code, "E_PAGE_FILL_LOW");
  assert.match(response.errors[0].action, /--debug/);
  assert.equal(await fs.readFile(path.join(outputDirectory, "01-cover.png"), "utf8"), "previous-image");
  assert.deepEqual(JSON.parse(await fs.readFile(path.join(outputDirectory, "manifest.json"), "utf8")), { previous: true });

  const debugResult = await runNode(["scripts/render.mjs", inputPath, "--output", outputDirectory, "--debug", "--json"], projectRoot);
  assert.equal(debugResult.code, 0, debugResult.stderr || debugResult.stdout);
  const debugResponse = JSON.parse(debugResult.stdout);
  const debugDirectory = `${outputDirectory}.debug`;
  assert.equal(debugResponse.outputDirectory, debugDirectory);
  assert.equal(debugResponse.manifest.style, "new");
  assert.equal(debugResponse.manifest.mode, "debug");
  assert.equal(debugResponse.manifest.deliveryReady, false);
  assert.ok(debugResponse.manifest.blockingDiagnostics.some((item) => item.code === "E_PAGE_FILL_LOW"));
  assert.ok(debugResponse.manifest.debugTargets.fillErrorPages.length > 0);
  const firstBody = debugResponse.manifest.pageDetails.find((page) => page.kind === "body");
  const methodologyPage = debugResponse.manifest.pageDetails.find((page) => page.features.includes("methodology-3x4"));
  assert.match(firstBody.text, /第一页内容很短/);
  assert.ok(firstBody.features.includes("image"));
  assert.ok(firstBody.visualRegions.some((region) => region.kind === "content-image" && region.width > 0 && region.height > 0));
  assert.match(methodologyPage?.text || "", /3×4 是智富界提出的一种分析投资机会的框架/);
  assert.match(methodologyPage?.text || "", /AI 基建[\s\S]*生成式大模型[\s\S]*AI 硬件/);
  assert.match(methodologyPage?.text || "", /挑战龙头[\s\S]*加入龙头[\s\S]*成为龙头的代理或生态伙伴[\s\S]*投资龙头/);
  assert.doesNotMatch(methodologyPage?.text || "", /商业模式|十二格/);
  await fs.access(path.join(debugDirectory, debugResponse.manifest.debugTargets.fillErrorPages[0]));
  assert.equal(await fs.readFile(path.join(outputDirectory, "01-cover.png"), "utf8"), "previous-image");
  assert.deepEqual(JSON.parse(await fs.readFile(path.join(outputDirectory, "manifest.json"), "utf8")), { previous: true });
});

test("cover render loads required fonts and downsamples 2x output to delivery size", { timeout: 60000 }, async (context) => {
  const workspace = await fs.mkdtemp(path.join(os.tmpdir(), "carousel-render-contract-"));
  context.after(() => fs.rm(workspace, { recursive: true, force: true }));
  const inputPath = path.join(workspace, "input.md");
  const outputDirectory = path.join(workspace, "视频图");
  const oldOutputDirectory = path.join(workspace, "视频图-old");
  await fs.writeFile(inputPath, `---
title: AI投资叙事
subtitle: 用清晰的字体层级讲明白产业变化
kicker: 字体与清晰度测试
---

正文用于满足格式要求。

:::callout
清晰层级有助于传递投资叙事。
:::

:::risk
样例内容不构成投资建议。
:::

:::thumbnails
![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAEAQH/XPWsWQAAAABJRU5ErkJggg==)
:::
`, "utf8");

  const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const result = await runNode(["scripts/render.mjs", inputPath, "--output", outputDirectory, "--cover-only", "--json"], projectRoot);
  assert.equal(result.code, 0, result.stderr || result.stdout);
  const response = JSON.parse(result.stdout);
  assert.equal(response.manifest.endcard, "native");
  assert.equal(response.manifest.style, "new");
  assert.equal(response.manifest.renderScale, 2);
  assert.deepEqual(
    [response.manifest.renderWidth, response.manifest.renderHeight, response.manifest.width, response.manifest.height],
    [2160, 2880, 1080, 1440]
  );
  assert.equal(response.manifest.fonts.sans, "Source Han Sans SC");
  assert.equal(response.manifest.fonts.serif, "Source Han Serif SC");
  assert.equal(response.manifest.fonts.loadedFaces.length, 8);
  assert.match(response.manifest.pageDetails[0].text, /字体与清晰度测试\nAI投资叙事\n用清晰的字体层级讲明白产业变化/);
  assert.doesNotMatch(response.manifest.pageDetails[0].text, /李菲特|智富界/);
  assert.deepEqual(response.manifest.pageDetails[0].visualRegions.map((region) => region.kind), ["cover-content"]);

  const png = await fs.readFile(path.join(outputDirectory, "01-cover.png"));
  assert.deepEqual([png.readUInt32BE(16), png.readUInt32BE(20)], [1080, 1440]);

  const oldResult = await runNode([
    "scripts/render.mjs",
    inputPath,
    "--output",
    oldOutputDirectory,
    "--style",
    "old",
    "--cover-only",
    "--json"
  ], projectRoot);
  assert.equal(oldResult.code, 0, oldResult.stderr || oldResult.stdout);
  const oldResponse = JSON.parse(oldResult.stdout);
  assert.equal(oldResponse.manifest.style, "old");
  const oldPng = await fs.readFile(path.join(oldOutputDirectory, "01-cover.png"));
  assert.notEqual(Buffer.compare(png, oldPng), 0);
});
