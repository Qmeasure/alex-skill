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
