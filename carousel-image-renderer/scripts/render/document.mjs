import fs from "node:fs/promises";
import process from "node:process";
import { embedLocalMarkdownImages } from "../images.mjs";
import { parseDocument, validateDocument } from "../parser.mjs";
import { diagnosticError, diagnosticsError, formatDiagnostic, parseFailure } from "../diagnostics.mjs";

export async function loadRenderDocument(inputPath, { coverOnly = false } = {}) {
  let rawSource;
  try {
    rawSource = await fs.readFile(inputPath, "utf8");
  } catch (error) {
    throw diagnosticError("E_INPUT_READ", "The input Markdown file could not be read.", {
      location: inputPath,
      actual: error.message,
      action: "Confirm the file exists and is readable UTF-8 text, then rerun render.mjs."
    });
  }

  let source;
  try {
    source = await embedLocalMarkdownImages(rawSource, inputPath);
  } catch (error) {
    throw diagnosticError("E_IMAGE_READ", "A local Markdown image could not be embedded.", {
      actual: error.message,
      expected: "Every local image path resolves from the Markdown file directory",
      action: "Fix the reported image path or regenerate the source thumbnails, then rerun render.mjs."
    });
  }

  let document;
  try {
    document = parseDocument(source);
  } catch (error) {
    throw diagnosticsError([parseFailure(error)]);
  }
  if (coverOnly && !document.meta.cover) {
    throw diagnosticError("E_COVER_REQUIRED", "--cover-only cannot run when front matter sets cover: false.", {
      action: "Enable the cover or remove --cover-only."
    });
  }

  const validation = validateDocument(document);
  if (validation.errors.length) throw diagnosticsError(validation.errors);
  validation.warnings.forEach((warning) => process.stderr.write(`${formatDiagnostic(warning, "Warning")}\n`));
  return { document, validation };
}
