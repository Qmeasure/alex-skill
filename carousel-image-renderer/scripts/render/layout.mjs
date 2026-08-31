import process from "node:process";
import { diagnostic, diagnosticsError, formatDiagnostic } from "../diagnostics.mjs";

// 正文页填充率红线（面积法：各块实际高度之和 ÷ flow 高度）：
// 低于 FILL_ERROR_THRESHOLD 渲染失败，低于 FILL_WARNING_THRESHOLD 打警告（可能是不可拆块进位，需自查）。
const FILL_ERROR_THRESHOLD = 0.7;
const FILL_WARNING_THRESHOLD = 0.75;
// 页数硬约束：封面与导流页固定占用 2 页，正文必须落在允许区间内。
const MIN_BODY_PAGES = 7;
const MAX_BODY_PAGES = 16;

export function buildBodyPageCountDiagnostics(bodyPages, totalPages, { coverOnly = false, debugAction = "" } = {}) {
  if (coverOnly) return [];
  const debugSuffix = debugAction ? ` ${debugAction}` : "";
  const errors = [];
  if (bodyPages < MIN_BODY_PAGES) {
    errors.push(diagnostic("E_BODY_PAGES_MIN", "The carousel does not meet the minimum body-page count.", {
      actual: `${bodyPages} body page(s), ${totalPages} total page(s)`,
      expected: `At least ${MIN_BODY_PAGES} body pages, ${MIN_BODY_PAGES + 2} total pages`,
      action: `Use unused source facts first, then add audited web research if needed; expand and re-render without padding or repetition.${debugSuffix}`
    }));
  }
  if (bodyPages > MAX_BODY_PAGES) {
    errors.push(diagnostic("E_BODY_PAGES_MAX", "The carousel exceeds the maximum body-page count.", {
      actual: `${bodyPages} body page(s), ${totalPages} total page(s)`,
      expected: `At most ${MAX_BODY_PAGES} body pages, ${MAX_BODY_PAGES + 2} total pages`,
      action: `Remove redundant or lower-priority material, combine adjacent complete ideas, and re-render; do not shrink text or remove the cover or endcard.${debugSuffix}`
    }));
  }
  return errors;
}

export function buildDebugTargets(pageDetails, diagnostics) {
  const pagesByNumber = new Map(pageDetails.map((page) => [page.page, page.file]));
  const pagesFor = (code) => [...new Set(diagnostics
    .filter((item) => item.code === code && item.page != null)
    .map((item) => item.page))]
    .sort((left, right) => left - right)
    .map((pageNumber) => pagesByNumber.get(pageNumber))
    .filter(Boolean);
  const failingPageNumbers = new Set(diagnostics
    .filter((item) => item.page != null)
    .map((item) => item.page));
  const adjacentPageNumbers = new Set();
  for (const pageNumber of failingPageNumbers) {
    if (pagesByNumber.has(pageNumber - 1) && !failingPageNumbers.has(pageNumber - 1)) adjacentPageNumbers.add(pageNumber - 1);
    if (pagesByNumber.has(pageNumber + 1) && !failingPageNumbers.has(pageNumber + 1)) adjacentPageNumbers.add(pageNumber + 1);
  }
  return {
    fillErrorPages: pagesFor("E_PAGE_FILL_LOW"),
    overflowPages: pagesFor("E_PAGE_OVERFLOW"),
    adjacentPages: [...adjacentPageNumbers].sort((left, right) => left - right).map((pageNumber) => pagesByNumber.get(pageNumber))
  };
}

export async function inspectLayout({ page, report, coverOnly, debug, debugAction, warnings }) {
  const renderErrors = [];
  if (report.overflowPages.length && !coverOnly) {
    const debugCards = page.locator(".page-card");
    const cardCount = await debugCards.count();
    for (let index = 0; index < cardCount; index += 1) {
      const text = await debugCards.nth(index).innerText();
      const lines = text.split(/\n/).filter(Boolean);
      const head = lines.slice(0, 3).join(" | ").slice(0, 60);
      const tail = lines.slice(-3).join(" | ").slice(0, 80);
      const size = await debugCards.nth(index).evaluate((el) => {
        const flow = el.querySelector(".page-flow") || el;
        return { used: flow.scrollHeight, max: flow.clientHeight };
      });
      const marker = report.overflowPages.includes(index + 1) ? "OVERFLOW" : "ok";
      console.error(`  page ${index + 1} [${marker}] content ${size.used}px / limit ${size.max}px :: head: ${head} :: tail: ${tail}`);
    }
    report.overflowPages.forEach((pageNumber) => renderErrors.push(diagnostic("E_PAGE_OVERFLOW", `Content overflows rendered page ${pageNumber}.`, {
      page: pageNumber,
      expected: "All blocks fit inside the 1080×1440 page flow",
      action: `Shorten the oversized unbreakable block; use a page break only between complete ideas. ${debugAction}`
    })));
  }

  // 正文页填充率检查（导流页与最后一页正文页由 runtime 标记豁免）。--cover-only 只出封面预览，跳过正文检查。
  // 提示文案自带算法说明，避免调用方为了理解百分比含义去翻源码。
  const FILL_ALGO_NOTE = "Fill ratio is area-based: sum of each block's rendered height ÷ page flow height (gaps between blocks are layout rhythm and not counted). Per-page values are written to fillRatios in manifest.json. Do not guess a page's contents from a stale manifest — any content change shifts all later pagination; re-render, read the new fillRatios, then add or remove content so the total lands just above a whole number of pages.";
  const percent = (value) => `${Math.round(value * 100)}%`;
  const sparsePages = coverOnly ? [] : (report.fillRatios || []).filter((entry) => !entry.last && entry.fill < FILL_WARNING_THRESHOLD);
  sparsePages.filter((entry) => entry.fill >= FILL_ERROR_THRESHOLD).forEach((entry) => {
    const message = `Body page ${entry.page} is only ${percent(entry.fill)} full (warns below ${percent(FILL_WARNING_THRESHOLD)}, fails below ${percent(FILL_ERROR_THRESHOLD)}). Usually an unbreakable block rounding up or an unnecessary :::pagebreak — inspect the PNG and rebalance if the page looks visibly empty.`;
    const warning = diagnostic("W_PAGE_FILL_LOW", message, {
      page: entry.page,
      actual: percent(entry.fill),
      expected: `At least ${percent(FILL_WARNING_THRESHOLD)}`,
      action: "Inspect the new PNG and rebalance nearby content only if the page looks visibly empty."
    });
    warnings.push(warning);
    process.stderr.write(`${formatDiagnostic(warning, "Warning")}\n`);
  });
  const sparseErrors = sparsePages.filter((entry) => entry.fill < FILL_ERROR_THRESHOLD);
  if (sparseErrors.length) {
    renderErrors.push(...sparseErrors.map((entry) => diagnostic("E_PAGE_FILL_LOW", `Body page ${entry.page} is below the minimum fill ratio.`, {
      page: entry.page,
      actual: percent(entry.fill),
      expected: `At least ${percent(FILL_ERROR_THRESHOLD)}`,
      action: `Rebalance nearby source-grounded content; if it is a trailing near-empty page, trim earlier content. ${debugAction} ${FILL_ALGO_NOTE}`
    })));
  }

  const bodyPages = (report.fillRatios || []).length;
  renderErrors.push(...buildBodyPageCountDiagnostics(bodyPages, report.pageCount, { coverOnly, debugAction }));
  if (renderErrors.length && !debug) throw diagnosticsError(renderErrors);
  return renderErrors;
}
