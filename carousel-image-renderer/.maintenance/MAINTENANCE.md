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
- 渲染器固定使用蓝、白、近黑一套品牌配色，不向 Agent 或输入稿暴露主题选择。
- `scripts/prepare-audit.mjs` 全自动生成上下文审计包和事实、证据与视觉审计包；Main Agent 只把对应文件夹交给两个并行 sub-agent。
- 两个审计 sub-agent 只定位和解释问题，不提供解决方案、改写或优化建议。
- 上下文审计只负责首次读者理解与叙事连续性；事实、证据与视觉审计负责事实、来源、3×4 证据、防御性否定、callout/risk 和视觉；同一类别只有一个负责人。
- 修复后按实际影响重跑审计，未受影响的 `PASS` 保持有效；分页变化同时影响两项审计。
- 最后一页（末页/endcard）由渲染器模板生成，只由验证与渲染流程检查。
- `--endcard guided` 是休眠功能：因二维码可能触发平台限流而暂时搁置，故意不写入运行提示词——Agent 不知道就不会自行启用。产品层面重新启用前，维护时不得将其文档化。
- 3×4 是独立产品规则。普通提示词重构不得改变其定义或映射标准，除非任务明确要求。

## 权威位置

| 内容 | 权威位置 |
|---|---|
| 触发条件、运行流程、HITL、联网时机、交付步骤 | `SKILL.md` |
| 事实边界、封面、叙事和文风 | `references/narrative-style.md` |
| Markdown、front matter 和自定义指令 | `references/content-format.md` |
| 固定品牌配色 | `assets/theme.css` |
| 3×4 定义与映射 | `references/3x4-methodology.md` |
| 首次读者上下文关联审计 | `references/context-audit-checklist.md` |
| 事实、来源、3×4 证据与视觉审计 | `references/audit-checklist.md` |
| 防御性否定的写作判断示例 | `references/defensive-negation-examples.md`（写作规范在 narrative-style.md，审计口径在 audit-checklist.md） |
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

审计提示或审计包契约发生实质变化时，把真实生成的两个文件夹分别交给两个独立 sub-agent，检查它们能否只凭文件夹完成各自审计并按约定格式只报告问题。
