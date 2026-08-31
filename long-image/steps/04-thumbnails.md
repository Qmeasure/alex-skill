# 步骤 4：生成研报页面缩略图

缩略图的作用是吸引阅读的用户加群，不可跳过。

:::warning 强制阻断
渲染脚本（步骤 5）会检查 `docx_preview` 字段和缩略图文件是否存在。**缺少缩略图时渲染会被拒绝。**
:::

## 按源格式处理

### PDF 源文件（自动模式）

```
python scripts/generate_thumbnails.py 线图/input.json --source report.pdf
```

脚本自动用 `pdf2image` 转换前 N 页，写入 `_page_thumbs/`，并回填 JSON 的 `docx_preview` 字段。

### DOCX 源文件（自动模式）

```
python scripts/generate_thumbnails.py 线图/input.json --source report.docx
```

脚本自动通过 LibreOffice headless 将 DOCX 导出为 PDF，再用 `pdf2image` 转图。

### HTML、图片、访谈记录等其他格式（导入模式）

Agent 自行生成缩略图图片后，使用导入模式：

```
python scripts/generate_thumbnails.py 线图/input.json --import img1.png img2.png ...
```

脚本负责将图片复制到 `_page_thumbs/`、统一重命名、回填 JSON。Agent 不需要手动管理文件和 JSON 字段。

### 存疑情况处理

如果Agent无法自行判断生成什么图片合适，直接阻断并且询问用户。

## 可选参数

- `--pages N`：展示的缩略图数量，默认 4。
- `--thumb-width N`：嵌入时缩放宽度（像素），默认 240。

详见 `references/schema.md` 的"研报预览横条"章节。
