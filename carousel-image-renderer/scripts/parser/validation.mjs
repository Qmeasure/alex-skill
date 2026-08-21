import { plainText } from "./text.mjs";

const INTERNAL_SOURCE_LEAKAGE_PATTERNS = [
  /教材|教科书|讲义/,
  /(?:本课程|这门课程|该课程|第[一二三四五六七八九十0-9]+课|[一二三四五六七八九十0-9]+节课|课程(?:用|把|以|从|先|讲|介绍|指出|认为|提到|给出|写|说明|设|收场|开始|结束|分为))/,
  /(?:用户提供|输入内容|前序对话|内部上下文|当前上下文|对话上下文|提示词|系统提示|内部指令|写作指令)/,
  /(?:上文|下文|前文|后文|本段|本节|本章|这篇文章|本文|文章提供|文中|原文|信源)/,
  /(?:本地|现有|公开|已有|输入|原始)(?:材料|资料|文档|文件)/,
  /(?:根据|按照|来自)(?:这份|该份|上述|前述)?(?:材料|资料|文档|文件|教材|教科书|讲义|课程|原文)/,
  /(?:材料|资料|文档|文件)(?:中|里)?(?:显示|表明|证明|指出|提到|认为|给出|写道|记录|介绍|列出|披露|说明|称)/
];

const NON_REFERENTIAL_LEXEMES = [
  "土耳其", "其他",
  "应该", "不该", "活该",
  "尤其", "极其", "其实", "其次", "与其", "何其", "名副其实",
  "吉他", "利他", "排他",
  "因此", "此外", "彼此", "与此同时"
];

const UNRESOLVED_REFERENCE_PATTERNS = [
  /上述|前述|下述|如上|如下|前者|后者|这里|那里|此处|该处|这边|那边/,
  /我们|他们|她们|它们|本人|我|他|她|它|这|那|该|其|此/
];

const GENERIC_REFERENCE_PATTERNS = [
  /(?:相关|其他)(?:公司|企业|机构|产品|技术|数据|指标|报告|研究|市场|行业|事件|政策|方案|框架|结论|数字|观点|问题|部分|内容)/
];

const EMPTY_EVIDENCE_DISCLAIMER_PATTERNS = [
  /(?:这里|那里|教材|教科书|讲义|课程|原文|材料|资料|文档|文件|公开信息|现有信息|当前信息|已有信息|数据|数字|统计|口径|证据|披露).{0,24}(?:没有(?:给出|说明|明确|披露)|未(?:给出|说明|明确|披露)|不足以|缺少|不清(?:楚)?|不明确|不统一|无法(?:确认|判断|支持|验证))/,
  /(?:公开|现有|已有|当前)?(?:材料|资料|信息|披露).{0,18}(?:只能|仅能|仅可).{0,18}(?:确认|判断|支持|说明)/,
  /(?:只能|仅能|只适合|更适合|仅适合|可作为).{0,18}(?:参考|量级|过滤器|筛选器|判断依据|观察指标)/,
  /(?:不能|无法)(?:据此|仅凭|直接|简单).{0,24}(?:判断|推断|得出|外推|证明|确认)/,
  /(?:仍需|还需|需要进一步|有待).{0,18}(?:验证|核实|观察|跟踪|明确|补充|确认)/,
  /(?:目前|现阶段|当前)(?:只能|仅能|仅可).{0,24}(?:确认|判断|观察|看到)/
];

function collectMatches(text, patterns) {
  const matches = new Set();
  patterns.forEach((pattern) => {
    const flags = pattern.flags.includes("g") ? pattern.flags : `${pattern.flags}g`;
    for (const match of String(text).matchAll(new RegExp(pattern.source, flags))) {
      if (match[0]) matches.add(match[0]);
    }
  });
  return [...matches];
}

function maskLexemes(text, lexemes) {
  return lexemes.reduce(
    (result, lexeme) => result.split(lexeme).join(" ".repeat(lexeme.length)),
    String(text)
  );
}

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
  const visibleSegments = [
    { prose: plainText(document.meta.kicker || ""), location: "front matter kicker" },
    { prose: plainText(document.meta.title || ""), location: "front matter title" },
    { prose: plainText(document.meta.subtitle || ""), location: "front matter subtitle" },
    ...document.blocks
      .filter((block) => block.type !== "methodology-3x4")
      .map((block) => ({ prose: proseForBlock(block), line: block.line }))
  ].filter(({ prose }) => prose);
  visibleSegments.forEach(({ prose, line, location }) => {
    const sourceLeaks = collectMatches(prose, INTERNAL_SOURCE_LEAKAGE_PATTERNS);
    if (sourceLeaks.length) {
      addError("E_INTERNAL_SOURCE_LEAKAGE", "Reader-facing copy exposes an internal source container or writing context.", {
        line,
        location,
        actual: sourceLeaks.join("、").slice(0, 160),
        expected: "Facts stated directly, with only necessary authoritative attribution",
        action: "Delete the source wrapper and state the supported fact directly; if no standalone fact remains, delete the sentence."
      });
    }

    const referenceText = maskLexemes(prose, NON_REFERENTIAL_LEXEMES);
    const unresolvedReferences = [
      ...new Set([
        ...collectMatches(referenceText, UNRESOLVED_REFERENCE_PATTERNS),
        ...collectMatches(prose, GENERIC_REFERENCE_PATTERNS)
      ])
    ];
    if (unresolvedReferences.length) {
      addError("E_UNRESOLVED_REFERENCE", "Reader-facing copy uses a pronoun or contextual pointer instead of an explicit subject.", {
        line,
        location,
        actual: unresolvedReferences.join("、").slice(0, 160),
        expected: "The exact person, company, metric, event, document, method, or scope named where it is used",
        action: "Replace every reference with the exact supported subject; delete the sentence rather than inventing a referent."
      });
    }

    const emptyDisclaimers = collectMatches(prose, EMPTY_EVIDENCE_DISCLAIMER_PATTERNS);
    if (emptyDisclaimers.length) {
      addError("E_EMPTY_EVIDENCE_DISCLAIMER", "Reader-facing copy discusses missing evidence or reading limits without adding a usable fact.", {
        line,
        location,
        actual: emptyDisclaimers.join("、").slice(0, 200),
        expected: "A concrete fact, applicable scope, condition, or causal relationship",
        action: "Delete the entire disclaimer sentence and any unsupported number or argument branch; do not paraphrase it into another caution."
      });
    }
  });
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
