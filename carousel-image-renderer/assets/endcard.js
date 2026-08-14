// 末页导流页（缩略图 + 品牌卡 + 免责声明）构建与版本文案。
// 导流块固定独立成页，与正文分页解耦：正文无需为它预留空间。
// 由 runtime.js 调用：window.__carouselEndcard.appendEndBlock(ctx, thumbnailsBlock)。
// 版本由 render.mjs 的 --endcard native|guided 决定，默认 native。
// native：平台原生导流，不含二维码，引导读者关注账号并从主页继续阅读。
// guided：卡片内通栏显示截图指引——视频号图文里长按会触发加速播放，
// 无法直接识别二维码，只能引导用户截图后到微信扫一扫从相册识别。
const __ENDCARD_COPY = {
  native: {
    title: "更多AI产业与投资研究",
    intro: "智富界持续跟踪模型、算力、应用与创业，把复杂变化讲清楚。",
    guide: "关注智富界 · 主页查看更多图文",
    showQr: false
  },
  guided: {
    title: "完整研报加入智富界交流群",
    intro: "智富界是一个聚焦AI产业、创业与投资的研究社群，帮助企业及用户看懂AI、用好AI、投资AI。",
    guide: "截图本页 → 微信扫一扫 → 从相册识别",
    showQr: true
  }
};

window.__carouselEndcard = (() => {
  function buildEndBlock(ctx, thumbnailsBlock) {
    const { data, element, textElement } = ctx;
    const variant = __ENDCARD_COPY[data.meta.endcard] ? data.meta.endcard : "native";
    const copy = __ENDCARD_COPY[variant];
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

    const brand = element("div", `brand-card brand-card-${variant}`);
    const info = element("div", "brand-card-info");
    info.appendChild(textElement("div", "brand-card-title", copy.title));
    info.appendChild(textElement("div", "brand-card-intro", copy.intro));
    brand.appendChild(info);
    if (copy.showQr && data.meta.brandQr) {
      const qr = element("div", "brand-card-qr");
      const img = element("img", "brand-card-qr-image");
      img.src = data.meta.brandQr;
      img.alt = "扫码加入研报交流";
      qr.appendChild(img);
      brand.appendChild(qr);
    }
    brand.appendChild(textElement("div", "brand-card-guide", copy.guide));
    endBlock.appendChild(brand);

    const disclaimer = element("div", "disclaimer");
    disclaimer.textContent = "本文由AI结合公开资料整理生成，不代表投资建议";
    endBlock.appendChild(disclaimer);
    return endBlock;
  }

  function appendEndBlock(ctx, thumbnailsBlock) {
    const { createBodyPage } = ctx;
    const record = createBodyPage();
    record.isEndcard = true;
    record.page.classList.add("endcard-page");
    record.flow.appendChild(buildEndBlock(ctx, thumbnailsBlock));
  }

  return { appendEndBlock };
})();
