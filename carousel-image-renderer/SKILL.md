---
name: carousel-image-renderer
description: Turn one or more local HTML, DOCX, or PDF sources on any newsworthy topic into a source-grounded Chinese financial-media carousel for 智富界. Use when an agent needs to discover local source files, extract them with Inkstone, research a verifiable market or investment relevance when needed, write for broad financial readers, and render a branded 1080×1440 multi-page PNG set with mandatory cover metadata, at least seven body pages, risk disclosure, source thumbnails, automatic pagination, and deterministic validation.
---

# 智富界轮播图

把广题材信源制作成面向泛金融读者的完整图片集。事实可以来自原始材料和经过预审的联网补充；不得编造或掩盖来源之间的冲突。

## 要求

- 使用本地 HTML、DOCX 或 PDF 信源；多份信源地位平等。
- 本地信源在本流程中具有最高可信度。默认接受其内容，不要求外部交叉验证；外部资料不得用于质疑、降级、删除或纠正本地信源。
- Front matter 显式提供非空 `title`，不得用正文 H1 回退。
- 封面必须启用。
- 正文不得出现“你”。
- 至少包含一个非空 `:::risk`。
- 至少渲染 7 页正文；封面和导流页另计，总页数至少 9 页。
- 最后一个内容块必须是非空 `:::thumbnails`。
- 验证或渲染返回非零退出码时不得交付，也不得声称产物已完成。

上述可机械判断的要求由脚本强制。不要只靠自查。

## 外部 SKILL 契约

本流程依赖两个外部 SKILL，不复述或依赖它们的内部规则编号：

- **Inkstone**：Agent 把 `source-manifest.json` 中每个 `inkstoneInputs` 路径逐一交给 Inkstone。读取 Inkstone 返回的 Markdown 路径；不要假设文件名、缓存位置或复制产物。Inkstone 负责结构化提取，不负责选题、改写或缩略图。
- **qu-ai-wei**：初稿完成后以 embedded mode 调用，只取终稿。调用时明确要求保留 front matter、Markdown 指令、表格、链接、图片路径、代码、事实和数字，并且不得引入“你”。本 SKILL 的格式与品牌约束优先。

步骤 1 确认两项 SKILL 均可用。缺失时停止并提示用户手动安装：

```bash
npx skills add zzzdajb/inkstone
npx skills add https://github.com/LifelongLazyLearner/qu-ai-wei
```

不得跳过依赖或用脚本冒充 SKILL 调用。

## 运行模式

- **HITL（默认）**：保留角度确认和封面三选一两个检查点。用户拒绝选择时使用推荐项继续。
- **yolo**：仅当用户显式要求“yolo”或“全自动”时启用，跳过检查点并由 Agent 选择推荐项。

## 工作流程

### 1. 检查环境并准备信源

所有文本文件使用 UTF-8。依次运行：

```bash
python "<skill-dir>/scripts/preflight.py"
node "<skill-dir>/scripts/source-prep.mjs" --workspace "<workspace>" --json
```

`source-prep.mjs` 是信源准备的唯一入口：

- 自动创建 `<workspace>/信源/`。
- 优先扫描 `信源/`；为空时非递归扫描工作区根目录。
- 按“同目录、同名主干”归为一个逻辑信源；不同主干视为多份信源。
- 正文提取选择 `HTML > DOCX > PDF`。
- 缩略图选择 `PDF > DOCX > HTML`；失败时按顺序降级并记录原因。
- PDF 取前 4 页；DOCX 生成 4 张预览；本地 HTML 生成 2 张预览。图片固定为 1240×1754。
- 多信源时轮流选择各组缩略图，最终 `thumbnailMarkdown` 最多放 4 张。
- 输出 `<workspace>/视频图/source-manifest.json`，其中 `inkstoneInputs` 可直接交给 Inkstone，`thumbnailMarkdown` 可直接放进最终 Markdown。
- 信源内容和有效缩略图均未变化时复用上次结果；只有明确需要重建时才加 `--force`。

若返回 `E_SOURCE_REQUIRED`，脚本已经创建好 `信源/`；请用户放入文件后重跑。其他错误按错误对象的 `action` 修复，不要临时手搓缩略图。

### 2. 提取并分析全部信源

对 manifest 中每个 `inkstoneInputs` 路径分别调用 Inkstone，阅读其返回的结构化 Markdown。多份材料共同参与分析，不根据文件名擅自设定主次。

确定：

- 原始标题、作者或机构、时间和文档类型；
- 核心事实、数据、观点、风险和材料之间的差异；
- 信源语言，以及是否存在翻译腔风险；
- 与市场、行业、企业、资产价格或消费成本的直接或间接关系。

### 3. 按需联网补充并预审

以下情况默认联网补充：

- 原始材料不足以支撑 7 页正文；
- 需要建立一条有证据的泛金融因果链；
- 需要背景、案例、最新数据或对照观点来帮助读者理解。

只使用高置信度来源。把候选事实、链接、支持内容和访问日期先写入 `<workspace>/视频图/web-research.md`，不得直接写入终稿。启动独立 sub-agent 做事实预审；只有通过的内容才能进入正文。

通过预审的外部事实可以自然融入叙事，无需逐段标记来自哪份材料。联网资料只用于补充背景、案例和泛金融因果链，不用于核验或纠正本地信源。外部资料与本地信源不一致时，仍以本地信源为最高优先级；只有差异本身影响理解时，才说明口径、时间或观点差异。找不到可靠证据时保留新闻价值，不强行制造投资结论。

### 4. 确认角度

HITL 模式下，改写前提供 3 个在核心问题或泛金融关系上不同的内容角度，每个包括：

- 一组暂定的 `kicker` / `title` / `subtitle`，用于说明角度，不作为最终封面方案；
- 一句话卖点；
- 该角度与泛金融读者的关系。

标出 1 个推荐角度，并用一句话说明推荐理由。

等用户选定内容角度后再写。yolo 模式直接采用推荐角度。

### 5. 编写并去 AI 味

正式写作前完整阅读 [references/narrative-style.md](references/narrative-style.md) 和 [references/content-format.md](references/content-format.md)；选择主题时阅读 [references/themes.md](references/themes.md)。

在 `<workspace>/视频图/` 按叙事规范编写 UTF-8 Markdown，以步骤 2、3 建立的证据集为事实边界。首次渲染前不加 `:::pagebreak`；只有确认存在不可接受的叙事断点时才少量使用。把 manifest 的 `thumbnailMarkdown` 原样放在全文最后。

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

正式渲染采用事务式输出：新版本完整通过检查后才替换旧 PNG 和 manifest；失败会保留上一版好产物。不要把命令接入会掩盖退出码的管道。

### 9. 独立审计

启动独立 sub-agent，给它最终 Markdown、PNG、必要的结构化信源和 [references/audit-checklist.md](references/audit-checklist.md)。优先按渲染 manifest 的 `auditTargets` 读取封面、最密正文页、risk/callout 页、低填充警告页和导流页，不再人工猜测页码。

若审计要求返工：

- 改正文措辞：重新执行 `qu-ai-wei → validate → lint → render`。
- 只改 Markdown 结构：重新执行 `validate → lint → render`。
- 只改脚本或样式：重新执行 `render → 视觉审计`。

每次交付前硬验证必须全绿。

### 10. 交付

从渲染 manifest 读取并交付 PNG 目录、`bodyPages` 和 `totalPages`；不要交付内部 HTML、封面临时目录或审计草稿。
