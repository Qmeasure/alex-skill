export function diagnostic(code, message, details = {}) {
  return {
    code,
    message,
    ...(details.location ? { location: details.location } : {}),
    ...(details.line != null ? { line: details.line } : {}),
    ...(details.page != null ? { page: details.page } : {}),
    ...(details.actual != null ? { actual: details.actual } : {}),
    ...(details.expected != null ? { expected: details.expected } : {}),
    ...(details.action ? { action: details.action } : {})
  };
}

export function formatDiagnostic(item, level = "Error") {
  const lines = [`${level} [${item.code}]: ${item.message}`];
  const location = item.location || (item.line != null ? `line ${item.line}` : item.page != null ? `page ${item.page}` : "");
  if (location) lines.push(`  Location: ${location}`);
  if (item.actual != null) lines.push(`  Actual: ${item.actual}`);
  if (item.expected != null) lines.push(`  Expected: ${item.expected}`);
  if (item.action) lines.push(`  Action: ${item.action}`);
  return lines.join("\n");
}

export function parseFailure(error) {
  return diagnostic("E_MARKDOWN_PARSE", error?.message || String(error), {
    expected: "Valid carousel Markdown and directives",
    action: "Fix the reported Markdown syntax, then run validate.mjs again."
  });
}

export function diagnosticError(code, message, details = {}) {
  const error = new Error(message);
  error.diagnostic = diagnostic(code, message, details);
  return error;
}

export function diagnosticsError(items) {
  const error = new Error(items.map((item) => item.message).join("\n"));
  error.diagnostics = items;
  return error;
}

export function diagnosticsFromError(error, fallbackCode = "E_RENDER_FAILED") {
  if (Array.isArray(error?.diagnostics)) return error.diagnostics;
  if (error?.diagnostic) return [error.diagnostic];
  return [diagnostic(fallbackCode, error?.message || String(error), {
    action: "Read the error details, fix the input or environment, then rerun the command."
  })];
}
