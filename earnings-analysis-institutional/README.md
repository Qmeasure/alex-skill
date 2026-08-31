# earnings-analysis-institutional

分析一家已覆盖公司刚发布的季报或年报，产出智富界机构版式的中文业绩更新报告（DOCX）和配套预测更新表（Excel）。

## 它和另外两个 skill 的关系

| | 回答什么问题 | 体量 | 什么时候用 |
|---|---|---|---|
| `initial-coverage-institutional` | 这家公司值不值得买 | 25–45 页 | 首次覆盖，从零建立认知 |
| **本 skill** | 这一期业绩改变了什么 | 14–18 页 | 财报刚发，已有旧预测可对照 |

版式完全一致：两个 skill 共用同一份 `references/Word文档格式标准.md`：每页右上角 logo + 「智富界」、首页左摘要右投资数据双栏、正文 12.7cm 窄栏而图表占满 18.6cm 版心、蓝白配色加四色图表板、图表与表格铺满宽度不孤立居中。

差别在装什么：

- **首页右栏**换成业绩更新的元素：评级带变动方向、目标价写「旧 → 新」或「维持」、报告期、收入与 EPS 相对一致预期的幅度，第 9 位是 12 个月**原始收盘价**股价图（首次覆盖版那里是相对表现图）
- **第 2 页**从 Key data 换成业绩速览：三口径对照表 + 分部拆分 + 指引对照与预测更新
- **章节骨架**换成业绩更新的逻辑链：总览 → 拆解 → 指引 → 逻辑更新 → 预测与估值
- **不做**三层标的池、分位统计、SOTP、足球场图、公司沿革、行业空间，那些是首次覆盖的活

## 与上游 earnings-analysis 的差异

本 skill 改造自 `codex-financial-cn/skills/earnings-analysis`，主题和主要功能不变。改的是：

- **自包含**。上游依赖插件根目录的 `CN_DOCX_OUTPUT_CONTRACT.md`、`DATA_QUERY_ORDER_CN.md` 等一批合同文件，本 skill 不引用任何外部相对路径，取数与输出规则全部内联
- **交互流对齐首次覆盖版**：Step 0 环境检查 → 五阶段推进 → 前置校验 → 脚本门验收
- **体量从 8–12 页扩到 14–18 页**，图表从 8–12 张扩到 18–25 张（机构版式的封面页和业绩速览页先占掉 2 页）
- **Excel 从可选改为必需**，但只做轻量预测更新表（四张 sheet），不重建完整三表模型
- **原「数据源发现记录 Gate」降级**为 `_data` 底稿开头的「数据源盘点」一节，摘要进报告的「来源与参考资料」
- 保留上游两条硬性要求：业绩公告日必须 ≤3 个月、一致预期必须取公告前快照

## 五个阶段

| 阶段 | 名称 | 产物 |
|---|---|---|
| 1 | 业绩数据采集与超预期分析 | `[公司]_业绩速览_[日期].md` |
| 2 | 预测更新 | `[公司]_预测更新_[日期].xlsx` |
| 3 | 估值与评级更新 | 估值稿 `.md` + 估值 sheet 并入阶段 2 Excel |
| 4 | 图表生成 | `[公司]_图表_[日期].zip` |
| 5 | 报告组装 | `[公司]_[季度]_业绩更新_[日期].docx` |

## 目录

```
SKILL.md                          入口：五阶段、执行标准、写作硬规则、验收
README.md                         本文件
assets/
  报告模板与版式.md                首页三区、业绩速览页、章节骨架、体量门槛
  研报写作规范.md                  怎么写、怎么不写出 AI 味
  去AI味案例库.md                  改前/改后对照
  质量检查清单.md                  分阶段逐项核对
  brand/                          logo 与二维码
references/
  Word文档格式标准.md              版式机制（与首次覆盖版同一份）
  阶段1-业绩采集与超预期分析.md
  阶段2-预测更新.md
  阶段3-估值与评级更新.md
  阶段4-图表生成.md
  阶段5-报告组装.md
  同业对照.md                      本期同业横向对照（可选章节）
  估值方法学.md                    增量估值的理论参考
scripts/
  check_environment.py             Step 0 汇总入口
  anti_fabrication_lint.py         反编造 lint
  checks/                          单项环境检查 + 渲染门 + 工作代号门
anthropic_skills/                  内嵌的 docx / xlsx 工具 skill
```

## 交付前的四道脚本门

```bash
python scripts/check_environment.py                                  # Step 0
python scripts/checks/check_render.py <pdf> --earnings               # 渲染门，五项断言
python scripts/checks/check_internal_labels.py <docx> <xlsx> <脚本>   # 工作代号门
python scripts/anti_fabrication_lint.py <脚本> <_data 底稿> <稿件>     # 反编造
```

渲染门的五项：页数区间 14–18、无空白页、首页元素齐全、首页未溢出（第 2 页必须以「业绩速览」开头）、文字未越出版心。前四项都是踩过坑之后补上的：空白页和首页溢出复发过两次，文字越界是嵌套表格宽度算错 80 DXA 把内容顶出版心 4pt，肉眼只看得出「文字被挤压」，说不出差多少。

## 安装

```bash
rsync -a --exclude '.DS_Store' earnings-analysis-institutional/ ~/.claude/skills/earnings-analysis-institutional/
```

装完新开会话才会出现在可调用清单里。
