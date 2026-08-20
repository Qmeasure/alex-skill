function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[character]);
}

function escapeAttribute(value) {
  return escapeHtml(value).replace(/`/g, "&#96;");
}

export function normalizeDestination(value) {
  const trimmed = String(value).trim();
  return trimmed.startsWith("<") && trimmed.endsWith(">") ? trimmed.slice(1, -1) : trimmed;
}

export function safeUrl(value, kind = "link") {
  const url = normalizeDestination(value);
  if (/^(?:javascript|vbscript):/i.test(url)) return "";
  if (/^data:/i.test(url) && !(kind === "image" && /^data:image\//i.test(url))) return "";
  return url;
}

export function parseInline(value, options = {}) {
  const tokens = [];
  const stash = (html) => `${tokens.push(html) - 1}`;
  let source = String(value);

  source = source.replace(/`([^`\n]+)`/g, (_, code) => stash(`<code class="inline-code">${escapeHtml(code)}</code>`));

  source = source.replace(/!\[([^\]]*)\]\((<[^>]+>|[^\s)]+)(?:\s+["']([^"']*)["'])?\)/g, (match, alt, destination, title) => {
    const url = safeUrl(destination, "image");
    if (!url) return match;
    const titleAttribute = title ? ` title="${escapeAttribute(title)}"` : "";
    return stash(`<img class="inline-markdown-image" src="${escapeAttribute(url)}" alt="${escapeAttribute(alt)}"${titleAttribute}>`);
  });

  source = source.replace(/\[([^\]]+)\]\((<[^>]+>|[^\s)]+)(?:\s+["']([^"']*)["'])?\)/g, (match, label, destination, title) => {
    const url = safeUrl(destination, "link");
    if (!url) return match;
    const titleAttribute = title ? ` title="${escapeAttribute(title)}"` : "";
    return stash(`<a class="markdown-link" href="${escapeAttribute(url)}"${titleAttribute}>${parseInline(label, options)}</a>`);
  });

  source = source.replace(/\[\^([^\]]+)\]/g, (match, id) => {
    const number = options.footnoteNumbers?.get(id);
    return number ? stash(`<sup class="footnote-ref">${number}</sup>`) : match;
  });

  source = source.replace(/<\/?(?:br|strong|b|em|i|u|mark|small|sub|sup|kbd|code|span)(?:\s+[^>]*)?\s*\/?>/gi, (tag) => {
    const match = tag.match(/^<(\/)?([a-z0-9]+)[^>]*>$/i);
    if (!match) return tag;
    const closing = Boolean(match[1]);
    const name = match[2].toLowerCase();
    if (name === "br") return stash("<br>");
    return stash(`<${closing ? "/" : ""}${name}>`);
  });

  let html = escapeHtml(source);
  html = html.replace(/\*\*([\s\S]+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/__([^_]+?)__/g, "<strong>$1</strong>");
  html = html.replace(/~~([\s\S]+?)~~/g, "<del>$1</del>");
  html = html.replace(/(^|[^*])\*([^*\n]+?)\*(?!\*)/g, "$1<em>$2</em>");
  html = html.replace(/(^|[^\w])_([^_\n]+?)_(?!\w)/g, "$1<em>$2</em>");
  html = html.replace(/==(.+?)==/g, '<span class="inline-highlight">$1</span>');
  html = html.replace(/\{accent\}([\s\S]+?)\{\/accent\}/g, '<span class="accent">$1</span>');
  html = html.replace(/\{circle\}([\s\S]+?)\{\/circle\}/g, '<span class="hand-circle">$1</span>');
  html = html.replace(/\{wavy\}([\s\S]+?)\{\/wavy\}/g, '<span class="hand-wavy">$1</span>');
  html = html.replace(/\n/g, "<br>");
  return html.replace(/(\d+)/g, (_, index) => tokens[Number(index)]);
}

export function plainText(value) {
  return String(value)
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/\[\^[^\]]+\]/g, "")
    .replace(/\{\/?(?:accent|circle|wavy)\}/g, "")
    .replace(/==|\*\*|__|~~|`|(?<!\*)\*(?!\*)|_/g, "")
    .replace(/<[^>]*>/g, "")
    .trim();
}

export { escapeHtml };
