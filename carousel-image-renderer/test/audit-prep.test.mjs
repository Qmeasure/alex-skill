import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import sharp from "sharp";
import test from "node:test";
import { prepareAuditPackages } from "../scripts/prepare-audit.mjs";

async function writeJson(filePath, value) {
  await fs.writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

async function createFixture({ missingSecondResult = false } = {}) {
  const workspace = await fs.mkdtemp(path.join(os.tmpdir(), "carousel-audit-"));
  const renderDirectory = path.join(workspace, "视频图");
  const resultsDirectory = path.join(renderDirectory, "inkstone-results");
  await fs.mkdir(resultsDirectory, { recursive: true });

  const inputPath = path.join(workspace, "carousel.md");
  await fs.writeFile(inputPath, `---
title: 审计样稿
source_pages: 2
---

# 封面

正文内容。

:::methodology-3x4

:::thumbnails
![来源一](../信源/a.png)
:::
`, "utf8");

  const pageDetails = [
    { page: 1, kind: "cover", label: "cover", features: [], file: "01-cover.png", text: "封面标签\n审计样稿\n封面副标题", visualRegions: [{ kind: "cover-content", x: 1, y: 1, width: 8, height: 5 }] },
    { page: 2, kind: "body", label: "3×4 是什么", features: ["callout", "risk", "methodology-3x4"], file: "02-page.png", fill: 0.8, text: "3×4 是什么\n第一段正文", visualRegions: [] },
    { page: 3, kind: "body", label: "image", features: ["image"], file: "03-page.png", fill: 0.82, text: "带内容图片的正文", visualRegions: [{ kind: "content-image", x: 2, y: 2, width: 4, height: 4 }] },
    { page: 4, kind: "endcard", label: "endcard", features: [], file: "04-page.png", text: "末页文字", visualRegions: [] }
  ];
  await writeJson(path.join(renderDirectory, "manifest.json"), {
    title: "审计样稿",
    mode: "formal",
    deliveryReady: true,
    pages: 4,
    bodyPages: 2,
    width: 10,
    height: 10,
    files: pageDetails.map((page) => page.file),
    pageDetails
  });
  await writeJson(path.join(renderDirectory, "source-manifest.json"), {
    status: "ready",
    inkstoneInputs: [path.join(workspace, "信源", "a.pdf"), path.join(workspace, "信源", "b.html")]
  });
  const pagePng = await sharp({ create: { width: 10, height: 10, channels: 4, background: "#ffffff" } }).png().toBuffer();
  await Promise.all([
    fs.writeFile(path.join(renderDirectory, "01-cover.png"), pagePng),
    fs.writeFile(path.join(renderDirectory, "02-page.png"), pagePng),
    fs.writeFile(path.join(renderDirectory, "03-page.png"), pagePng),
    fs.writeFile(path.join(renderDirectory, "04-page.png"), pagePng),
    fs.writeFile(path.join(resultsDirectory, "01.md"), "# 来源一\n", "utf8"),
    fs.writeFile(path.join(renderDirectory, "web-research.md"), "# 外部资料\n", "utf8"),
    ...(missingSecondResult ? [] : [fs.writeFile(path.join(resultsDirectory, "02.md"), "# 来源二\n", "utf8")])
  ]);
  return { workspace, inputPath };
}

test("prepareAuditPackages creates two isolated, sanitized audit folders", async (t) => {
  const fixture = await createFixture();
  t.after(() => fs.rm(fixture.workspace, { recursive: true, force: true }));

  const result = await prepareAuditPackages(fixture);
  const contextFiles = (await fs.readdir(result.contextDirectory)).sort();
  const evidenceFiles = (await fs.readdir(result.evidenceDirectory)).sort();
  assert.deepEqual(contextFiles, ["AUDIT.md", "pages.md"]);
  assert.deepEqual(evidenceFiles, ["AUDIT.md", "article.md", "pages.md", "sources", "visual", "web-research.md"]);

  const article = await fs.readFile(path.join(result.evidenceDirectory, "article.md"), "utf8");
  assert.doesNotMatch(article, /source_pages|:::thumbnails|来源一/);
  const pages = await fs.readFile(path.join(result.contextDirectory, "pages.md"), "utf8");
  assert.match(pages, /第 1 页｜封面[\s\S]*封面标签[\s\S]*第 2 页｜正文[\s\S]*第一段正文[\s\S]*第 3 页｜正文[\s\S]*带内容图片的正文/);
  assert.doesNotMatch(pages, /末页文字|第 4 页/);
  const contextAudit = await fs.readFile(path.join(result.contextDirectory, "AUDIT.md"), "utf8");
  const evidenceAudit = await fs.readFile(path.join(result.evidenceDirectory, "AUDIT.md"), "utf8");
  assert.match(contextAudit, /第 2 页包含渲染器生成的 `methodology-3x4` 固定组件/);
  assert.match(evidenceAudit, /第 2 页包含渲染器生成的 `methodology-3x4` 固定组件/);
  assert.match(contextAudit, /不得审查、改写或要求补充审计包标记的固定组件文案/);
  assert.match(evidenceAudit, /不核验或改写审计包标记的固定组件文案/);
  assert.match(contextAudit, /内部来源容器/);
  assert.match(contextAudit, /`BLOCKER`/);
  assert.match(contextAudit, /无事实增量的证据免责声明/);
  assert.deepEqual((await fs.readdir(path.join(result.evidenceDirectory, "visual"))).sort(), ["01-cover-content.png", "03-image-01.png"]);
  assert.deepEqual(
    await sharp(path.join(result.evidenceDirectory, "visual", "01-cover-content.png")).metadata().then(({ width, height }) => [width, height]),
    [56, 53]
  );
  assert.deepEqual((await fs.readdir(path.join(result.evidenceDirectory, "sources"))).sort(), ["01.md", "02.md", "index.json"]);

  const sourceIndex = JSON.parse(await fs.readFile(path.join(result.evidenceDirectory, "sources", "index.json"), "utf8"));
  assert.deepEqual(sourceIndex, [{ input: "a.pdf", result: "01.md" }, { input: "b.html", result: "02.md" }]);
  assert.equal(result.pages, 3);
  assert.equal(result.sources, 2);
  assert.deepEqual(result.visualFiles, ["01-cover-content.png", "03-image-01.png"]);
  assert.equal(result.webResearch, true);
});

test("prepareAuditPackages preserves the last complete package when an Inkstone result is missing", async (t) => {
  const fixture = await createFixture({ missingSecondResult: true });
  t.after(() => fs.rm(fixture.workspace, { recursive: true, force: true }));
  const outputRoot = path.join(fixture.workspace, "审计包");
  await fs.mkdir(outputRoot, { recursive: true });
  await fs.writeFile(path.join(outputRoot, "sentinel.txt"), "complete", "utf8");

  await assert.rejects(prepareAuditPackages(fixture), (error) => error.diagnostic?.code === "E_AUDIT_SOURCES");
  assert.equal(await fs.readFile(path.join(outputRoot, "sentinel.txt"), "utf8"), "complete");
  assert.deepEqual((await fs.readdir(fixture.workspace)).filter((name) => name.startsWith(".audit-packages-staging-")), []);
});
