---
name: carousel-image-renderer
description: Turn one or more local HTML, DOCX, or PDF sources on any newsworthy topic into a source-grounded Chinese financial-media carousel for 智富界. Use when an agent needs to discover local source files, extract them with Inkstone, research a verifiable market or investment relevance when needed, write for broad financial readers, and render a branded 1080×1440 multi-page PNG set with mandatory cover metadata, at least seven body pages, risk disclosure, source thumbnails, automatic pagination, and deterministic validation.
---

# 智富界轮播图

把广题材信源制作成面向泛金融读者的完整图片集。事实可以来自原始材料和经过预审的联网补充；不得编造或掩盖来源之间的冲突。

## 要求

- 使用本地 HTML、DOCX 或 PDF 信源；多份信源地位平等。
- 本地信源为最高依据，直接采用其内容；外部资料只作补充。
- Front matter 显式提供非空 `title`。
- 启用封面。
- 正文禁用“你”。
- 至少包含一个非空 `:::risk`。
- 至少渲染 7 页正文，且总页数至少 9 页。
- 以非空 `:::thumbnails` 结束全文。
- 仅在验证和渲染均成功后交付。

上述可机械判断的要求以脚本结果为准。

## 外部 SKILL 契约

本流程依赖 Inkstone 和 qu-ai-wei：

- **Inkstone**：把 `source-manifest.json` 中每个 `inkstoneInputs` 路径逐一交给 Inkstone，以其返回的 Markdown 路径为准。本流程负责选题、改写和缩略图。
- **qu-ai-wei**：初稿完成后以 embedded mode 调用并使用其终稿。调用时要求保留 front matter、Markdown 指令、表格、链接、图片路径、代码、事实和数字；终稿继续遵守本 SKILL 的格式与品牌要求。

步骤 1 确认两项 SKILL 均可用。缺失时停止并提示用户手动安装：

```bash
npx skills add zzzdajb/inkstone
npx skills add https://github.com/LifelongLazyLearner/qu-ai-wei
```

两项依赖均通过对应 SKILL 调用。

## 运行模式

- **HITL（默认）**：保留角度确认和封面三选一两个检查点。用户表示无偏好时使用推荐项继续。
- **yolo**：仅当用户显式要求“yolo”或“全自动”时启用，跳过检查点并由 Agent 选择推荐项。

## 工作流程

### 1. 检查环境并准备信源

所有文本文件使用 UTF-8。依次运行：

```bash
python "<skill-dir>/scripts/preflight.py"
node "<skill-dir>/scripts/source-prep.mjs" --workspace "<workspace>" --json
```

`source-prep.mjs` 负责信源准备：

- 自动创建并优先扫描 `<workspace>/信源/`；目录为空时非递归扫描工作区根目录。
- 按“同目录、同名主干”归组；每组按 `HTML > DOCX > PDF` 选择正文，按 `PDF > DOCX > HTML` 生成缩略图。
- 输出 `<workspace>/视频图/source-manifest.json`；其中 `inkstoneInputs` 交给 Inkstone，`thumbnailMarkdown` 放在最终 Markdown 末尾，最多包含 4 张缩略图。
- 信源内容和有效缩略图未变化时复用上次结果；需要重建时添加 `--force`。

若返回 `E_SOURCE_REQUIRED`，请用户把文件放入脚本已创建的 `信源/` 后重跑。其他错误按错误对象的 `action` 修复并重跑 `source-prep.mjs`。

### 2. 提取并分析全部信源

对 manifest 中每个 `inkstoneInputs` 路径分别调用 Inkstone，阅读其返回的结构化 Markdown。多份材料共同参与分析，不根据文件名擅自设定主次。

确定：

- 原始标题、作者或机构、时间和文档类型；
- 核心事实、数据、观点、风险和材料之间的差异；
- 信源语言，以及是否存在翻译腔风险；
- 与市场、行业、企业、资产价格或消费成本的直接或间接关系。

在 `<workspace>/视频图/editorial-brief.md` 创建内部编辑摘要，只写 `主体`、`选定角度` 和 `要点`。先记录会进入正文或约束写作的 `[本地]` 要点；风险和多信源差异写进相关要点。不要写完整信源摘要。

### 3. 按需联网补充并预审

以下情况默认联网补充：

- 原始材料不足以支撑 7 页正文；
- 需要建立一条有证据的泛金融因果链；
- 需要背景、案例、最新数据或对照观点来帮助读者理解。

只使用高置信度来源。把候选事实、链接、支持内容和访问日期先写入 `<workspace>/视频图/web-research.md`，不得直接写入终稿。启动独立 sub-agent 做事实预审，并把每条候选事实的结论和一句话理由写回同一文件，分别标记为“预审：通过/拒绝”和“理由：……”。只有标记为“通过”的内容才能进入 `editorial-brief.md` 和正文。

