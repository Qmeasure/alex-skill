// Markdown 解析与文档校验：把输入 Markdown 解析为渲染文档（meta + blocks）。
// 被 render.mjs 与 validate.mjs 共同使用。

import { plainText } from "./parser/text.mjs";

export { parseDocument } from "./parser/document.mjs";
export { normalizeDestination, plainText, safeUrl } from "./parser/text.mjs";

export function validateDocument(document) {
  const errors = [];
  const warnings = [];
  const addError = (code, message, details = {}) => errors.push({ code, message, ...details });
  const addWarning = (code, message, details = {}) => warnings.push({ code, message, ...details });
  if (!document.meta.title) {
    addError("E_TITLE_REQUIRED", "Front matter must contain a non-empty title.", {
      expected: "A one-line `title:` field in front matter",
      action: "Add the final cover title to front matter; body H1 headings are not a fallback."
    });
  }
  if (!document.meta.cover) {
    addError("E_COVER_REQUIRED", "The branded carousel must include its cover page.", {
      actual: "cover: false",
      expected: "cover: true or an omitted cover field",
      action: "Remove `cover: false` or set `cover: true`."
    });
  }
  if (Object.prototype.hasOwnProperty.call(document.meta, "theme")) {
    addError("E_THEME_REMOVED", "Custom themes are no longer supported.", {
      actual: document.meta.theme,
      expected: "No `theme` field; the renderer uses the fixed brand palette",
      action: "Remove front matter `theme`."
    });
  }
  const visibleBlocks = document.blocks.filter((block) => block.type !== "pagebreak");
  if (!visibleBlocks.length) {
    addError("E_BODY_EMPTY", "The article has no renderable content blocks.", {
      expected: "At least one body content block",
      action: "Add article body content below front matter."
    });
  }
  document.blocks.filter((block) => block.type === "section").forEach((block) => {
    String(block.raw || "").split("\n").forEach((line, index) => {
      if (!/^\s*#{1,6}(?:\s+|$)/.test(line)) return;
      addError("E_SECTION_MARKDOWN_HEADING", ":::section content must not contain Markdown heading syntax.", {
        line: block.line == null ? undefined : block.line + index + 1,
        actual: line.trim().slice(0, 80),
        expected: "Plain section title text without leading Markdown heading markers",
        action: "Remove the leading # characters; use either a plain :::section title or a standalone H2–H6 heading, not both."
      });
    });
  });
  if (!document.blocks.some((block) => block.type === "callout")) {
    addError("E_CALLOUT_REQUIRED", "Every carousel must contain at least one non-empty :::callout block.", {
      expected: "At least one non-empty :::callout directive",
      action: "Add a concise AI viewpoint grounded in the available evidence."
    });
  }
  if (!document.blocks.some((block) => block.type === "risk")) {
    addError("E_RISK_REQUIRED", "Every carousel must contain at least one non-empty :::risk block.", {
      expected: "At least one non-empty :::risk directive",
      action: "Add a concise risk disclosure grounded in the source material."
    });
  }
  const methodologyIndexes = document.blocks
    .map((block, index) => block.type === "methodology-3x4" ? index : -1)
    .filter((index) => index >= 0);
  if (methodologyIndexes.length > 1) {
    addError("E_3X4_COMPONENT_MULTIPLE", "The fixed :::methodology-3x4 component may appear at most once.", {
      actual: methodologyIndexes.length,
      expected: "Zero or one :::methodology-3x4 directive",
      action: "Keep only the first fixed 3×4 introduction before the article-specific mapping."
    });
  }
  const thumbnailIndexes = document.blocks.map((block, index) => block.type === "thumbnails" ? index : -1).filter((index) => index >= 0);
  if (!thumbnailIndexes.length) {
    addError("E_THUMBNAILS_REQUIRED", "Every carousel must end with source thumbnails.", {
      expected: "One non-empty :::thumbnails directive",
      action: "Run source-prep.mjs and insert its generated thumbnail paths at the end of the Markdown."
    });
  } else {
    if (thumbnailIndexes.length > 1) {
      addError("E_THUMBNAILS_MULTIPLE", "Only one :::thumbnails directive is allowed.", {
        actual: thumbnailIndexes.length,
        expected: 1,
        action: "Merge all thumbnail images into the final :::thumbnails block."
      });
    }
    const lastContentIndex = document.blocks.reduce((last, block, index) => block.type === "pagebreak" ? last : index, -1);
    if (thumbnailIndexes.at(-1) !== lastContentIndex) {
      addError("E_THUMBNAILS_POSITION", "The :::thumbnails directive must be the final content block.", {
        action: "Move :::thumbnails after all body content and remove content that follows it."
      });
    }
    const thumbnailBlock = document.blocks[thumbnailIndexes[0]];
    if (thumbnailBlock?.images?.length > 4) {
      addError("E_THUMBNAILS_COUNT", "The endcard supports at most four source thumbnails.", {
        line: thumbnailBlock.line,
        actual: thumbnailBlock.images.length,
        expected: "1–4 thumbnails",
        action: "Use source-manifest.json `thumbnailMarkdown`, which selects at most four previews across all source groups."
      });
    }
  }

  const listProse = (block) => block.items.map((item) => [
    plainText(item.raw),
    ...(item.children || []).map((child) => listProse(child))
  ].join(" ")).join(" ");
  const proseForBlock = (block) => {
    if (["code", "thumbnails", "pagebreak", "hr"].includes(block.type)) return "";
    if (block.type === "image") return plainText(block.title || block.alt || "");
    if (block.raw != null) return plainText(block.raw);
    if (block.type === "list") return listProse(block);
    if (block.type === "metrics") return block.items.map((item) => `${item.label} ${item.value}`).join(" ");
    if (block.type === "table") return [
      ...block.headers.map((cell) => cell.raw),
      ...block.rows.flat().map((cell) => cell.raw)
    ].join(" ");
    if (block.type === "footnotes") return block.items.map((item) => plainText(item.raw)).join(" ");
    return "";
  };
  const methodologyReference = /3\s*[×xX*]\s*4/;
  const methodologyReferences = document.blocks
    .map((block, index) => ({ block, index, prose: proseForBlock(block) }))
    .filter(({ block, prose }) => block.type !== "methodology-3x4" && methodologyReference.test(prose));
  const coverReference = [document.meta.kicker, document.meta.title, document.meta.subtitle]
    .some((value) => methodologyReference.test(plainText(value || "")));
  if (coverReference) {
    addError("E_3X4_COVER_REFERENCE", "The cover cannot mention 3×4 before the fixed body introduction.", {
      expected: "Introduce 3×4 with :::methodology-3x4 in the body before the article-specific mapping",
      action: "Remove the 3×4 label from the cover and keep the selected financial angle."
    });
  }
  if (methodologyReferences.length && !methodologyIndexes.length) {
    addError("E_3X4_COMPONENT_REQUIRED", "Body copy mentions 3×4 without the fixed introduction component.", {
      line: methodologyReferences[0].block.line,
      expected: "A :::methodology-3x4 directive before the first article-specific 3×4 reference",
      action: "Insert the fixed directive after the factual causal chain and before the mapping; do not write the introduction manually."
    });
  } else if (methodologyReferences.some(({ index }) => index < methodologyIndexes[0])) {
    const earlyReference = methodologyReferences.find(({ index }) => index < methodologyIndexes[0]);
    addError("E_3X4_COMPONENT_ORDER", "Body copy mentions 3×4 before the fixed introduction component.", {
      line: earlyReference?.block.line,
      expected: ":::methodology-3x4 is the first reader-visible 3×4 reference",
      action: "Move the fixed component before this reference."
    });
  }
  const forbiddenBodyTerms = [
    {
      term: "你",
      code: "E_BODY_SECOND_PERSON",
      message: "Body copy must not use the second-person character “你”.",
      expected: "Objective wording with the subject omitted or named explicitly",
      action: "Rewrite the sentence without second-person or generic audience substitutions."
    },
    {
      term: "本文",
      code: "E_BODY_META_REFERENCE",
      message: "Body copy must not refer to itself with “本文”.",
      expected: "Direct narration of the subject, evidence, or conclusion",
      action: "Name the event or subject directly, or remove the meta-reference."
    }
  ];
  document.blocks.forEach((block) => {
    const prose = proseForBlock(block);
    forbiddenBodyTerms.forEach(({ term, code, message, expected, action }) => {
      const occurrences = prose.split(term).length - 1;
      if (occurrences) {
        addError(code, message, {
          line: block.line,
          actual: `${term} × ${occurrences}`,
          expected,
          action
        });
      }
    });
  });
  document.blocks.forEach((block, index) => {
    if (block.type === "paragraph" && plainText(block.raw).length > 700) {
      addWarning("W_PARAGRAPH_LONG", `Paragraph block ${index + 1} is longer than 700 characters and may not fit on one page.`, {
        line: block.line,
        action: "Split the paragraph at a complete thought if it overflows."
      });
    }
    if (["circle", "wavy", "accent"].some((mark) => {
      const opens = (block.raw?.match(new RegExp(`\\{${mark}\\}`, "g")) || []).length;
      const closes = (block.raw?.match(new RegExp(`\\{\\/${mark}\\}`, "g")) || []).length;
      return opens !== closes;
    })) {
      addError("E_INLINE_MARK_UNBALANCED", `Unbalanced inline mark in block ${index + 1}.`, {
        line: block.line,
        action: "Add the matching closing mark in the same paragraph."
      });
    }
    if (block.type === "table" && block.columnCount > 5) {
      addWarning("W_TABLE_WIDE", `Table block ${index + 1} has ${block.columnCount} columns; 5 or fewer are recommended.`, { line: block.line });
    }
    if (block.type === "table" && block.rows.length > 10) {
      addWarning("W_TABLE_TALL", `Table block ${index + 1} has ${block.rows.length} body rows and may be too tall for one page.`, { line: block.line });
    }
    if (block.type === "code" && block.raw.split("\n").length > 18) {
      addWarning("W_CODE_LONG", `Code block ${index + 1} has more than 18 lines and may be too tall for one page.`, { line: block.line });
    }
    if (block.type === "image" && !block.alt && !block.title) {
      addWarning("W_IMAGE_UNLABELED", `Image block ${index + 1} has no alt text or title, so it will render without a caption.`, { line: block.line });
    }
  });
  return { errors, warnings };
}
