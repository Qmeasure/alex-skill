import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { buildAuditTargets } from "../scripts/render.mjs";

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

test("failed render returns a stable code and preserves previous owned output", { timeout: 60000 }, async (context) => {
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

正文只有一页，因此正式渲染必须失败。

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
  assert.equal(response.errors[0].code, "E_BODY_PAGES_MIN");
  assert.equal(await fs.readFile(path.join(outputDirectory, "01-cover.png"), "utf8"), "previous-image");
  assert.deepEqual(JSON.parse(await fs.readFile(path.join(outputDirectory, "manifest.json"), "utf8")), { previous: true });
});
