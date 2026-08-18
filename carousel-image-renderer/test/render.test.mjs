import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { buildAuditTargets, qrAssetPathFor, resolveEndcardVariant } from "../scripts/render.mjs";

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

test("audit targets identify the pages that need visual review", () => {
  const targets = buildAuditTargets([
    { file: "01-cover.png", kind: "cover", features: [] },
    { file: "02-page.png", kind: "body", fill: 0.78, lastBody: false, features: ["callout"] },
    { file: "03-page.png", kind: "body", fill: 0.92, lastBody: false, features: ["risk", "table"] },
    { file: "04-page.png", kind: "body", fill: 0.72, lastBody: false, features: [] },
    { file: "05-page.png", kind: "endcard", features: [] }
  ]);
  assert.deepEqual(targets, {
    cover: "01-cover.png",
    densestBody: "03-page.png",
    riskPages: ["03-page.png"],
    calloutPages: ["02-page.png"],
    fillWarningPages: ["04-page.png"],
    endcard: "05-page.png"
  });
});

test("default endcard is native and does not request a QR asset", () => {
  const endcard = resolveEndcardVariant();
  assert.equal(endcard, "native");
  assert.equal(qrAssetPathFor(endcard), null);
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

test("guided endcard requests the bundled QR asset", () => {
  const endcard = resolveEndcardVariant("guided");
  assert.equal(endcard, "guided");
  assert.match(qrAssetPathFor(endcard), /zhifujie-qr\.png$/);
});

test("legacy endcard is rejected with a stable diagnostic", () => {
  assert.throws(
    () => resolveEndcardVariant("legacy"),
    (error) => error?.diagnostic?.code === "E_ENDCARD_UNSUPPORTED"
  );
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

第一页内容很短。

:::pagebreak

第二页内容很短。

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
  assert.equal(debugResponse.manifest.mode, "debug");
  assert.equal(debugResponse.manifest.deliveryReady, false);
  assert.ok(debugResponse.manifest.blockingDiagnostics.some((item) => item.code === "E_PAGE_FILL_LOW"));
  assert.ok(debugResponse.manifest.debugTargets.fillErrorPages.length > 0);
  await fs.access(path.join(debugDirectory, debugResponse.manifest.debugTargets.fillErrorPages[0]));
  assert.equal(await fs.readFile(path.join(outputDirectory, "01-cover.png"), "utf8"), "previous-image");
  assert.deepEqual(JSON.parse(await fs.readFile(path.join(outputDirectory, "manifest.json"), "utf8")), { previous: true });
});

test("cover render loads required fonts and downsamples 2x output to delivery size", { timeout: 60000 }, async (context) => {
  const workspace = await fs.mkdtemp(path.join(os.tmpdir(), "carousel-render-contract-"));
  context.after(() => fs.rm(workspace, { recursive: true, force: true }));
  const inputPath = path.join(workspace, "input.md");
  const outputDirectory = path.join(workspace, "视频图");
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
  assert.equal(response.manifest.renderScale, 2);
  assert.deepEqual(
    [response.manifest.renderWidth, response.manifest.renderHeight, response.manifest.width, response.manifest.height],
    [2160, 2880, 1080, 1440]
  );
  assert.equal(response.manifest.fonts.sans, "Source Han Sans SC");
  assert.equal(response.manifest.fonts.serif, "Source Han Serif SC");
  assert.equal(response.manifest.fonts.loadedFaces.length, 8);

  const png = await fs.readFile(path.join(outputDirectory, "01-cover.png"));
  assert.deepEqual([png.readUInt32BE(16), png.readUInt32BE(20)], [1080, 1440]);
});
