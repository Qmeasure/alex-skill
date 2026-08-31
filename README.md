# SKILLS

一套面向投研、文档处理、写作质检和信息可视化的 AI Skills。选择 Skill 时，先看你要交付什么，再看输入材料是什么。

## 快速选择

| 你要做的事 | 使用 Skill | 主要产物 | 不要选它做什么 |
|---|---|---|---|
| 对一家公司做机构级首次覆盖，研报和估值模型一起交付 | [`equity-research-obsidian`](./equity-research-obsidian/SKILL.md) | Obsidian Markdown、Excel 估值模型、`input.json`、决策 memo | 不适合只想导出 Word 或只查一个数据 |
| 写一份完整的券商风格首次覆盖深度研报 | [`initial-coverage-advanced`](./initial-coverage-advanced/SKILL.md) | DOCX 研报、联动 Excel 模型 | 不适合只做简化损益模型 |
| 写一份智富界机构版式的首次覆盖深度研报 | [`initial-coverage-institutional`](./initial-coverage-institutional/SKILL.md) | DOCX 研报（25–45 页 / 40–70 图表）、联动 Excel 模型 | 不做业绩更新；只要通用券商版式选 `initial-coverage-advanced` |
| 分析一家已覆盖公司刚发布的季报或年报 | [`earnings-analysis-institutional`](./earnings-analysis-institutional/SKILL.md) | DOCX 业绩更新（14–18 页 / 18–25 图表）、预测更新 Excel | 不做首次覆盖，也不适合尚未覆盖的公司 |
| 已有定性研究，只需要把业务判断做成估值模型 | [`valuation-model`](./valuation-model/SKILL.md) | Excel 估值模型、`input.json`、决策 memo | 不适合纯定性研究或单纯套 DCF 模板 |
| 给公司做五年净利润、成本和盈亏平衡预测 | [`one-page-model`](./one-page-model/SKILL.md) | 一页式 Excel 损益模型 | 不做 DCF、可比估值或精细三表联动 |
| 把 Obsidian Markdown 导出成 Word | [`obsidian-to-docx`](./obsidian-to-docx/SKILL.md) | `.docx` | 不研究、不建模、不补写内容 |
| 复盘上周推荐的股票 | [`pitch-review`](./pitch-review/SKILL.md) | 带行情图的 Markdown 复盘报告 | 不做全市场选股、首次覆盖或估值建模 |
| 把投资研讨录音转成 Gamma/PPT 大纲 | [`gamma-ppt-outline`](./gamma-ppt-outline/SKILL.md) | 可导入 Gamma 的 Markdown 大纲 | 不输出会议纪要，也不处理没有转录文本的音频 |
| 转录并剪掉播客口误，审核后交付剪映草稿 | [`podcast-editor`](./podcast-editor/SKILL.md) | 剪映音频草稿 | 逐字审核页只是审核工具；不处理视频，也不导出成品音频或 FCPXML |
| 把长文档整理成适合打印或插入报告的结构图 | [`document-structure-map`](./document-structure-map/SKILL.md) | 纵向结构图 HTML/长图 | 不适合手机转发长图 |
| 把研究材料做成微信、公众号或手机长图 | [`long-image`](./long-image/SKILL.md) | 1080px 竖版长图，必要时 Internal/External 双版 | 不适合打印版结构图 |
| 把文本做成一张逻辑树思维导图 | [`text-to-mindmap`](./text-to-mindmap/SKILL.md) | 竖向逻辑树 PNG | 不输出 XMind/FreeMind，也不做横向或放射状导图 |
| 把文章、报告或数据贴做成多页轮播图片卡片 | [`carousel-image-renderer`](./carousel-image-renderer/SKILL.md) | 1080×1440 PNG 卡片组和 `manifest.json` | 不输出交互网页，也不改写事实 |
| 核查一篇已有文稿里的数字和事实 | [`doc-data-verify`](./doc-data-verify/SKILL.md) | 6 字段核查表、可确认的修正稿 | 不适合没有事实数据的纯润色 |
| 在回答前核验当前数据、职位、价格、法规或产品信息 | [`verify-before-answer`](./verify-before-answer/SKILL.md) | 带来源、时间和置信度的回答 | 这是通用核验纪律，不是文稿核查器 |
| 把中文改得更自然，去掉 AI 味和翻译腔 | [`de-ai-flavor-zh`](./de-ai-flavor-zh/SKILL.md) | 改写后的中文文本 | 不适合英文、纯数据查询或事实核查 |
| 修改微信公众号文章：核事实、修结构、清元话和改稿痕迹、同步 HTML 跑校验 | [`wechat-article-revise`](./wechat-article-revise/SKILL.md) | 改后的 md 正文、同步过的公众号 HTML、校验与预览产物 | 不适合英文、未成稿的选题构思或纯事实查询 |
| 为另一个 AI 写执行任务的 prompt | [`directional-prompt-writer`](./directional-prompt-writer/SKILL.md) | 方向性 prompt | 不适合写给人执行的流程文档 |
| 让 AI 或用户围绕一个方案持续追问、锁定决策 | [`grill-me`](./grill-me/SKILL.md) | 多轮质询对话 | 不生成方案，也不提供降级方案或 mock 数据 |

