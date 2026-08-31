# 步骤 6：验收成图

## 自动化检查

运行验收脚本：

```
python scripts/verify_output.py input.json --output-dir outputs
```

脚本自动检查：
- 输出文件是否齐全（single 一套，dual 两套）
- PNG 宽度是否为 1080px
- 受众标签是否正确（internal 有"内部研究版"，external/single 无标签）
- External HTML 敏感词扫描
- 顶部/底部二维码是否一致

返回码 `0` 表示自动检查全部通过。

## 目视确认

脚本无法覆盖的项目，需要目视确认：

- 每张表的全部列都在正文宽度内，表头与单元格在手机等比例缩放后仍可读，没有横向溢出或被裁切。
- 观点卡排版紧凑、层次分明，竖线结构完整。
- 底部品牌栏中文字和二维码完整可见。
- 真实二维码实测可扫码。

版式细节参见 `references/layout-standards.md`。
