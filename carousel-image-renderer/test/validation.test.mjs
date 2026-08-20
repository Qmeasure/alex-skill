import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { parseDocument, validateDocument } from "../scripts/parser.mjs";

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

function errorCodes(source) {
  return validateDocument(parseDocument(source)).errors.map((item) => item.code);
}

test("hard requirements return stable error codes together", () => {
  const codes = errorCodes("# 旧版回退标题\n\n这段正文里有你。\n");
  assert.deepEqual(codes, [
    "E_TITLE_REQUIRED",
    "E_CALLOUT_REQUIRED",
    "E_RISK_REQUIRED",
    "E_THUMBNAILS_REQUIRED",
    "E_BODY_SECOND_PERSON"
  ]);
});

test("valid title, callout, risk, and final thumbnails pass hard validation", () => {
  const source = `---
title: 明确标题
---

市场变化会影响企业成本。

:::callout
成本变化可能重塑企业竞争力。
:::

:::risk
价格波动可能放大短期回撤。
:::

:::thumbnails
![](./page-01.png)
:::
`;
  assert.deepEqual(errorCodes(source), []);
});

test("the fixed 3×4 directive expands deterministic copy and accepts no parameters", () => {
  const source = `---
title: 固定方法论组件
---

:::methodology-3x4

当前案例对应 AI 基建，主体对应投资龙头。

:::callout
订单变化决定需求能否持续。
:::

:::risk
新增产能可能改变价格方向。
:::

:::thumbnails
![](./page-01.png)
:::
`;
  const document = parseDocument(source);
  const methodology = document.blocks.find((block) => block.type === "methodology-3x4");
  assert.match(methodology?.raw || "", /3×4 是智富界提出的一种分析投资机会的框架/);
  assert.match(methodology?.raw || "", /AI 基建[\s\S]*生成式大模型[\s\S]*AI 硬件/);
  assert.match(methodology?.raw || "", /挑战龙头[\s\S]*投资龙头/);
  assert.doesNotMatch(methodology?.raw || "", /商业模式|十二格/);
  assert.deepEqual(validateDocument(document).errors, []);
  assert.throws(
    () => parseDocument(source.replace(":::methodology-3x4", ":::methodology-3x4 custom")),
    /does not accept parameters/
  );
});

test("3×4 references require one fixed component before the first reference", () => {
  const tail = `

:::callout
关系证据需要核验。
:::

:::risk
映射错误可能误导判断。
:::

:::thumbnails
![](./page-01.png)
:::
`;
  const withoutComponent = `---\ntitle: 缺少组件\n---\n\n3×4 对应 AI 基建。${tail}`;
  const afterReference = `---\ntitle: 顺序错误\n---\n\n3×4 对应 AI 基建。\n\n:::methodology-3x4${tail}`;
  const duplicate = `---\ntitle: 重复组件\n---\n\n:::methodology-3x4\n\n:::methodology-3x4${tail}`;
  const coverReference = `---\ntitle: 3×4 映射\n---\n\n:::methodology-3x4${tail}`;
  assert.ok(errorCodes(withoutComponent).includes("E_3X4_COMPONENT_REQUIRED"));
  assert.ok(errorCodes(afterReference).includes("E_3X4_COMPONENT_ORDER"));
  assert.ok(errorCodes(duplicate).includes("E_3X4_COMPONENT_MULTIPLE"));
  assert.ok(errorCodes(coverReference).includes("E_3X4_COVER_REFERENCE"));
});

test("the fixed brand palette rejects legacy theme metadata", () => {
  const base = `---
title: 主题测试
---

正文。

:::callout
行业变化可能带来结构性机会。
:::

:::risk
存在波动风险。
:::

:::thumbnails
![](./page-01.png)
:::
`;
  assert.equal(Object.hasOwn(parseDocument(base).meta, "theme"), false);
  for (const theme of ["finance", "tech", "classic", "editorial"]) {
    const source = base.replace("title: 主题测试", `title: 主题测试\ntheme: ${theme}`);
    assert.ok(errorCodes(source).includes("E_THEME_REMOVED"));
  }
});

test("thumbnails must be the final content block", () => {
  const source = `---
title: 明确标题
---

:::callout
行业变化可能带来结构性机会。
:::

:::risk
存在波动风险。
:::

:::thumbnails
![](./page-01.png)
:::

后面不应再有正文。
`;
  assert.ok(errorCodes(source).includes("E_THUMBNAILS_POSITION"));
});

