# 步骤 5：渲染与验收

## Pipeline 一键执行

完成步骤 4（缩略图）和步骤 4a（设置日期）后，用 pipeline 脚本一次性完成 检查→渲染→验收：

```
python scripts/pipeline.py 线图/input.json
```

Pipeline 依次执行：
1. 缩略图检查（`check_thumbnails.py`）
2. 渲染（`render_mobile_share.py`）
3. 输出验收（`verify_output.py`）

任一步骤失败即停止。全部通过后仍建议目视确认排版（见步骤 6）。

## 前置条件

Pipeline / 渲染脚本启动时会自动检查，任一不通过即拒绝：

1. **日期**：`meta.date` 必须已通过 `set_date.py` 设置。Agent 不得自行填写日期——必须由用户显式要求后运行：
   ```
   python scripts/set_date.py 线图/input.json                     # 默认当天，无需传参
   python scripts/set_date.py 线图/input.json --date 2025-03-15   # 仅用户要求指定日期时
   ```
2. **缩略图**：`docx_preview` 字段和对应缩略图文件必须存在。

## 单独运行渲染

如需跳过 pipeline 单独渲染：

```
python scripts/render_mobile_share.py 线图/input.json
```

默认 `--mode auto`，根据 JSON 中的 `output_policy` 自动选择：
- `single` → 输出 `input.png`
- `dual` → 输出 `input-internal.png` 与 `input-external.png`

## 调试与覆盖

- `--mode single|both|internal|external`：仅用于明确覆盖或调试，不要用来绕过输出策略判断。
- `--html-only`：仅生成 HTML，跳过 PNG。仅用于调试，正式交付不得使用。
