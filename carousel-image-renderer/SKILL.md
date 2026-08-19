---
name: carousel-image-renderer
description: Create source-grounded Chinese financial-media carousels for 智富界 from local HTML, DOCX, or PDF sources. Use when Codex needs to extract local material, fill explicit research gaps, choose a financial angle, apply the 3×4 methodology when strongly relevant, write and humanize Chinese copy, and render a validated 1080×1440 PNG carousel.
---

# 智富界轮播图

把本地信源改写成面向泛金融读者的智富界图片集。

## 最高要求
严禁修改任何SKILL内容，严格按照SKILL的步骤执行，在没有用户显式要求的情况下，严禁做任何擅自变通。严禁修改任何SKILL文件，所有内容必须使用SKILL规定的产出，YOU CAN ONLY READ AND YOU ARE ALLOWED TO DO NOTHING EXCEPT READ AND EXECUTE WITHOUT HUMAN PERMISSIONS.

## 成品要求

- 以本地信源为主要依据；联网只补足明确缺口。
- 信源只约束事实和口径，不自动成为正文主语；取材来源身份的具体口径以 [叙事与编辑规范](references/narrative-style.md) 为准。
- 成品必须独立成篇；除一般常识外，不依赖信源原文、内部材料、前序对话或方法论文件才能理解。
- 仅在证据充分时显式映射 3×4；先解释 3×4 是什么，再说明对应关系。
- 封面包含非空标题；正文页数以正式渲染结果为准，并须通过渲染器的页数范围检查；禁用“你”和“本文”；全文包含至少一个非空 `:::callout` 和至少一个 `:::risk` 风险披露。
- 全文以非空末页（endcard，即信源缩略图导流页）结束，并使用预设品牌与字体。

脚本会检查格式、页数、字体和渲染结果；全部通过后才能交付。

## 依赖与模式

- 用 Inkstone 提取 `source-manifest.json` 中的每个 `inkstoneInputs`。Inkstone 不可用时说明缺失项并停止。
- 初稿完成后以 embedded mode 调用 qu-ai-wei；保留事实、数字和 Markdown 结构，使用其终稿。qu-ai-wei 不可用时同样说明缺失项并停止，不交付未经润色的初稿。

- **HITL（默认）**：写作前让用户一次选择内容角度和暂定封面。
- **yolo**：仅在用户明确要求“yolo”或“全自动”时跳过选择，直接采用推荐方案。

## 工作流程

### 1. 准备信源

```bash
python "<skill-dir>/scripts/preflight.py"
node "<skill-dir>/scripts/source-prep.mjs" --workspace "<workspace>" --json
```

按命令返回的 `action` 处理错误并重跑。若返回 `E_SOURCE_REQUIRED`，请用户把信源放入脚本创建的 `信源/`。

### 2. 提取并分析

逐一用 Inkstone 提取 manifest 中的文件，按 `inkstoneInputs` 顺序把完整结果保存为 `<workspace>/视频图/inkstone-results/01.md`、`02.md`……并阅读全部结果。完整阅读 [3×4 方法论](references/3x4-methodology.md)，再分析：

- 主体、作者或机构、时间和文档类型；
- 事实、数据、观点、风险及多份材料之间的差异；
- 与市场、行业、企业、资产价格或生活成本的关系；
- 3×4 映射及其证据边界；
- 完成文章所缺的背景、事实或因果环节。

在 `<workspace>/视频图/editorial-brief.md` 记录 `主体`、`3×4 映射`、`研究缺口` 和带 `[本地]` 标记的 `要点`。显式映射时记录方法论要求的五项答案和证据；不显式映射时记录理由。

### 3. 一次确认角度与封面

HITL 模式下提供 3 组方案，每组包含：

- 内容角度；
- 暂定 `kicker`、`title` 和 `subtitle`；
- 一句话卖点及其与泛金融读者的关系。

标出推荐方案和理由。用户无偏好时采用推荐项；yolo 模式直接采用推荐项。把选定角度和暂定封面写入 `editorial-brief.md`。需要让用户看到候选封面效果时，可用仅含 front matter 和必需非空块的骨架稿运行渲染命令并加 `--cover-only`，只输出封面 PNG。

### 4. 按缺口联网

只为选定角度的明确缺口联网，包括：

- 本地材料不足以完整支撑选定角度；
- 角度依赖材料中没有的背景或最新事实；
- 泛金融因果链缺少必要环节；
- 显式 3×4 映射缺少关系证据。

由 Agent 判断来源是否可靠。只把实际采用的外部事实、支持内容、链接和访问日期写入 `<workspace>/视频图/web-research.md`，并作为 `[外部]` 要点加入 `editorial-brief.md`；不记录候选材料或执行独立预审。

### 5. 写作

完整阅读 [叙事与编辑规范](references/narrative-style.md) 和 [Markdown 渲染协议](references/content-format.md)。

根据 `editorial-brief.md` 编写 UTF-8 Markdown。使用本地信源和已记录的外部事实；强相关内容按 3×4 方法论显式映射。优先自动分页，并把 manifest 的 `thumbnailMarkdown` 原样放在全文最后。

可以根据终稿润色暂定封面，但不得改变用户选定的核心角度和标题承诺。完成初稿后调用 qu-ai-wei，将其终稿写回 Markdown。

### 6. 验证并渲染

```bash
node "<skill-dir>/scripts/validate.mjs" <input.md> --json
python "<skill-dir>/scripts/lint.py" <input.md> --json
node "<skill-dir>/scripts/render.mjs" <input.md> --output "<workspace>/视频图" --json
```

修复全部硬错误和 lint 错误；逐项处理或明确接受 lint 告警。

正式渲染因页面填充、溢出或正文页数范围失败时，用相同参数添加 `--debug`；以诊断页和 manifest 中的 `bodyPages` 为准修改正文后重新正式渲染。不得通过重复内容或无意义分页满足页数要求，也不得审计或交付 debug 产物。

### 7. 审计并交付

生成两个相互隔离、自包含的审计文件夹：

```bash
node "<skill-dir>/scripts/prepare-audit.mjs" <input.md> --workspace "<workspace>" --json
```

上下文审计包只包含正式渲染后的逐页可见文字；事实、证据与视觉审计包只提供封面标题内容区和正文内容图片的裁剪图，不提供整页 PNG。

并行启动两个相互独立的 sub-agent，只把脚本返回的对应文件夹交给它：

- 上下文关联审计：`完整读取 <contextDirectory>，按照其中 AUDIT.md 审计并输出结果。`
- 事实、证据与视觉审计：`完整读取 <evidenceDirectory>，按照其中 AUDIT.md 审计并输出结果。`

汇总并成批修复全部 `BLOCKER` 和 `REVISION`，然后重新验证、lint、正式渲染并生成新审计包。按修改影响重跑审计：

- 读者可见文字、顺序、结构、分页或 3×4 解释改变时，重跑上下文关联审计；
- 事实、来源、3×4 证据、callout、risk、图片、视觉或分页改变时，重跑事实、证据与视觉审计。

未受影响的 `PASS` 保持有效。两项审计均为 `PASS` 后交付；末页只由验证、渲染和审计包脚本处理。

交付正式 PNG 目录，以及 manifest 中的 `bodyPages` 和 `totalPages`。
