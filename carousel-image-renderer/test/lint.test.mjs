import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

function runPython(args, cwd) {
  return new Promise((resolve, reject) => {
    const child = spawn("python", args, { cwd, shell: false, windowsHide: true });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", reject);
    child.on("close", (code) => resolve({ code, stdout, stderr }));
  });
}

test("lint independently catches residual mechanical style patterns", async (context) => {
  const workspace = await fs.mkdtemp(path.join(os.tmpdir(), "carousel-lint-"));
  context.after(() => fs.rm(workspace, { recursive: true, force: true }));
  const inputPath = path.join(workspace, "input.md");
  await fs.writeFile(inputPath, `---
title: Lint 测试
kicker: 深度分析
---

# 重复标题

这不是旧方案，而是新方案。

风险偏好仍在变化。
`, "utf8");

  const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const result = await runPython(["scripts/lint.py", inputPath, "--json"], projectRoot);
  assert.equal(result.code, 0, result.stderr || result.stdout);
  const response = JSON.parse(result.stdout);
  assert.equal(response.ok, true);
  assert.deepEqual(response.warnings.map((item) => item.code), [
    "W_KICKER_SUBJECTIVE",
    "W_BODY_H1",
    "W_AI_CONTRASTIVE",
    "W_RISK_OUTSIDE_BLOCK"
  ]);
  assert.equal(response.warnings[0].line, 3);
  assert.equal(response.warnings[1].line, 6);
  assert.equal(response.warnings[2].line, 8);
  assert.equal(response.warnings[3].line, 10);
});

test("lint blocks exact AI blacklist phrases outside code and thumbnails", async (context) => {
  const workspace = await fs.mkdtemp(path.join(os.tmpdir(), "carousel-lint-blacklist-"));
  context.after(() => fs.rm(workspace, { recursive: true, force: true }));
  const inputPath = path.join(workspace, "input.md");
  await fs.writeFile(inputPath, `---
title: 证据最完整的落点
---

这条线索需要重写。
这项映射需要重写。
先说清楚背景。

\`\`\`text
先说清楚
\`\`\`

:::thumbnails
![这条线索](./page.png)
:::
`, "utf8");

  const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const result = await runPython(["scripts/lint.py", inputPath, "--json"], projectRoot);
  assert.equal(result.code, 1, result.stderr || result.stdout);
  const response = JSON.parse(result.stdout);
  assert.equal(response.ok, false);
  assert.deepEqual(response.errors.map((item) => item.actual), [
    "证据最完整的落点",
    "这条线索",
    "这项映射",
    "先说清楚"
  ]);
});


test("lint reports an error for unclosed front matter", async (context) => {
  const workspace = await fs.mkdtemp(path.join(os.tmpdir(), "carousel-lint-unclosed-"));
  context.after(() => fs.rm(workspace, { recursive: true, force: true }));
  const inputPath = path.join(workspace, "input.md");
  await fs.writeFile(inputPath, `---
title: 没有收尾的 front matter

正文从这里开始。
`, "utf8");

  const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const result = await runPython(["scripts/lint.py", inputPath, "--json"], projectRoot);
  assert.equal(result.code, 1, result.stderr || result.stdout);
  const response = JSON.parse(result.stdout);
  assert.equal(response.ok, false);
  assert.deepEqual(response.errors.map((item) => item.code), ["E_FRONT_MATTER_PARSE"]);
  assert.equal(response.errors[0].line, 1);
});

test("lint reports an error for a front-matter line without a colon", async (context) => {
  const workspace = await fs.mkdtemp(path.join(os.tmpdir(), "carousel-lint-colonless-"));
  context.after(() => fs.rm(workspace, { recursive: true, force: true }));
  const inputPath = path.join(workspace, "input.md");
  await fs.writeFile(inputPath, `---
title: 正常标题
这一行没有冒号
---

正文内容。
`, "utf8");

  const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const result = await runPython(["scripts/lint.py", inputPath, "--json"], projectRoot);
  assert.equal(result.code, 1, result.stderr || result.stdout);
  const response = JSON.parse(result.stdout);
  assert.equal(response.ok, false);
  assert.deepEqual(response.errors.map((item) => item.code), ["E_FRONT_MATTER_PARSE"]);
  assert.equal(response.errors[0].line, 3);
});

test("lint accepts well-formed front matter without E_FRONT_MATTER_PARSE", async (context) => {
  const workspace = await fs.mkdtemp(path.join(os.tmpdir(), "carousel-lint-wellformed-"));
  context.after(() => fs.rm(workspace, { recursive: true, force: true }));
  const inputPath = path.join(workspace, "input.md");
  await fs.writeFile(inputPath, `---
title: 标题
subtitle: 副标题
kicker: 报道
---

正文内容。
`, "utf8");

  const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const result = await runPython(["scripts/lint.py", inputPath, "--json"], projectRoot);
  assert.equal(result.code, 0, result.stderr || result.stdout);
  const response = JSON.parse(result.stdout);
  assert.equal(response.ok, true);
  assert.deepEqual(response.errors, []);
  assert.equal(response.warnings.filter((item) => item.code === "E_FRONT_MATTER_PARSE").length, 0);
});
