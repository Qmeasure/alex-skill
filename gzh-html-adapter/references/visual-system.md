# 蓝白视觉系统

这份文档是配色、字号和间距的唯一真相。生成正文时照抄下面的片段，只替换文字和数值，不得自行拟定色值、字号或间距。

整篇成稿的观感参照 [../assets/sample-body.html](../assets/sample-body.html)（正文片段），要直接在浏览器里看效果就打开 [../assets/sample-preview.html](../assets/sample-preview.html)（带复制按钮的预览页，由前者生成，改了样张要重新跑 `build_preview.py`）。

`scripts/validate_gzh_html.py` 按本文档硬校验，越界报错。改动本文档必须同步改校验器和样张。

## 色板

| Token | 值 | 用途 |
|---|---|---|
| 深蓝 | `#1B3A6B` | h2/h3 文字、表头背景、图表标题、strong、KPI 数值 |
| 主蓝 | `#2B6EF2` | h2 左竖条、链接、一级系列条形、进度条填充 |
| 中蓝 | `#6FA0E8` | 二级系列、引用块左条 |
| 浅蓝底 | `#F2F6FC` | 引用块底、表格偶数行、图表轨道、KPI 标签格 |
| 边框蓝 | `#D8E2F0` | 表格线、图表容器边框、分隔线 |
| 正文黑 | `#1A1A1A` | 正文、h4、单元格文字 |
| 次要灰 | `#666666` | 单位、来源、注释、分组块字段名 |
| 弱化灰 | `#9A9A9A` | 次级分隔、弱化标注 |
| 警示红 | `#C0392B` | 只用于负值与未达标 |
| 琥珀 | `#E0A458` | 第四系列、对照项 |
| 白 | `#FFFFFF` | 根背景、表格奇数行、图表容器底、深底上的文字 |

色板与 `initial-coverage-institutional` 同源，研报与公众号推文视觉一致。

**图表系列取用顺序**：`#2B6EF2` → `#1B3A6B` → `#6FA0E8` → `#E0A458`。超过四个系列时保留数据表，不画图。`#C0392B` 只标负值与未达标，不参与轮转。

**两条硬规则**

- 任何声明 `background` 或 `background-color` 的元素必须同时声明 `color`。微信 iOS 深色模式会反转背景却不反转继承来的文字，浅蓝底上会出现白字。
- 颜色不带透明度。只有 `box-shadow` 和 `text-shadow` 可以用半透明黑。

## 字号与间距

| 元素 | font-size | line-height | margin |
|---|---|---|---|
| h2 | 19px | 1.4 | `1.6em 0 .6em` |
| h3 | 17px | 1.5 | `1.4em 0 .5em` |
| h4 | 16px | 1.6 | `1.2em 0 .4em` |
| 正文 p | 16px | 1.75 | `0 0 1em` |
| 引用块 | 15px | 1.7 | `1.2em 0` |
| 表格 | 14px（5–6 列 13px） | 默认 | `1.2em 0` |
| 来源与注释行 | 13px | 1.6 | `0 0 1em` |

### 文章标题不进正文

公众号后台有独立的标题栏，标题在那里填，正文里不写。正文出现 `<h1>` 会被校验器直接拦下；用大字号加粗段落把标题再写一遍同样不允许，效果是读者在标题栏下面又看到一遍同样的话。

标题层级映射：

- 正文最高标题层级固定为 `h2`；
- 原文开头若有唯一一个 `h1` 且就是文章标题，摘掉它，写进交付说明供粘贴到标题栏；
- 取原文实际用到的最高标题层级映射为 `h2`，其余依次顺延，最深到 `h4`；
- 深于 `h4` 的层级改为加粗首句的普通段落，不新增标题级别。

## 片段表

**根容器**

```html
<section style="max-width:100%;box-sizing:border-box;background:#FFFFFF;color:#1A1A1A;font-family:inherit;">
```

根背景只能是 `#FFFFFF`，或仅由 `#FFFFFF` 与 `#F2F6FC` 构成的原生 CSS 渐变。

**标题**

```html
<h2 style="margin:1.6em 0 .6em;padding-left:10px;border-left:4px solid #2B6EF2;font-size:19px;line-height:1.4;font-weight:700;color:#1B3A6B;"><span leaf="">小标题</span></h2>

<h3 style="margin:1.4em 0 .5em;font-size:17px;line-height:1.5;font-weight:700;color:#1B3A6B;"><span leaf="">小标题</span></h3>

<h4 style="margin:1.2em 0 .4em;font-size:16px;line-height:1.6;font-weight:700;color:#1A1A1A;"><span leaf="">小标题</span></h4>
```

**正文、强调、链接**

```html
<p style="margin:0 0 1em;font-size:16px;line-height:1.75;color:#1A1A1A;word-break:break-word;"><span leaf="">正文</span></p>

<span leaf="" style="color:#1B3A6B;font-weight:700;">加粗强调</span>
<span leaf="" style="font-style:italic;">斜体</span>
<a href="https://example.com/x" style="color:#2B6EF2;text-decoration:underline;word-break:break-all;"><span leaf="">链接文字</span></a>
```

