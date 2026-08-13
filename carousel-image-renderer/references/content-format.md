# Markdown 渲染协议

本文件只定义输入格式。选题、文风、联网和合规规则见 [narrative-style.md](narrative-style.md)。

## 目录

- [Front matter](#front-matter)
- [原生 Markdown](#原生-markdown)
- [行内标记](#行内标记)
- [块级指令](#块级指令)

## Front matter

每份输入必须以 front matter 开头：

```md
---
title: 一份公司研究
subtitle: 两个数字，看懂成本变化
kicker: 公司公告 2026年8月
cover: true
theme: finance
---
```

字段：

- `title`：必填，单行；只用于封面，支持行内标记。
- `subtitle`：可选封面副标题。
- `kicker`：可选封面标签；默认“图文报告”。
- `cover`：必须为 `true`，省略时默认为 `true`。设为 `false` 会返回 `E_COVER_REQUIRED`。
- `theme`：`classic`、`finance`、`editorial` 或 `tech`，默认 `classic`。
- `callout_label`：可选，覆盖 `:::callout` 的默认“AI观点”前缀。
- `source_pages`：可选正整数，用于导流页的“完整内容预览 共X页”。

每个字段只占一行。`title` 缺失或为空会返回 `E_TITLE_REQUIRED`；正文 H1 不会成为封面标题。

品牌页脚固定为左侧“智富界”、右侧“看懂AI，用好AI，投资AI”，不要在输入中增加品牌字段。

## 原生 Markdown

段落之间留空行。同一段内连续非空行保留换行。

### 标题与行内格式

正文使用二至六级标题：

```md
## 二级标题
### 三级标题

**粗体**、*斜体*、~~删除线~~、`行内代码`
[研究链接](https://example.com "可选标题")
```

链接会显示样式，但 PNG 不可点击。

### 列表、任务、引用和分隔线

```md
- 无序项目
  - 嵌套项目

1. 有序项目
2. 第二项

- [x] 已完成
- [ ] 待处理

> 引用或旁注。

---
```

### 表格

```md
| 指标 | 2025年 | 2026Q1 |
|:---|---:|---:|
| 营收 | 617.99亿元 | 249亿元 |
```

表格不会跨页拆分。超过 5 列或 10 行会产生警告。

### 图片

```md
![产线示意图](./images/fab.png "可选图片说明")
```

图片必须独占一行。相对路径以输入 Markdown 所在目录为基准。支持 PNG、JPEG、GIF、WebP、SVG 和 AVIF；HTTP(S) 图片也可使用。title 优先作为图注，没有 title 时使用 alt。

### 代码

````md
```javascript
const revenue = 617.99;
```
````

支持反引号和波浪线围栏。超过 18 行会产生警告。

### 脚注

```md
这是一项带注释的结论。[^source]

[^source]: 公司公告中的统计口径。
```

定义会汇总成末尾注释块。

### 安全 HTML

允许常见结构和行内标签：`div`、`p`、`section`、`blockquote`、标题、列表、`strong`、`em`、`u`、`mark`、`small`、`sub`、`sup`、`kbd`、`code`、`span`、`br`。属性会被移除；脚本、iframe 和事件处理器不会执行。优先使用 Markdown。

## 行内标记

```md
{accent}橙金色文字{/accent}
{circle}关键数字{/circle}
{wavy}手绘下划线{/wavy}
==高亮文字==
```

每个标记在同一段内闭合。未配对会返回 `E_INLINE_MARK_UNBALANCED`。

## 块级指令

块级指令由开始行、内容和独立的 `:::` 结束行组成。

### `:::section`

```md
:::section
成本曲线开始变化
:::
```

### `:::lead`

```md
:::lead
利润率的拐点，往往先藏在成本里。
:::
```

### `:::metrics`

每行使用 `标签 | 值`：

```md
:::metrics
- 营收 | 249亿元
- 净利润 | 18.75亿元
- 毛利率 | 34%
:::
```

### `:::marker`

```md
:::marker
产能利用率决定新增投入能否转化为利润。
:::
```

### `:::callout`

```md
:::callout
估值能否维持，还要看利润兑现速度。
:::
```

渲染器自动添加 `AI观点：`；不要在内容中重复标签。

### `:::risk`

```md
:::risk
需求回落和新增产能释放可能同时压低价格。
:::
```

渲染器自动添加 `AI提示风险：`。每份轮播图至少需要一个非空 risk；缺失会返回 `E_RISK_REQUIRED`。

### `:::source`

只用于正文特有的统计口径：

```md
:::source
这里的市场份额按出货量而非收入计算。
:::
```

来源署名由封面 kicker 承载。不要在正文重复“整理自某机构”等填充归因，也不要出现“信源”一词。

### `:::thumbnails`

```md
:::thumbnails
![](./信源缩略图/report/page-01.png)
![](./信源缩略图/report/page-02.png)
:::
```

规则：

- 必须非空且只能出现一次。
- 必须是最后一个内容块。
- 导流页最多放 4 张；使用 `source-manifest.json` 的 `thumbnailMarkdown`，不要手工选择。
- 缩略图只承担原始资料预览和引流作用，不要求正文级可读性。

### `:::pagebreak`

```md
:::pagebreak
```

只在完整语义之间使用。自动分页是默认行为。正文页填充率低于 70% 会失败，70%–75% 会警告；末尾正文页和导流页豁免。
