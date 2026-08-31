---
name: long-image
description: "将 PDF、DOCX、Markdown、网页、图片等任意来源的长内容转为 1080px 竖版研究长图。内容含具体标的的投资建议、评级、估值或目标价时生成 Internal/External 双版，否则生成单版；无法判断时先询问用户。打印/文档结构图请使用 $document-structure-map。"
---

# 线图

将长文档转为适合手机阅读和转发的 1080px 宽竖向长图，语言使用简体中文。

## 前置依赖

本技能依赖 **Inkstone** 提取源文档内容。步骤 0 检查依赖时会确认 Inkstone 是否已安装；若未安装，停止执行并提示用户在终端手动运行：

```
npx skills add zzzdajb/inkstone
```

安装完成后重新开始。

- `single`：单版。用于中性行业/公司/知识整理。只生成 `input.png`。
- `dual`：双版。用于包含投资建议、评级、估值等内容的研究。生成 `input-internal.png` 与 `input-external.png`。

## 输出目录

所有产物统一放在工作目录下的 `线图/` 文件夹中，步骤 1 开始时创建。

```
workspace/                    ← 用户工作目录（动态）
  report.pdf                  ← 源文件（用户提供）
  线图/                       ← 步骤 1 创建
    source_content.md (.html) ← 步骤 1（Inkstone 提取）
    _source_images/           ← 步骤 1（Inkstone 提取，PDF/DOCX）
    input.json                ← 步骤 3 创建
    _page_thumbs/             ← 步骤 4 缩略图
    input.png / input.html    ← 步骤 5 最终输出
```

## 工作流程

按顺序执行以下步骤，每步的详细说明在对应文件中：

| 步骤 | 文件 | 说明 |
|---|---|---|
| 0 | `steps/00-check-deps.md` | 检查运行环境与依赖 |
| 1 | `steps/01-read-source.md` | 使用 Inkstone 提取源文档，阅读并建立论证骨架 |
| 2 | `steps/02-output-policy.md` | 判断并记录 single/dual 输出策略 |
| 3 | `steps/03-create-json.md` | 基于 `source_content` 按 schema 创建结构化 JSON |
| 3a | `steps/03a-audit-json.md` | **Sub-agent** — JSON 合规审计，建议性 |
| 3b | `steps/03b-audit-data.md` | **Sub-agent** — 数据可靠性审计：溯源比对 + 联网核实 |
| 4 | `steps/04-thumbnails.md` | 生成缩略图：`python scripts/generate_thumbnails.py`（渲染器强制检查） |
| 4a | — | **用户触发** — 设置生成日期：`python scripts/set_date.py <input.json>`（默认当天，无需传参）。仅当用户显式要求指定日期时候才根据用户要求加参数 `--date YYYY-MM-DD`，否则不传参数。 |
| 5 | `steps/05-render.md` | Pipeline 一键执行：`python scripts/pipeline.py`（检查→渲染→验收） |
| 6 | `steps/06-verify.md` | 目视确认排版与可读性（pipeline 已执行自动化验收） |
| 6a | `steps/06a-audit-external.md` | **Sub-agent** — External 成品终审，建议性，仅 dual |

## 参考资料

| 文件 | 用途 |
|---|---|
| `references/schema.md` | JSON 字段定义与约束（步骤 3 使用） |
| `references/external-compliance.md` | External 外部版合规过滤规则（步骤 2、3 使用） |
| `references/layout-standards.md` | 内容与版式标准（步骤 3、6 使用） |
| `assets/brand.json` | 品牌配置（二维码、底栏文案等） |

## 环境约束

- 优先使用 `uv` 管理 Python 依赖；仅当环境中没有 `uv` 时回退到 `pip`。
- Windows 环境下 Shell 优先级：Git Bash > PowerShell 7 > PowerShell 5 > Cmd。
- 运行 Python 脚本前，先设置 `PYTHONUTF8=1`（PowerShell: `$env:PYTHONUTF8="1"`，Bash: `export PYTHONUTF8=1`），否则中文内容会因系统默认编码变为乱码。
- 禁止使用 `type`、`Get-Content` 或无编码参数的 shell 命令读取含中文的源文件；应使用 Read 工具或 Python `open(path, encoding="utf-8")`。