## 按需求找入口

### 投研与财务模型

- **“研报 + 估值模型一起做”**：用 `equity-research-obsidian`。它是 Obsidian 输出主线，模型结果是报告估值数字的唯一来源。
- **“写深度研报，最终交 Word”**：用 `initial-coverage-advanced`。它按五个阶段完成公司研究、盈利预测、估值、图表和 DOCX 组装。
- **“要智富界机构版式的深度研报”**：用 `initial-coverage-institutional`。五阶段流程与 `initial-coverage-advanced` 相同，差别在版式和门禁：每页 logo 与机构名、首页左摘要右投资数据双栏、正文窄栏而图表占满版心，交付前跑渲染门和版式线条门。
- **“已覆盖的公司刚出财报”**：用 `earnings-analysis-institutional`。只写新增信息：实际值 vs 我方预测 vs 一致预期的三口径对照、差异归因、指引解读、预测与目标价的旧新对照。
- **“已有研报，接着做估值”**：用 `valuation-model`。核心链条是业务驱动量、需求或 TAM、营收、利润、至少两种估值方法、隐含股价。
- **“只想估算五年利润或什么时候盈利”**：用 `one-page-model`。它只做损益预测，不做估值。
- **“把 Markdown 研报转成 Word”**：用 `obsidian-to-docx`。它只转换格式，输入 Markdown 缺内容时回到上游修改。

### 复盘、汇报与内容整理

- **“复盘上周推票”**：用 `pitch-review`。它验证既有推荐是否兑现，不修改原推票，也不替用户重新选股。
- **“录音整理成 PPT/Gamma”**：用 `gamma-ppt-outline`。必须有 `txt` 或 `srt` 转录文本；内容只能来自录音。
- **“剪播客或音频口误”**：用 `podcast-editor`。一个文件按合成音轨处理，多个文件按嘉宾分轨处理；用户逐字确认后生成剪映音频草稿。
- **“一图看懂这份长文档的结构”**：用 `document-structure-map`。重点是论证骨架、证据链、风险和章节关系。
- **“做成手机上看的研究长图”**：用 `long-image`。有针对具体标的的评级、估值、目标价或交易建议时，生成 Internal/External 双版。
- **“做一张思维导图图片”**：用 `text-to-mindmap`。输出固定为竖向逻辑树 PNG。
- **“做多页轮播图文卡片”**：用 `carousel-image-renderer`。输出多张 1080×1440 PNG，支持 `classic`、`finance`、`editorial`、`tech` 主题。

### 写作和核验

- **“这段太 AI 了，改自然点”**：用 `de-ai-flavor-zh`。重点不是换几个词，而是删除空架子、补清因果和机制。
- **“改一下这篇公众号文章”“这个标题没写明白”“完全看不懂”“背景没交代清楚”“这些都不核心”**：用 `wechat-article-revise`。五道检查按顺序过：事实层（数字回溯、优先用被批评材料自身的内部证据）、结构层（标题只写分析手法、段首用分类标签、自创比喻、论证跳过前提、只贴标签不说理、结论章用通用框架、人造分组、条目重叠）、洁净度（元话、改稿痕迹、设问自答、跨章引用、首尾呼应、无关花絮）、句子层（转 `de-ai-flavor-zh`）、交付层（md↔HTML 同步、跑校验、重建预览、手机宽度实测）。
- **“核实这篇文章的数据”**：用 `doc-data-verify`。它逐项核验原文数据，并区分一致、不一致、已过期、缺失、冲突。
- **“现在的价格、职位、政策、版本是多少”**：按 `verify-before-answer` 先查证，再回答。任何当前事实、具体数字或产品 API 信息都不能只凭记忆。
- **“帮我写一个给 Claude/GPT 的 prompt”**：用 `directional-prompt-writer`。写目标、方法、约束和质量标准，不把一个想象中的答案写死。
- **“逼我把方案想清楚”或“grill me”**：用 `grill-me`。它通过连续提问补齐决策树，不接受 Plan B、降级方案或假数据。

## 最容易选错的几组

### 三种首次覆盖 Skill

三者都能做首次覆盖，研究深度同级，差别在交付端和版式：