**引用块**

```html
<blockquote style="margin:1.2em 0;padding:.8em 1em;background:#F2F6FC;color:#1A1A1A;border-left:3px solid #6FA0E8;font-size:15px;line-height:1.7;box-sizing:border-box;"><p style="margin:0;font-size:15px;line-height:1.7;color:#1A1A1A;"><span leaf="">引文</span></p></blockquote>
```

**列表**

```html
<ul style="margin:0 0 1em;padding-left:1.4em;color:#1A1A1A;">
  <li style="margin:0 0 .5em;font-size:16px;line-height:1.75;color:#1A1A1A;"><span leaf="">条目</span></li>
</ul>
```

`ol` 用同一套值，只换标签。

**分隔线与来源行**

```html
<hr style="border:none;border-top:1px solid #D8E2F0;margin:1.6em 0;" />

<p style="margin:0 0 1em;font-size:13px;line-height:1.6;color:#666666;"><span leaf="">数据来源：……</span></p>
```

## 表格

```html
<table style="width:100%;border-collapse:collapse;table-layout:fixed;margin:1.2em 0;font-size:14px;color:#1A1A1A;">
  <thead style="color:#FFFFFF;">
    <tr style="color:#FFFFFF;">
      <th style="background:#1B3A6B;color:#FFFFFF;font-weight:700;text-align:left;padding:.6em .5em;border:1px solid #D8E2F0;"><span leaf="">表头</span></th>
    </tr>
  </thead>
  <tbody style="color:#1A1A1A;">
    <tr style="color:#1A1A1A;">
      <td style="background:#FFFFFF;color:#1A1A1A;padding:.55em .5em;border:1px solid #D8E2F0;vertical-align:top;"><span leaf="">奇数行</span></td>
    </tr>
    <tr style="color:#1A1A1A;">
      <td style="background:#F2F6FC;color:#1A1A1A;padding:.55em .5em;border:1px solid #D8E2F0;vertical-align:top;"><span leaf="">偶数行</span></td>
    </tr>
  </tbody>
</table>
```

斑马纹写在 `td` 上，不写在 `tr` 上，微信编辑器对行级背景的保留不稳定。

### 宽表策略

公众号正文宽约 355px。按列数分档：

- **≤4 列**：`font-size:14px`，padding 照上面的值。
- **5–6 列**：`font-size:13px`，单元格 padding 收紧到 `.45em .35em`，靠 `table-layout:fixed` 换行。
- **>6 列**：转纵向分组块。每个数据行输出一个 `section`，块内首行是行标题，其后每个字段一行。

```html
<section style="border:1px solid #D8E2F0;background:#FFFFFF;color:#1A1A1A;margin:.8em 0;padding:.7em .9em;box-sizing:border-box;">
  <p style="margin:0 0 .5em;font-size:15px;line-height:1.5;font-weight:700;color:#1B3A6B;"><span leaf="">行标题</span></p>
  <p style="margin:0 0 .3em;font-size:14px;line-height:1.6;color:#1A1A1A;"><span leaf="" style="color:#666666;">字段名：</span><span leaf="">值</span></p>
</section>
```

转分组块只改排列方式：表头文案、单位、脚注、行列顺序、数值精度全部保留，不合并字段，不省略空值。

## 图表

结构与数据规则见 [native-charts.md](native-charts.md)，本节只定容器与用色。

```html
<section style="border:1px solid #D8E2F0;background:#FFFFFF;color:#1A1A1A;margin:1.2em 0;padding:.9em;box-sizing:border-box;">
  <p style="margin:0 0 .2em;font-size:15px;line-height:1.5;font-weight:700;color:#1B3A6B;"><span leaf="">图表标题</span></p>
  <p style="margin:0 0 .8em;font-size:13px;line-height:1.6;color:#666666;"><span leaf="">单位：……</span></p>
  <p style="margin:0 0 .3em;font-size:14px;line-height:1.6;color:#1A1A1A;"><span leaf="">类别　数值</span></p>
  <section style="width:100%;height:14px;background:#F2F6FC;margin:0 0 .8em;box-sizing:border-box;color:#1A1A1A;">
    <section style="width:64%;height:14px;background:#2B6EF2;color:#FFFFFF;box-sizing:border-box;"><span leaf=""> </span></section>
  </section>
  <p style="margin:0;font-size:13px;line-height:1.6;color:#666666;"><span leaf="">数据来源：……</span></p>
</section>
```

- 轨道一律 `#F2F6FC`，填充按系列顺序取色。
- 负值用 `#C0392B`，条长按绝对值算，同时保留方向文字（「下降 14.2」），数值文字也用警示红。
- 进度图：轨道 `#F2F6FC` 加 `1px solid #D8E2F0` 边框，已达部分 `#2B6EF2`，未达部分不填色。
- KPI：标签格 `#F2F6FC` 底、`#666666` 字，数值格 `#FFFFFF` 底、`#1B3A6B` 字、18px 加粗。
- 时间线：两列表格，左列 28% 宽、`#F2F6FC` 底、`#1B3A6B` 加粗日期，右列白底事件。
