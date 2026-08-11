// 封面页构建。由 runtime.js 在编排阶段调用：window.__carouselCover(ctx)。
// ctx 约定：{ data, root, pageRecords, element, textElement, createBrand, BRAND_TAGLINE }。
window.__carouselCover = function createCoverPage(ctx) {
  const { data, root, pageRecords, element, textElement, createBrand, BRAND_TAGLINE } = ctx;
  const page = element("section", "page-card cover-page");
  page.dataset.kind = "cover";
  page.appendChild(textElement("div", "cover-kicker", data.meta.kicker));
  const main = element("div", "cover-main");
  main.appendChild(element("h1", "cover-title", data.meta.titleHtml));
  if (data.meta.subtitleHtml) main.appendChild(element("p", "cover-subtitle", data.meta.subtitleHtml));
  page.appendChild(main);
  const bottom = element("div", "cover-bottom");
  bottom.appendChild(createBrand());
  bottom.appendChild(textElement("span", "cover-tagline", BRAND_TAGLINE));
  bottom.appendChild(textElement("span", "page-number", ""));
  page.appendChild(bottom);
  root.appendChild(page);
  pageRecords.push({ page, flow: null });
};