- 要 Obsidian Markdown，并且报告、估值模型和决策 memo 同目录交付，选 `equity-research-obsidian`。
- 要通用券商风格 DOCX 和联动 Excel，选 `initial-coverage-advanced`。
- 要智富界机构版式（每页 logo 与机构名、首页双栏、蓝白配色、正文窄栏、交付前有脚本门），选 `initial-coverage-institutional`。
- `equity-research-obsidian` 会复用 `initial-coverage-advanced` 的研究、写作和质检规范，但不是两个 Skill 同时独立跑一遍。

### `initial-coverage-institutional` 和 `earnings-analysis-institutional`

版式、配色和门禁脚本是同一套，分工按覆盖阶段：

- 第一次写这家公司，选 `initial-coverage-institutional`。它从公司概况讲起，25–45 页。
- 公司已经覆盖过、这次只是财报出来了，选 `earnings-analysis-institutional`。它只写新增信息，不重复公司背景，14–18 页。
- 公司从没覆盖过却直接用业绩更新，读者会缺上下文，先做首次覆盖。

### `valuation-model` 和 `one-page-model`

- 要回答“业务假设变化后，合理股价或隐含价怎么变化”，选 `valuation-model`。
- 要回答“未来五年利润多少、成本怎么拆、哪一年盈亏平衡”，选 `one-page-model`。
- 前者至少使用两种估值方法；后者只做损益预测，不输出估值结论。

### 三种文档可视化 Skill

- `document-structure-map`：打印或放进报告，关注长文档的论证结构。
- `long-image`：手机和微信转发，固定 1080px 宽，按投资敏感内容决定单版或双版。
- `text-to-mindmap`：一张 PNG 思维导图，固定竖向逻辑树布局。

### 两种社交图文 Skill

- `long-image` 是一张可向下延伸的研究长图，适合完整内容摘要和合规分版。
- `carousel-image-renderer` 是多张固定尺寸卡片，适合文章、报告和数据贴的分页阅读。

### `wechat-article-revise`、`de-ai-flavor-zh` 和 `gzh-html-adapter`

三者都参与公众号文章的交付，分工不重叠，`wechat-article-revise` 是总流程，另外两个是它调用的环节：

- `wechat-article-revise` 管**整条改稿流水线**：核事实 → 修结构 → 清成品脏话 → 转句子层 → 同步 HTML 并校验。
- `de-ai-flavor-zh` 管**句子层**：这句话读起来像不像人写的。对付套话、三段排比、伪分析尾巴、硬翻译词、装饰性比喻。
- `gzh-html-adapter` 管**格式转换**：把定稿 Markdown 转成公众号可粘贴的内联样式 HTML，提供 `validate_gzh_html.py` 和 `build_preview.py`。
- 判断口诀：句子通顺但读者还是不知道这节在讲什么，用 `wechat-article-revise`；意思都懂但读着一股 AI 腔，用 `de-ai-flavor-zh`；文章定稿了只差转 HTML，用 `gzh-html-adapter`。
- 顺序要求：先定结构再抠措辞。结构没定就去改句子，改完的句子会被下一轮结构调整整段删掉。

### `verify-before-answer` 和 `doc-data-verify`

- `verify-before-answer` 面向任何回答：只要涉及当前事实、具体数字、法规、职位、价格、产品功能等，就先查证。
- `doc-data-verify` 面向一篇已有文稿：提取文中的全部事实数据，逐项核查并生成核查表和修正稿。

## 给 AI 的调用规则

1. 先识别最终交付物：报告、模型、Word、图片、PPT 大纲、核查表、改写文本或 prompt。
2. 再检查输入前置：例如 Gamma Skill 需要转录文本，估值模型需要研报或业务数据，Word 导出需要 Markdown。
3. 选择一个主 Skill，不要因为关键词重叠而把所有相关 Skill 都完整执行一遍。
4. 只有在任务确实要求某个后处理产物时，再追加后处理 Skill，例如先生成 Obsidian 报告，再用 `obsidian-to-docx` 导出 Word。
5. 只要回答里包含当前数字、价格、职位、法规、产品版本或其他时效事实，执行 `verify-before-answer` 的核验纪律。
6. 事实核验、模型校验、图像渲染和格式验收都是交付门槛。脚本或视觉检查失败时，不能把产物称为完成。
7. 不同 Skill 的具体流程、依赖、命令和停止条件，以对应目录中的 `SKILL.md` 为准；本 README 只负责快速选入口。

## 维护原则

- 新增 Skill 时，必须在本 README 的“快速选择”表和“按需求找入口”中增加一行。
- 修改 Skill 的触发条件或输出边界时，同步更新本 README，避免导航与实际行为不一致。
- 具体规则只在对应 `SKILL.md` 维护，README 不复制完整流程。
