# Content format

## Front matter

Start each input with this simple YAML-compatible front matter:

```md
---
title: GEO {circle}第二步{/circle} 到底做什么
subtitle: 一份真实读数，解释为什么排名高却很少被提到
kicker: GEO 数据复盘
cover: true
theme: classic
---
```

Supported fields:

- `title` — required; supports inline marks and appears on the cover only.
- `subtitle` — optional cover subtitle.
- `kicker` — small cover label.
- `cover` — `true` or `false`; defaults to `true`.
- `theme` — `classic`, `finance`, `editorial`, or `tech`; defaults to `classic`. See [themes.md](themes.md) for selection guidance.
- `callout_label` — optional label prefix for `:::callout` panels; defaults to `AI观点`.
- `source_pages` — optional integer; total page count of the source document. When set, the thumbnails heading shows `完整内容预览 共X页`.

Keep each field on one line. Quote a value only when leading or trailing spaces matter.

The brand footer is fixed in the template: `智富界` on the left and `看懂AI，用好AI，投资AI` on the right. Do not add brand fields to individual inputs.

## Native Markdown

Write ordinary paragraphs separated by a blank line. Consecutive non-empty lines inside one paragraph preserve their line breaks.

### Headings and inline formatting

```md
# 一级标题
## 二级标题
### 三级标题
#### 四级标题
##### 五级标题
###### 六级标题

**粗体**、__粗体__、*斜体*、_斜体_、~~删除线~~、`行内代码`

[研究链接](https://example.com "可选标题")
```

When front matter has no `title`, the first level-one heading becomes the cover title. Otherwise all headings are body headings. Links are styled for the PNG but are not clickable in the raster output.

### Lists, tasks, quotes, and rules

```md
- 无序列表
  - 嵌套项目
    1. 更深一层

1. 有序列表
2. 第二项

- [x] 已完成
- [ ] 待处理

> 一段引用或旁注。

---
```

Indent nested lists with spaces. Use a blank line after the complete list.

### Tables

```md
| 指标 | 2025年 | 2026Q1 |
|:---|---:|---:|
| 营收 | 617.99亿元 | 约249亿元 |
| 净利润 | 18.75亿元 | 247.62亿元 |
```

Column colons control left, center, or right alignment. Prefer no more than 5 columns and 10 body rows because a table stays on one page. Use `:::metrics` instead when the content is only a label/value list.

### Images

```md
![产线示意图](./images/fab.png "可选图片说明")
```

Put a figure on its own line. Relative paths resolve from the input Markdown file. Local PNG, JPEG, GIF, WebP, SVG, and AVIF files are embedded before rendering; HTTP(S) image URLs are also accepted. The title is used as the caption, falling back to the alt text.

### Code blocks

````md
```javascript
const revenue = 617.99;
console.log(revenue);
```
````

Backtick and tilde fences are supported. Prefer no more than 18 lines per code block.

### Footnotes

```md
这是需要来源的结论。[^source]

[^source]: 数据来源：公司招股说明书。
```

Footnote definitions are collected into a compact note block at the end of the carousel.

### Safe raw HTML

```html
<div class="warning">
  <strong>保留文字排版</strong><br>
  <mark>但移除所有属性</mark>
</div>
```

Safe structural and inline tags such as `div`, `p`, `section`, `blockquote`, headings, lists, `strong`, `em`, `u`, `mark`, `small`, `sub`, `sup`, `kbd`, `code`, `span`, and `br` are retained. All attributes are removed. Scripts, iframes, event handlers, and other executable HTML are never executed and remain escaped text. Prefer Markdown syntax unless raw HTML is necessary.

## Inline marks

```md
{accent}橙金色文字{/accent}
{circle}5 次{/circle}
{wavy}位置真不差{/wavy}
==放一起看才有意思==
**竞争力不行**
```

Keep each `{circle}` or `{wavy}` span short and close every mark on the same paragraph.

## Block directives

### Section heading

```md
:::section
三、一份真实读数：他排第 13，却几乎没被提过
:::
```

### Metrics

Use one `label | value` pair per bullet:

```md
:::metrics
- AI 提及率 | 5%
- 前三推荐率 | 6.47%
- 平均排名 | 第 2.57 位
- 赛道 736 个品牌里 | 第 13 名
:::
```

### Marker conclusion

```md
:::marker
「第 13 名」这个成绩，是在「已经被提到」这个小池子里算出来的。
:::
```

### Closing callout

Use this for the larger pale-yellow conclusion panel normally placed near the bottom of a page:

```md
:::callout
先画地图，再定坐标，
最后才轮到动笔。
:::
```

A closing callout near the bottom of a body page is optional — use it when a closing perspective adds value, skip it when the page already ends with a strong narrative beat. Keep it to one or two short lines. The renderer prefixes the panel with a configurable label (default `AI观点：`) and keeps the whole panel on one page; do not repeat the label in the Markdown content. To change the label, set `callout_label` in front matter (e.g. `callout_label: 划重点`).

### Risk callout

Use this for any risk-related content. The renderer prefixes the panel with `AI提示风险：` and renders it with an orange-red accent to distinguish it from opinion callouts:

```md
:::risk
周期见顶、出口管制收紧、流通盘解锁后抛压集中——三重风险叠加。
:::
```

All risk mentions — whether about past events or future possibilities — must be wrapped in `:::risk`. Do not repeat the label in the Markdown content.

### Lead and source

```md
:::lead
先看一组容易被误读的数据。
:::

:::source
数据来自 Geolix 只读看板，每条均可回溯到原始提问与回答。
:::
```

### Thumbnails

Use this to insert source material preview images at the end of the carousel. The renderer automatically creates a grid layout with a heading and call-to-action text. Just provide the images:

```md
:::thumbnails
![](./source-page1.png)
![](./source-page2.png)
:::
```

Images are arranged in a centered row. Use 1–4 images (2 recommended); they don't need to be legible—the purpose is to hint that more complete content is available.

### Forced page break

```md
:::pagebreak
```

Use this only between complete ideas. Automatic pagination is the default.

## Complete example

```md
---
title: GEO {circle}第二步{/circle} 到底做什么
subtitle: 排名很好，为什么 AI 还是不提你？
kicker: GEO 数据复盘
cover: true
---

:::section
三、一份真实读数：他排第 13，却几乎没被提过
:::

上个月我们把一位 TRON 能量租赁客户接进看板，第 1 份读数是这样的：

:::metrics
- AI 提及率 | 5%
- 前三推荐率 | 6.47%
- 平均排名 | 第 2.57 位
- 赛道 736 个品牌里 | 第 13 名
:::

这 4 个数，==放一起看才有意思==。

平均排名第 2.57 位，说明 AI 一旦提到他，{wavy}位置真不差{/wavy}。可 AI 提及率只有 5%——100 次相关提问里，AI 只想起过他 {circle}5 次{/circle}。

:::marker
「第 13 名」这个好看的成绩，是在「已经被提到」这个小池子里算出来的。
:::

他不是{accent}竞争力不行{/accent}，是{accent}出场次数太少{/accent}。

:::source
数据来自 Geolix 只读看板，每一条都可回溯到原始提问与回答。我们不做数据美化，也不生成不存在的数字。
:::
```
