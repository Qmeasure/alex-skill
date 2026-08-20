import fs from "node:fs/promises";
import path from "node:path";
import sharp from "sharp";
import { diagnosticError } from "../diagnostics.mjs";

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

export async function downsampleScreenshot(png, dimensions) {
  const sourceWidth = png.readUInt32BE(16);
  const sourceHeight = png.readUInt32BE(20);
  if (sourceWidth !== dimensions.renderWidth || sourceHeight !== dimensions.renderHeight) {
    throw diagnosticError("E_RENDER_DIMENSIONS", "The high-resolution screenshot has unexpected dimensions.", {
      actual: `${sourceWidth}×${sourceHeight}`,
      expected: `${dimensions.renderWidth}×${dimensions.renderHeight}`,
      action: `Keep the browser viewport at ${dimensions.pageWidth}×${dimensions.pageHeight}, deviceScaleFactor at ${dimensions.renderScale}, and screenshot scale at device.`
    });
  }
  try {
    const { data, info } = await sharp(png)
      .resize(dimensions.pageWidth, dimensions.pageHeight, { fit: "fill", kernel: sharp.kernel.lanczos3 })
      .png({ compressionLevel: 9, adaptiveFiltering: true })
      .toBuffer({ resolveWithObject: true });
    if (info.width !== dimensions.pageWidth || info.height !== dimensions.pageHeight) {
      throw new Error(`Sharp returned ${info.width}×${info.height}.`);
    }
    return data;
  } catch (error) {
    throw diagnosticError("E_OUTPUT_RESIZE", "The supersampled screenshot could not be resized to the delivery dimensions.", {
      actual: error.message,
      expected: `${dimensions.pageWidth}×${dimensions.pageHeight} PNG output`,
      action: "Confirm sharp is installed and operational, then rerun render.mjs."
    });
  }
}

export async function captureScreenshots({ page, coverOnly, stagingDirectory, dimensions }) {
  const cards = page.locator(".page-card");
  const count = await cards.count();
  const files = [];
  for (let index = 0; index < count; index += 1) {
    const kind = await cards.nth(index).getAttribute("data-kind");
    if (coverOnly && kind !== "cover") continue;
    const fileName = `${String(index + 1).padStart(2, "0")}-${kind === "cover" ? "cover" : "page"}.png`;
    const supersampled = await cards.nth(index).screenshot({ type: "png", scale: "device" });
    const delivered = await downsampleScreenshot(supersampled, dimensions);
    await fs.writeFile(path.join(stagingDirectory, fileName), delivered);
    files.push(fileName);
  }
  return files;
}

export async function writeManifest(stagingDirectory, manifest) {
  await fs.writeFile(path.join(stagingDirectory, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
}
