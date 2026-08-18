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
- 并行运行首次读者审计和事实与视觉审计；两个 sub-agent 均不得接收最后一页。
- 最后一页是渲染器模板，只由验证与渲染流程检查。
- 3×4 是独立产品规则。普通提示词重构不得改变其定义或映射标准，除非任务明确要求。

## 权威位置

| 内容 | 权威位置 |
|---|---|
| 触发条件、运行流程、HITL、联网时机、交付步骤 | `SKILL.md` |
| 事实边界、封面、叙事和文风 | `references/narrative-style.md` |
| Markdown、front matter 和自定义指令 | `references/content-format.md` |
| 主题选择 | `references/themes.md` |
| 3×4 定义与映射 | `references/3x4-methodology.md` |
| 首次读者上下文关联审计 | `references/context-audit-checklist.md` |
| 事实、来源、3×4 证据与视觉审计 | `references/audit-checklist.md` |
| 正文内容用途及禁止案例 | `references/content-purpose-blacklist.md` |
| 防御性否定的写作与审计边界 | `references/defensive-negation-examples.md` |
| 格式、页数、字体、尺寸和渲染硬约束 | `scripts/` 与 `test/` |

运行文件可以简短引用关键约束，但不要复制另一文件的解释、完整规则或实现细节。

## 修改检查

1. 先确定新规则的唯一归属，再编辑。
2. 搜索同义要求、反向重述和过时引用；删除不会改变合格 Agent 行为的句子。
3. 让 `SKILL.md` 只保留编排所需信息；让 reference 只承担表中对应职责。
4. 能由脚本返回稳定诊断的问题，不在多处枚举错误条件和实现参数。
5. 更新运行规则后检查 `agents/openai.yaml` 是否仍与技能用途一致。
6. 不从运行提示词暴露本维护文件。
7. 打包或安装后确认隐藏目录仍随 SKILL 携带。

## 验证

按改动风险运行相关检查，不默认运行完整测试套件：

```bash
python "<skill-creator-dir>/scripts/quick_validate.py" .
node --test test/validation.test.mjs
npm run check
```

提示词发生实质变化时，再用一个真实任务做独立前向检查，观察 Agent 是否能找到信源、只做缺口驱动联网、停顿一次并完成验证与审计。
