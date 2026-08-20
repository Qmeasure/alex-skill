// Stable Parser facade shared by render.mjs, validate.mjs, and external callers.

export { parseDocument } from "./parser/document.mjs";
export { normalizeDestination, plainText, safeUrl } from "./parser/text.mjs";
export { validateDocument } from "./parser/validation.mjs";