通过预审的外部事实可以自然融入叙事，无需逐段标记来自哪份材料。联网资料只用于补充背景、案例和泛金融因果链，不用于核验或纠正本地信源。外部资料与本地信源不一致时，仍以本地信源为最高优先级；只有差异本身影响理解时，才说明口径、时间或观点差异。找不到可靠证据时保留新闻价值，不强行制造投资结论。

若进行了联网补充，把通过预审且确定采用的内容作为 `[外部]` 要点追加到 `editorial-brief.md`；链接与预审详情仍留在 `web-research.md`。

### 4. 确认角度

HITL 模式下，改写前提供 3 个在核心问题或泛金融关系上不同的内容角度，每个包括：

- 一组暂定的 `kicker` / `title` / `subtitle`，用于说明角度，不作为最终封面方案；
- 一句话卖点；
- 该角度与泛金融读者的关系。

标出 1 个推荐角度，并用一句话说明推荐理由。

用户选定内容角度后，将其写入 `editorial-brief.md` 再开始写作。yolo 模式直接采用推荐角度并写入摘要。

### 5. 编写并去 AI 味

正式写作前完整阅读 [references/narrative-style.md](references/narrative-style.md) 和 [references/content-format.md](references/content-format.md)；选择主题时阅读 [references/themes.md](references/themes.md)。

先读取 `editorial-brief.md`，再在 `<workspace>/视频图/` 按叙事规范编写 UTF-8 Markdown。摘要只用于保持主体、角度和要点一致，不替代本地信源或通过预审的外部资料。首次渲染前不加 `:::pagebreak`；只有确认存在不可接受的叙事断点时才少量使用。把 manifest 的 `thumbnailMarkdown` 原样放在全文最后。

完成初稿后调用 qu-ai-wei，并按“外部 SKILL 契约”传入覆盖条件。将返回终稿写回 Markdown。

### 6. 选择封面

HITL 模式下，根据选定角度和最终正文重新编写 3 组 `kicker` / `title` / `subtitle`，标出 1 组推荐方案并用一句话说明推荐理由。让用户直接按文字选择，再把选定文案写回最终 Markdown。不要把步骤 4 中未选角度的暂定文案作为封面候选。yolo 模式使用推荐方案。

### 7. 验证格式与文风

先运行硬验证：

```bash
node "<skill-dir>/scripts/validate.mjs" <input.md> --json
```

验证器一次返回全部问题。按稳定错误码、位置、期望值和 `action` 修复，直到 `valid: true`。

再运行机械文风检查：

```bash
python "<skill-dir>/scripts/lint.py" <input.md> --json
```

qu-ai-wei 负责生成阶段的改写，lint 再独立复检可机械识别的残留模式；提示词约束不能代替脚本检查。lint 使用稳定告警码，逐项修复或明确接受；告警本身不等同于硬失败。处理后重新运行硬验证。

### 8. 正式渲染

```bash
node "<skill-dir>/scripts/render.mjs" <input.md> --output "<workspace>/视频图" --json
```

渲染器输出编号 PNG 和 `manifest.json`，默认使用不含二维码的 native 导流卡；仅在明确需要二维码截图引导时使用 `--endcard guided`。可用 `--theme classic|finance|editorial|tech` 和 `--endcard native|guided` 覆盖。

正式渲染采用事务式输出：新版本完整通过检查后才替换旧 PNG 和 manifest；失败会保留上一版好产物。若本次命令返回非零退出码，停在本步骤，不读取或审计目录中现有的 PNG 和 manifest；按错误对象的 `action` 修复并重新渲染。步骤 9 只使用本次成功渲染生成的 manifest。不要把命令接入会掩盖退出码的管道。

### 9. 独立审计

启动独立 sub-agent，给它最终 Markdown、PNG、必要的结构化信源和 [references/audit-checklist.md](references/audit-checklist.md)。优先按渲染 manifest 的 `auditTargets` 读取封面、最密正文页、risk/callout 页、低填充警告页和导流页，不再人工猜测页码。

若审计要求返工：

- 改正文措辞：重新执行 `qu-ai-wei → validate → lint → render`。
- 只改 Markdown 结构：重新执行 `validate → lint → render`。
- 只改脚本或样式：重新执行 `render → 视觉审计`。

每次交付前硬验证必须全绿。

### 10. 交付

从渲染 manifest 读取并交付 PNG 目录、`bodyPages` 和 `totalPages`；不要交付内部 HTML、`editorial-brief.md`、封面临时目录或审计草稿。
