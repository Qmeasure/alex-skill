// 渲染环境：Playwright 模块定位、浏览器启动选项、输出目录清理。

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = path.resolve(SCRIPT_DIR, "..");

export async function loadPlaywright() {
  try {
    return await import("playwright");
  } catch (initialError) {
    const candidates = [
      process.env.PLAYWRIGHT_MODULE,
      process.env.CODEX_NODE_MODULES && path.join(process.env.CODEX_NODE_MODULES, "playwright/index.mjs"),
      path.join(process.cwd(), "node_modules/playwright/index.mjs"),
      path.resolve(SKILL_DIR, "../node_modules/playwright/index.mjs"),
      process.env.HOME && path.join(process.env.HOME, ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs")
    ].filter(Boolean);

    for (const candidate of candidates) {
      try {
        await fs.access(candidate);
        return await import(pathToFileURL(candidate).href);
      } catch {
        // Try the next deterministic local candidate.
      }
    }
    throw new Error(`Playwright is required but was not found. Install playwright in the current workspace. Original error: ${initialError.message}`);
  }
}

export async function cleanOwnedOutputs(outputDirectory) {
  await fs.mkdir(outputDirectory, { recursive: true });
  const entries = await fs.readdir(outputDirectory, { withFileTypes: true });
  await Promise.all(entries.filter((entry) => entry.isFile() && (/^\d{2}-(?:cover|page)\.png$/.test(entry.name) || entry.name === "manifest.json"))
    .map((entry) => fs.unlink(path.join(outputDirectory, entry.name))));
}

function isOwnedOutput(name) {
  return /^\d{2}-(?:cover|page)\.png$/.test(name) || name === "manifest.json";
}

export async function createStagingDirectory(outputDirectory) {
  const parent = path.dirname(outputDirectory);
  await fs.mkdir(parent, { recursive: true });
  return fs.mkdtemp(path.join(parent, `.${path.basename(outputDirectory)}-staging-`));
}

export async function discardStagingDirectory(stagingDirectory) {
  if (!stagingDirectory) return;
  await fs.rm(stagingDirectory, { recursive: true, force: true });
}

export async function commitOwnedOutputs(stagingDirectory, outputDirectory) {
  const parent = path.dirname(outputDirectory);
  await fs.mkdir(outputDirectory, { recursive: true });
  const stagedEntries = (await fs.readdir(stagingDirectory, { withFileTypes: true }))
    .filter((entry) => entry.isFile() && isOwnedOutput(entry.name));
  if (!stagedEntries.some((entry) => entry.name === "manifest.json")) {
    throw new Error("Staged render has no manifest.json; refusing to replace the previous output.");
  }

  const backupDirectory = await fs.mkdtemp(path.join(parent, `.${path.basename(outputDirectory)}-backup-`));
  const backedUp = [];
  const committed = [];
  try {
    const oldEntries = (await fs.readdir(outputDirectory, { withFileTypes: true }))
      .filter((entry) => entry.isFile() && isOwnedOutput(entry.name));
    for (const entry of oldEntries) {
      await fs.rename(path.join(outputDirectory, entry.name), path.join(backupDirectory, entry.name));
      backedUp.push(entry.name);
    }
    for (const entry of stagedEntries) {
      await fs.rename(path.join(stagingDirectory, entry.name), path.join(outputDirectory, entry.name));
      committed.push(entry.name);
    }
  } catch (error) {
    for (const name of committed.reverse()) {
      await fs.rename(path.join(outputDirectory, name), path.join(stagingDirectory, name)).catch(() => {});
    }
    for (const name of backedUp.reverse()) {
      await fs.rename(path.join(backupDirectory, name), path.join(outputDirectory, name)).catch(() => {});
    }
    throw error;
  } finally {
    await fs.rm(backupDirectory, { recursive: true, force: true });
  }
}

export async function browserLaunchOptions() {
  const candidates = [
    process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
    process.platform === "darwin" && "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    process.platform === "darwin" && "/Applications/Chromium.app/Contents/MacOS/Chromium",
    process.platform === "darwin" && "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    process.platform === "win32" && process.env.PROGRAMFILES && path.join(process.env.PROGRAMFILES, "Google/Chrome/Application/chrome.exe"),
    process.platform === "win32" && process.env["PROGRAMFILES(X86)"] && path.join(process.env["PROGRAMFILES(X86)"], "Google/Chrome/Application/chrome.exe"),
    process.platform === "win32" && process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, "Google/Chrome/Application/chrome.exe"),
    process.platform === "linux" && "/usr/bin/google-chrome",
    process.platform === "linux" && "/usr/bin/chromium",
    process.platform === "linux" && "/usr/bin/chromium-browser"
  ].filter(Boolean);

  for (const candidate of candidates) {
    try {
      await fs.access(candidate);
      return { headless: true, executablePath: candidate };
    } catch {
      // Use Playwright's managed browser when no system browser is available.
    }
  }
  return { headless: true };
}
