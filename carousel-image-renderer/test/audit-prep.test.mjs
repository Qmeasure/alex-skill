import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
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

:::thumbnails
![来源一](../信源/a.png)
:::
`, "utf8");

  const pageDetails = [
    { page: 1, kind: "cover", label: "cover", features: [], file: "01-cover.png" },
    { page: 2, kind: "body", label: "section", features: ["callout"], file: "02-page.png", fill: 0.8 },
    { page: 3, kind: "endcard", label: "endcard", features: [], file: "03-page.png" }
  ];
  await writeJson(path.join(renderDirectory, "manifest.json"), {
    title: "审计样稿",
    mode: "formal",
    deliveryReady: true,
    pages: 3,
    bodyPages: 1,
    files: pageDetails.map((page) => page.file),
    pageDetails,
    auditTargets: {
      cover: "01-cover.png",
      densestBody: "02-page.png",
      calloutPages: ["02-page.png"],
      riskPages: [],
      fillWarningPages: [],
      endcard: "03-page.png"
    }
  });
  await writeJson(path.join(renderDirectory, "source-manifest.json"), {
    status: "ready",
    inkstoneInputs: [path.join(workspace, "信源", "a.pdf"), path.join(workspace, "信源", "b.html")]
  });
  await Promise.all([
    fs.writeFile(path.join(renderDirectory, "01-cover.png"), "cover"),
    fs.writeFile(path.join(renderDirectory, "02-page.png"), "body"),
    fs.writeFile(path.join(renderDirectory, "03-page.png"), "endcard"),
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
  assert.deepEqual(contextFiles, ["AUDIT.md", "article.md", "manifest.json", "pages"]);
  assert.deepEqual(evidenceFiles, ["AUDIT.md", "article.md", "manifest.json", "pages", "sources", "web-research.md"]);

  const article = await fs.readFile(path.join(result.contextDirectory, "article.md"), "utf8");
  assert.doesNotMatch(article, /source_pages|:::thumbnails|来源一/);
  assert.deepEqual((await fs.readdir(path.join(result.contextDirectory, "pages"))).sort(), ["01-cover.png", "02-page.png"]);
  assert.deepEqual((await fs.readdir(path.join(result.evidenceDirectory, "sources"))).sort(), ["01.md", "02.md", "index.json"]);

  const auditManifest = JSON.parse(await fs.readFile(path.join(result.evidenceDirectory, "manifest.json"), "utf8"));
  assert.deepEqual(Object.keys(auditManifest), ["title", "mode", "deliveryReady", "pages", "bodyPages", "files", "pageDetails", "auditTargets"]);
  assert.deepEqual(auditManifest.files, ["01-cover.png", "02-page.png"]);
  assert.equal(auditManifest.pageDetails.some((page) => page.kind === "endcard"), false);
  assert.equal(Object.hasOwn(auditManifest.auditTargets, "endcard"), false);
  const sourceIndex = JSON.parse(await fs.readFile(path.join(result.evidenceDirectory, "sources", "index.json"), "utf8"));
  assert.deepEqual(sourceIndex, [{ input: "a.pdf", result: "01.md" }, { input: "b.html", result: "02.md" }]);
  assert.equal(result.pages, 2);
  assert.equal(result.sources, 2);
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
