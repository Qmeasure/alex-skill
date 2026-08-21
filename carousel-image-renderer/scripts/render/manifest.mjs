import { plainText } from "../parser.mjs";
import { buildDebugTargets } from "./layout.mjs";

export async function collectPageDetails(page, report, coverOnly) {
  const rawPageDetails = await page.evaluate(() => [...document.querySelectorAll(".page-card")].map((card, index) => {
    const kind = card.classList.contains("endcard-page") ? "endcard" : (card.dataset.kind || "body");
    const labelNode = card.querySelector(".cover-title, .methodology-3x4-title, .section-text, .subheading, .lead-block, .body-paragraph, .thumbnails-heading");
    const features = [
      ["risk", ".risk-block"],
      ["callout", ".callout-block"],
      ["table", ".markdown-table"],
      ["image", ".markdown-image, .inline-markdown-image"],
      ["metrics", ".metrics"],
      ["methodology-3x4", ".methodology-3x4"]
    ].filter(([, selector]) => card.querySelector(selector)).map(([name]) => name);
    const textNodes = kind === "cover"
      ? [...card.querySelectorAll(".cover-kicker, .cover-title, .cover-subtitle")]
      : kind === "body" ? [card.querySelector(".page-flow")].filter(Boolean) : [];
    const text = textNodes
      .map((node) => node.innerText || node.textContent || "")
      .join("\n")
      .replace(/\r\n?/g, "\n")
      .replace(/[ \t]+/g, " ")
      .replace(/ *\n */g, "\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
    const cardRect = card.getBoundingClientRect();
    const regionNodes = kind === "cover"
      ? [["cover-content", card.querySelector(".cover-main")]]
      : kind === "body"
        ? [...card.querySelectorAll(".markdown-image, .inline-markdown-image")].map((node) => ["content-image", node])
        : [];
    const visualRegions = regionNodes.filter(([, node]) => node).map(([regionKind, node]) => {
      const rect = node.getBoundingClientRect();
      const x = Math.max(0, Math.floor(rect.left - cardRect.left));
      const y = Math.max(0, Math.floor(rect.top - cardRect.top));
      return {
        kind: regionKind,
        x,
        y,
        width: Math.min(cardRect.width - x, Math.ceil(rect.right - cardRect.left) - x),
        height: Math.min(cardRect.height - y, Math.ceil(rect.bottom - cardRect.top) - y)
      };
    }).filter((region) => region.width > 0 && region.height > 0);
    return {
      page: index + 1,
      kind,
      label: (labelNode?.textContent || "").replace(/\s+/g, " ").trim().slice(0, 120),
      features,
      text,
      visualRegions
    };
  }));
  const fills = new Map((report.fillRatios || []).map((entry) => [entry.page, entry]));
  return rawPageDetails
    .filter((detail) => !coverOnly || detail.kind === "cover")
    .map((detail) => {
      const fill = fills.get(detail.page);
      return {
        ...detail,
        file: `${String(detail.page).padStart(2, "0")}-${detail.kind === "cover" ? "cover" : "page"}.png`,
        ...(fill ? { fill: fill.fill, lastBody: fill.last } : {})
      };
    });
}

export function buildManifest({
  document,
  endcard,
  style,
  coverOnly,
  debug,
  files,
  pageDetails,
  fontReport,
  report,
  warnings,
  validationErrors,
  renderErrors,
  dimensions
}) {
  const blockingDiagnostics = debug ? [
    ...validationErrors.map((item) => ({ ...item, phase: "validation" })),
    ...renderErrors.map((item) => ({ ...item, phase: "layout" }))
  ] : [];
  return {
    title: plainText(document.meta.title),
    endcard,
    style,
    coverOnly,
    mode: debug ? "debug" : "formal",
    deliveryReady: !debug && !coverOnly,
    pages: files.length,
    bodyPages: pageDetails.filter((detail) => detail.kind === "body").length,
    totalPages: files.length,
    width: dimensions.pageWidth,
    height: dimensions.pageHeight,
    renderScale: dimensions.renderScale,
    renderWidth: dimensions.renderWidth,
    renderHeight: dimensions.renderHeight,
    resizeKernel: "lanczos3",
    fonts: {
      sans: "Source Han Sans SC",
      serif: "Source Han Serif SC",
      loadedFaces: fontReport.loadedFonts
    },
    files,
    pageDetails,
    ...(debug ? { debugTargets: buildDebugTargets(pageDetails, renderErrors) } : {}),
    fillRatios: report.fillRatios || [],
    warnings,
    blockingDiagnostics
  };
}
