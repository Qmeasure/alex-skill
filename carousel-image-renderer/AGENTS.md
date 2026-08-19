# carousel-image-renderer 维护指引

这是一个通用 SKILL，用于把本地信源制作成智富界中文金融轮播图。

## 维护原则

- 修改仓库前，先完整阅读 [`.maintenance/MAINTENANCE.md`](.maintenance/MAINTENANCE.md)；维护决策、规则归属和验证要求以它为准。
- 单纯执行 SKILL 时只遵循 `SKILL.md`，不要读取或暴露 `.maintenance/`，也不要从运行文件链接维护说明。
- 每条规则只保留一个权威位置。修改前先用 `rg` 搜索重复、同义、反向和过时表述，再在正确位置做最小改动。
- 能由脚本稳定检查的约束放在 `scripts/` 并用 `test/` 固定，不在提示词中重复实现细节。
- 不顺带改变 3×4、固定品牌配色、审计职责或休眠功能；除非任务明确要求。

## 主要目录

- `SKILL.md`：触发、流程与交付编排。
- `references/`：写作、格式、3×4 与审计规范。
- `scripts/`、`assets/`：处理、验证、渲染与固定模板。
- `test/`：产品契约与回归测试。
- `agents/openai.yaml`：客户端展示元数据。

具体权威边界见维护说明，不在这里重复。

## 验证

按改动风险运行最小充分检查，不默认执行完整测试套件：

```bash
npm run check
node --test test/<相关测试文件>.test.mjs
```

技能结构或元数据变化时，再运行外部 `skill-creator/scripts/quick_validate.py`。审计契约发生实质变化时，按维护说明完成真实双包、双独立审计验证。

提交前检查 `git diff`，确认没有无关改动或重复规则，并确保 `.maintenance/` 随 SKILL 分发但不进入运行提示词。