test("second-person checks skip code, thumbnail alt text, and image paths", () => {
  const source = `---
title: 明确标题
---

\`\`\`text
你
\`\`\`

![示意图](./你.png)

:::callout
行业变化可能带来结构性机会。
:::

:::risk
存在波动风险。
:::

:::thumbnails
![](./你.png)
:::
`;
  assert.ok(!errorCodes(source).includes("E_BODY_SECOND_PERSON"));
});

test("second-person checks include rendered image captions and nested lists", () => {
  const source = `---
title: 明确标题
---

![你会看到的图](./chart.png)

- 第一层
  - 你会看到的嵌套项

:::callout
行业变化可能带来结构性机会。
:::

:::risk
存在波动风险。
:::

:::thumbnails
![](./page.png)
:::
`;
  const errors = validateDocument(parseDocument(source)).errors.filter((item) => item.code === "E_BODY_SECOND_PERSON");
  assert.equal(errors.length, 2);
});

test("body meta-reference checks reject 本文 but skip code and thumbnail paths", () => {
  const source = `---
title: 明确标题
---

本文解释行业变化。

\`\`\`text
本文
\`\`\`

![](./本文.png)

:::callout
行业变化可能带来结构性机会。
:::

:::risk
存在波动风险。
:::

:::thumbnails
![](./本文.png)
:::
`;
  const errors = validateDocument(parseDocument(source)).errors.filter((item) => item.code === "E_BODY_META_REFERENCE");
  assert.equal(errors.length, 1);
  assert.equal(errors[0].line, 5);
});

test("body meta-reference checks include rendered image captions and nested lists", () => {
  const source = `---
title: 明确标题
---

![本文数据](./chart.png)

- 第一层
  - 本文结论

:::callout
行业变化可能带来结构性机会。
:::

:::risk
存在波动风险。
:::

:::thumbnails
![](./page.png)
:::
`;
  const errors = validateDocument(parseDocument(source)).errors.filter((item) => item.code === "E_BODY_META_REFERENCE");
  assert.equal(errors.length, 2);
});

test("more than four endcard thumbnails fail with a dedicated code", () => {
  const images = [1, 2, 3, 4, 5].map((number) => `![](./page-${number}.png)`).join("\n");
  const source = `---
title: 明确标题
---

:::callout
行业变化可能带来结构性机会。
:::

:::risk
存在波动风险。
:::

:::thumbnails
${images}
:::
`;
  assert.ok(errorCodes(source).includes("E_THUMBNAILS_COUNT"));
});

test("cover cannot be disabled because total delivery requires nine pages", () => {
  const source = `---
title: 明确标题
cover: false
---

:::callout
行业变化可能带来结构性机会。
:::

:::risk
存在波动风险。
:::

:::thumbnails
![](./page.png)
:::
`;
  assert.ok(errorCodes(source).includes("E_COVER_REQUIRED"));
});

test("hard errors report absolute Markdown line numbers", () => {
  const source = `---
title: 明确标题
---

你不应出现在正文。

:::callout
行业变化可能带来结构性机会。
:::

:::risk
存在波动风险。
:::

:::thumbnails
![](./page-01.png)
:::
`;
  const error = validateDocument(parseDocument(source)).errors.find((item) => item.code === "E_BODY_SECOND_PERSON");
  assert.equal(error.line, 5);
});

test("callout label override is discarded by the parser", () => {
  const document = parseDocument(`---
title: 固定标签测试
callout_label: 自定义观点
---

:::callout
行业变化可能带来结构性机会。
:::

:::risk
需求波动可能压低价格。
:::

:::thumbnails
![](./page-01.png)
:::
`);
  assert.equal(document.meta.callout_label, undefined);
  assert.deepEqual(validateDocument(document).errors, []);
});

test("validate CLI emits all hard errors as machine-readable JSON", async (context) => {
  const workspace = await fs.mkdtemp(path.join(os.tmpdir(), "carousel-validate-cli-"));
  context.after(() => fs.rm(workspace, { recursive: true, force: true }));
  const inputPath = path.join(workspace, "invalid.md");
  await fs.writeFile(inputPath, "# 回退标题\n\n正文里有你。\n", "utf8");
  const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const result = await runNode(["scripts/validate.mjs", inputPath, "--json"], projectRoot);
  assert.equal(result.code, 1, result.stderr || result.stdout);
  const response = JSON.parse(result.stdout);
  assert.equal(response.valid, false);
  assert.deepEqual(response.errors.map((item) => item.code), [
    "E_TITLE_REQUIRED",
    "E_CALLOUT_REQUIRED",
    "E_RISK_REQUIRED",
    "E_THUMBNAILS_REQUIRED",
    "E_BODY_SECOND_PERSON"
  ]);
  assert.ok(response.errors.every((item) => item.action));
});
