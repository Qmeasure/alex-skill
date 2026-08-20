import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import * as parser from "../scripts/parser.mjs";

const {
  normalizeDestination,
  parseDocument,
  plainText,
  safeUrl,
  validateDocument
} = parser;

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

test("parser facade preserves representative AST and sanitization contracts", () => {
  assert.deepEqual(Object.keys(parser), [
    "normalizeDestination",
    "parseDocument",
    "plainText",
    "safeUrl",
    "validateDocument"
  ]);
  assert.equal(normalizeDestination(" <./chart.png> "), "./chart.png");
  assert.equal(safeUrl("javascript:alert(1)"), "");
  assert.equal(safeUrl("data:text/html,unsafe", "image"), "");
  assert.equal(safeUrl("data:image/png;base64,AA", "image"), "data:image/png;base64,AA");
  assert.equal(plainText("**标题** [链接](https://example.com) {accent}值{/accent} <b>粗</b>"), "标题 链接 值 粗");

  const document = parseDocument(`---
title: 组合契约
---

<span data-x="1">允许</span><script>拒绝</script>

- 一级
  - 二级

| 指标 | 值 |
| --- | ---: |
| 收入 | **2** |

![图](<data:image/png;base64,AA> "标题")

[^note]: 脚注
`);

  assert.deepEqual(document.blocks.map((block) => block.type), ["paragraph", "list", "table", "image", "footnotes"]);
  assert.deepEqual(document.blocks.map((block) => block.line), [5, 7, 10, 14, 16]);
  assert.equal(document.blocks[0].html, "<span>允许</span>&lt;script&gt;拒绝&lt;/script&gt;");
  assert.equal(document.blocks[1].items[0].children[0].items[0].raw, "二级");
  assert.deepEqual(document.blocks[2].alignments, ["left", "right"]);
  assert.equal(document.blocks[2].rows[0][1].html, "<strong>2</strong>");
  assert.deepEqual(
    { alt: document.blocks[3].alt, src: document.blocks[3].src, title: document.blocks[3].title },
    { alt: "图", src: "data:image/png;base64,AA", title: "标题" }
  );
  assert.equal(document.blocks[4].items[0].html, "脚注");
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

test("section rejects nested Markdown headings without blocking literal hash text", () => {
  const base = `---
title: Section 语法测试
---

:::section
SECTION_TITLE
:::

:::callout
行业变化可能带来结构性机会。
:::

:::risk
需求波动可能压低价格。
:::

:::thumbnails
![](./page-01.png)
:::
`;
  const invalid = base.replace("SECTION_TITLE", "## 成本曲线开始变化");
  const error = validateDocument(parseDocument(invalid)).errors.find((item) => item.code === "E_SECTION_MARKDOWN_HEADING");
  assert.equal(error?.line, 6);
  assert.equal(error?.actual, "## 成本曲线开始变化");
  assert.match(error?.action || "", /Remove the leading #/);

  const valid = base.replace("SECTION_TITLE", "C#生态的成本曲线开始变化");
  assert.equal(errorCodes(valid).includes("E_SECTION_MARKDOWN_HEADING"), false);
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

test("forbidden body terms cover visible prose and skip non-prose fields", () => {
  for (const { term, code } of [
    { term: "你", code: "E_BODY_SECOND_PERSON" },
    { term: "本文", code: "E_BODY_META_REFERENCE" }
  ]) {
    const source = `---
title: 明确标题
---

${term}出现在正文。

![${term}图](./chart.png)

- 第一层
  - ${term}嵌套项

\`\`\`text
${term}
\`\`\`

![](./${term}.png)

:::callout
行业变化可能带来结构性机会。
:::

:::risk
存在波动风险。
:::

:::thumbnails
![](./${term}.png)
:::
`;
    const errors = validateDocument(parseDocument(source)).errors.filter((item) => item.code === code);
    assert.deepEqual(errors.map((item) => item.line), [5, 7, 9], `${term} should only be reported from visible prose`);
    assert.ok(errors.every((item) => item.actual === `${term} × 1`));
  }
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
