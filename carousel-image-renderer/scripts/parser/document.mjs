import { parseBlocks } from "./blocks.mjs";
import { parseFrontMatter } from "./front-matter.mjs";
import { parseInline, plainText } from "./text.mjs";

function countWords(blocks) {
  const parts = [];
  function collect(block) {
    if (block.raw != null) parts.push(plainText(block.raw));
    if (block.type === "list") {
      block.items.forEach((item) => {
        parts.push(plainText(item.raw));
        if (item.children) item.children.forEach(collect);
      });
    }
    if (block.type === "metrics") {
      block.items.forEach((item) => { parts.push(item.label); parts.push(item.value); });
    }
    if (block.type === "table") {
      block.headers.forEach((h) => parts.push(h.raw));
      block.rows.forEach((row) => row.forEach((cell) => parts.push(cell.raw)));
    }
    if (block.type === "footnotes") {
      block.items.forEach((item) => parts.push(plainText(item.raw)));
    }
  }
  blocks.forEach(collect);
  const text = parts.join(" ");
  const chinese = (text.match(/[一-鿿㐀-䶿]/g) || []).length;
  const english = (text.replace(/[一-鿿㐀-䶿]/g, " ").match(/[a-zA-Z]+/g) || []).length;
  return chinese + english;
}

export function parseDocument(source) {
  const { meta: suppliedMeta, body, bodyLineOffset } = parseFrontMatter(source);
  const meta = {
    title: "",
    subtitle: "",
    kicker: "图文报告",
    cover: true,
    ...suppliedMeta
  };
  delete meta.callout_label;
  const blocks = parseBlocks(body, bodyLineOffset);
  blocks.forEach((block) => {
    if (block.line != null) block.line += bodyLineOffset;
  });
  meta.title = String(meta.title || "").trim();
  meta.subtitle = String(meta.subtitle || "").trim();
  meta.kicker = String(meta.kicker || "图文报告").trim();
  meta.cover = meta.cover !== false;
  meta.titleHtml = parseInline(meta.title);
  meta.subtitleHtml = parseInline(meta.subtitle);
  const wc = countWords(blocks);
  meta.wordCount = wc;
  meta.readingMinutes = Math.max(1, Math.ceil(wc / 400));
  return { meta, blocks };
}
