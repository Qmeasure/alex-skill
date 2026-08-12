# 微信公众号 HTML 规则

## 正文文件

正文是一个纯 HTML 片段：

```html
<section style="max-width:100%;box-sizing:border-box;background:#FFFFFF;color:#1A1A1A;font-family:inherit;">
  ...
</section>
```

正文只能有一个根 `<section>`，不能包含 `DOCTYPE`、`html`、`head`、`body`。
根元素必须通过 `background` 或 `background-color` 声明背景，取值只能是 `#FFFFFF`，或仅由 `#FFFFFF` 与 `#F2F6FC` 构成的原生 CSS 渐变；不能用透明、继承值或无法判断亮度的写法代替。

## 标签和属性

正文可使用：

- 结构：`section`、`p`、`h2`、`h3`、`h4`、`blockquote`；
- 列表：`ul`、`ol`、`li`；
- 表格：`table`、`thead`、`tbody`、`tr`、`th`、`td`；
- 行内：`span`、`strong`、`em`、`a`、`br`、`hr`。

限制：

- 结构元素必须有非空 `style` 属性。
- 所有可见文字必须放在 `<span leaf="">` 内。
- `span` 只允许 `leaf` 和 `style`；链接只允许 `href` 和 `style`。
- 表格单元格可以使用 `colspan`、`rowspan` 和 `style`。
- 不使用 `class`、`id`、`data-*`、事件属性和自定义属性。

禁止：

- `h1`。文章标题在公众号后台的标题栏填写，正文最高标题层级是 `h2`；
- `img`、`picture`、`source`、SVG、Canvas；
- `video`、`audio`、`iframe`、`object`、`embed`；
- `style`、`script`、`link`；
- `div`、`button`、`form`、`input`；
- `src`、`srcset` 和任何事件属性。

## 内联 CSS

样式要保证粘贴稳定。字体从公众号编辑器继承；颜色、字号、间距和边框照抄
[visual-system.md](visual-system.md) 的片段表，不在这里另行拟定。

该文档同时规定两条与粘贴稳定性相关的硬规则：

- 任何声明 `background` 或 `background-color` 的元素必须同时声明 `color`；
- 颜色不带透明度，只有 `box-shadow` 和 `text-shadow` 可以用半透明黑。

图表可以使用：

- 百分比 `width` 和确定的 `height`；
- `display:block`、`inline-block`、`table`、`table-cell`；
- `vertical-align`、`text-align`；
- `border`、`border-width`、`border-style`、`border-color`；
- 色板内的颜色，用法见 [visual-system.md](visual-system.md)；
- 克制的 `box-shadow` 或 `text-shadow`；
- `overflow`、`word-break`、`box-sizing`。

根背景可以是纯色 `#FFFFFF`，也可以是仅由 `#FFFFFF` 与 `#F2F6FC` 构成的 `linear-gradient(...)`、`radial-gradient(...)` 等原生 CSS 渐变。表头、图表条形等局部可以使用深蓝底加白字，校验器只对根背景做取值限制。

不得使用：

- 外部字体和字体文件；
- CSS 变量；
- `url()`、data URI、`background-image`、`list-style-image`；
- `position:absolute|fixed|sticky`、`float`；
- Grid、动画、媒体查询和关键帧；
- 滤镜；
- 依赖浏览器脚本计算的布局。

## 文字包裹

正确：

```html
<p style="margin:0 0 1em;line-height:1.75;color:inherit;">
  <span leaf="">正文文字</span>
</p>
```

文字不能直接位于 `p`、标题、表格单元格、链接或列表项内。标点也属于可见文字，应放在 `span[leaf]` 中。

## 链接

- 使用完整的 `http://` 或 `https://` 地址。
- 链接文字保留原文，不把 URL 改写成新标题。
- 图片来源只有图片地址时，可以把原题注或替代文字链接到该地址，但不能嵌入图片。
- 禁止 `javascript:`、data URI 和相对路径。

## 预览页

预览页是完整 HTML 文档，可以包含工具栏、按钮、文档级 CSS 和复制脚本。以下条件必须同时满足：

- 正文位于单独的 `gzh-content` 节点；
- 按钮、状态提示和脚本位于正文节点之外；
- 复制函数只选择正文节点的子内容；
- 正文校验器只检查 `{原文件名}_公众号正文.html`，不检查预览外壳。
