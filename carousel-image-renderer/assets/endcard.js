// 末页导流页（缩略图 + 品牌卡 + 免责声明）构建与版本文案。
// 导流块固定独立成页，与正文分页解耦：正文无需为它预留空间。
// 由 runtime.js 调用：window.__carouselEndcard.appendEndBlock(ctx, thumbnailsBlock)。
// 版本由 render.mjs 的 --endcard guided|legacy 决定，默认 guided。
// legacy：二维码下方小字“扫码加入研报交流”（2026年8月前的线上文案）。
// guided：去掉小字，卡片内通栏一行截图指引——视频号图文里长按会触发加速播放，
// 无法直接识别二维码，只能引导用户截图后到微信扫一扫从相册识别。
const __ENDCARD_COPY = {
  legacy: { qrLabel: "扫码加入研报交流", guide: "" },
  guided: { qrLabel: "", guide: "截图本页 → 微信扫一扫 → 从相册识别" }
};

window.__carouselEndcard = (() => {
  function buildEndBlock(ctx, thumbnailsBlock) {
    const { data, element, textElement } = ctx;
    const copy = __ENDCARD_COPY[data.meta.endcard] || __ENDCARD_COPY.guided;
    const endBlock = element("div", "end-block");

    if (thumbnailsBlock) {
      const thumbSection = element("div", "thumbnails-block");
      const thumbHeading = data.meta.source_pages ? `完整内容预览 共${data.meta.source_pages}页` : "完整内容预览";
      thumbSection.appendChild(textElement("div", "thumbnails-heading", thumbHeading));
      const grid = element("div", "thumbnails-grid");
      thumbnailsBlock.images.forEach((img) => {
        const thumb = element("div", "thumbnail-item");
        const image = element("img", "thumbnail-image");
        image.src = img.src;
        image.alt = img.alt || "";
        thumb.appendChild(image);
        grid.appendChild(thumb);
      });
      thumbSection.appendChild(grid);
      endBlock.appendChild(thumbSection);
    }

    if (data.meta.brandQr) {
      const brand = element("div", copy.guide ? "brand-card brand-card-guided" : "brand-card");
      const info = element("div", "brand-card-info");
      info.appendChild(textElement("div", "brand-card-title", "完整研报加入智富界交流群"));
      info.appendChild(textElement("div", "brand-card-intro", "智富界是一个聚焦AI产业、创业与投资的研究平台，帮助企业及用户看懂AI、用好AI、投资AI。"));
      brand.appendChild(info);
      const qr = element("div", "brand-card-qr");
      const img = element("img", "brand-card-qr-image");
      img.src = data.meta.brandQr;
      img.alt = "扫码加入研报交流";
      qr.appendChild(img);
      if (copy.qrLabel) qr.appendChild(textElement("div", "brand-card-qr-label", copy.qrLabel));
      brand.appendChild(qr);
      if (copy.guide) brand.appendChild(textElement("div", "brand-card-guide", copy.guide));
      endBlock.appendChild(brand);
    }

    const disclaimer = element("div", "disclaimer");
    disclaimer.textContent = "本文由AI结合公开资料整理生成，不代表投资建议";
    endBlock.appendChild(disclaimer);
    return endBlock;
  }

  function appendEndBlock(ctx, thumbnailsBlock) {
    const { data, pageRecords, createBodyPage } = ctx;
    if (!thumbnailsBlock && !data.meta.brandQr) {
      // 既无缩略图也无品牌码时只剩免责声明，直接接在最后一页正文末尾，不单独占页。
      const lastBody = [...pageRecords].reverse().find((record) => record.flow && !record.isEndcard);
      if (lastBody) lastBody.flow.appendChild(buildEndBlock(ctx, null));
      return;
    }
    const record = createBodyPage();
    record.isEndcard = true;
    record.page.classList.add("endcard-page");
    record.flow.appendChild(buildEndBlock(ctx, thumbnailsBlock));
  }

  return { appendEndBlock };
})();
