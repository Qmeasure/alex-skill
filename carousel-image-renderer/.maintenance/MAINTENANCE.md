# carousel-image-renderer 维护说明

本文件随 SKILL 分发，但不属于运行提示词。不要从 `SKILL.md`、`references/` 或 `agents/openai.yaml` 链接本文件；只有维护任务应显式读取它。

## 设计目标

- 把提示词视为可执行规范：短、单义、可验证。
- 同一规则只有一个权威位置，避免复制后独立演化。
- 只保留会改变 Agent 决策或产物的文字。
- 在生成前简要说明关键约束，把机械细节交给脚本和测试。

## 流程决策

- 本地信源是主要编辑依据；联网只补足选定角度的明确缺口。
- 联网材料由执行 Agent 判断，只记录实际采用的事实，不设置候选事实预审。
- 默认只有一次 HITL，同时选择内容角度和暂定封面；yolo 模式跳过。
- 最终封面可以润色，但不能改变用户选择的角度和标题承诺。
- Main Agent 起草前必须重申 AIGC 风格关键约束；独立 AIGC 风格 sub-agent 负责以 qu-ai-wei embedded mode 清理初稿，并在每批审计修订后执行最终文字，Main Agent 只决定修改要求和验收结果。
- AIGC 风格 sub-agent 只接收当前 Markdown 和 Main Agent 批准后的修改要求，不读取信源或原始审计报告；每篇最多调用三次，没有读者可见文字修改时不调用。
- 渲染器提供两套固定品牌风格：白、荧光青柠、近黑的 `new` 为默认值；原蓝、白、近黑风格仅在用户明确要求 `old` 时使用。风格是渲染参数，不进入 Markdown front matter。
- `:::methodology-3x4` 由渲染器生成固定介绍文案；Agent 只决定是否插入并撰写后续场景与入场方式映射。
- `scripts/prepare-audit.mjs` 全自动生成上下文审计包和事实、证据与视觉审计包；首轮 Main Agent 只把对应文件夹交给两个并行 sub-agent。
- 两个审计 sub-agent 只定位和解释实质问题，不提供解决方案、改写、优化建议或交付结论；所有输出都只是建议，由 Main Agent 独立裁决。
- 上下文审计的成品依据只包括渲染后逐页可见文字，负责首次读者理解、叙事连续性、内部来源或指令泄露、悬空指代和无事实增量的证据免责声明；固定 3×4 文案只检查插入位置和衔接，不检查或改写内容。
- 事实、证据与视觉审计负责事实、来源、3×4 场景与入场方式证据和 callout/risk；固定 3×4 文案不与文章信源核验，视觉只检查封面层级和正文内容图片相关性，AIGC 风格由独立编辑 sub-agent 负责。
- overflow、坏图、字体加载、尺寸、页序和填充率由渲染器与脚本检查，不重复交给逐篇 LLM 审计。
- 审计包只向事实、证据与视觉 sub-agent 提供封面标题内容区和正文内容图片的裁剪图，不暴露整页模板；同一类别只有一个负责人。
- 审计最多两轮：第一轮完整双审，第二轮只按修改影响复审已处理问题、直接回归和新增重大风险；未受影响的审计不重跑，分页变化同时影响两项审计。
- `PASS` 只表示该 sub-agent 本轮没有建议，不是交付批准；是否修改、接受现状、驳回或停止交付只由 Main Agent 决定，第二轮后不得继续发起审计。
- 最后一页（末页/endcard）由渲染器模板生成，只由验证与渲染流程检查。
- `--endcard guided` 是休眠功能：因二维码可能触发平台限流而暂时搁置，故意不写入运行提示词——Agent 不知道就不会自行启用。产品层面重新启用前，维护时不得将其文档化。
- 3×4 是独立产品规则。普通提示词重构不得改变其定义或映射标准，除非任务明确要求。

## 权威位置

| 内容 | 权威位置 |
|---|---|
| 触发条件、运行流程、HITL、联网时机、交付步骤 | `SKILL.md` |
| 事实边界、封面、叙事和文风 | `references/narrative-style.md` |
| Markdown、front matter 和自定义指令 | `references/content-format.md` |
| 固定品牌风格与选择 | `assets/theme.css` 保存 `old` 基础样式，`assets/theme-new.css` 保存默认 `new` 覆盖样式，选择逻辑与诊断在 `scripts/render.mjs` 和 `test/render.test.mjs` |
| 3×4 使用条件与具体映射 | `references/3x4-methodology.md` |
| 3×4 固定读者文案 | `assets/methodology-3x4.mjs` |
| 首次读者上下文关联审计 | `references/context-audit-checklist.md` |
| 事实、来源、3×4 证据与视觉审计 | `references/audit-checklist.md` |
| AIGC 风格与防御性废话 | 写作规范在 `references/narrative-style.md`，判断示例在 `references/defensive-negation-examples.md` |
| 审计包构建、隔离与清洗 | `scripts/prepare-audit.mjs` 与 `test/audit-prep.test.mjs` |
| 格式、页数、字体、尺寸和渲染硬约束 | `scripts/` 与 `test/` |

运行文件可以简短引用关键约束，但不要复制另一文件的解释、完整规则或实现细节。非权威文件只引用权威文件，不复述规则细节。

## 修改检查

1. 先确定新规则的唯一归属，再编辑。
2. 修改任何规则前，全仓搜索其关键词、同义要求、反向重述和过时引用，列出所有复述点并同步修改或删除；删除不会改变合格 Agent 行为的句子。
3. 让 `SKILL.md` 只保留编排所需信息；让 reference 只承担表中对应职责。
4. 能由脚本返回稳定诊断的问题，不在多处枚举错误条件和实现参数。
5. 更新运行规则后检查 `agents/openai.yaml` 是否仍与技能用途一致。
6. 不从运行提示词暴露本维护文件。
7. 打包或安装后确认隐藏目录仍随 SKILL 携带。

## 验证

按改动风险运行相关检查，不默认运行完整测试套件：

```bash
python "<skill-creator-dir>/scripts/quick_validate.py" .  # 外部 skill-creator 技能的脚本，不在本仓库
node --test test/audit-prep.test.mjs
npm run check
```

审计提示或审计包契约发生实质变化时，把真实生成的两个文件夹分别交给两个独立 sub-agent，检查上下文包不含图片、事实与视觉包只含限定图片，并确认两者能只凭文件夹按约定格式报告建议，不作修改、交付或严重度的最终裁决。

AIGC 风格提示或编排发生实质变化时，把一份真实 AI 初稿交给全新上下文的 sub-agent，确认它调用 qu-ai-wei、清理无信息量的防御性表达、保留事实与 Markdown，并只返回完整终稿。
