# initial-coverage-institutional-tex

`initial-coverage-institutional` 的 LaTeX 版。研究方法、五阶段流程、智富界机构版式都和 Word 版一致，区别在排版工具和交付物：

- 交付一个多文件 tex 工程、它编译出的 PDF，以及联动 Excel、底稿 CSV、图表 PNG
- 全流程不产出任何 Word 或 Markdown 文件，阶段稿件也是 tex，底稿是 CSV
- 表格和关键数字由脚本从 Excel 导出成 tex，正文不手写表格、不手敲评级目标价
- 编译引擎是 Tectonic；中文用思源宋体，西文和数字用 ctex 默认字体

## 和 Word 版对齐到什么程度

用两份 Word 版的真实报告做了回归：铂科新材（已上市，37 页）和宇树科技（Pre-IPO，26 页），各用 TeX 重排一遍，和 Word 导出的 PDF 逐页比。

- 页数：两份都和 Word 版相同
- 铂科新材：37 页里 30 页的数字锚点纵向偏移在 1.5bp 以内；另外 7 页整体差一行正文，原因是 Latin Modern 的数字比思源宋体窄，某一段少折一行
- 宇树科技：原稿有几处没按规范排（表格标题在表下、表格带竖线、半宽图单独居中），TeX 版按规范排，这几页之后的流动随之错开

这套对齐靠三件事：

1. **单位用 bp**：Word 的磅是 1/72 英寸，等于 TeX 的 `bp`，不是 `pt`
2. **行高模型**：单倍行高 = 1.867 × 字号，行顶到基线 = 1.371 × 字号，多倍行距只加在基线下方，段间距取上段段后和下段段前的较大值。这是在 Word PDF 上量出来的，推算值和实测差不到 0.3bp
3. **字形尺寸吸附**：Word for Mac 导出时字形尺寸吸附到 0.24bp 的整数倍（9bp 画成 9.12bp），断行要一致就得用同样的尺寸

## 目录

| 文件 / 目录 | 作用 |
|---|---|
| `SKILL.md` | 入口：触发条件、五阶段、取数与输出标准、验收 |
| `references/TeX版式标准.md` | 版式数值与交付前检查，取代 Word 版的格式标准 |
| `references/阶段1–5`、`估值方法学`、`同业对照` | 各阶段做法，产物改成 tex / CSV |
| `assets/tex-template/` | 报告工程模板：`main.tex`、`style/zfj-report.sty`、`front/`、`chapters/`、`drafts/draft.tex` |
| `assets/brand/` | logo 与二维码 |
| `assets/*.md` | 报告模板与版式、写作规范、去 AI 味案例库、质量检查清单 |
| `anthropic_skills/xlsx/` | 内嵌 xlsx 工具 Skill（重算用 `recalc.py`） |
| `scripts/new_report.py` | 从模板新建报告工程 |
| `scripts/export_excel_to_tex.py` | Excel「报告数字」「报告表格」→ `data/keyfigures.tex`、`tables/*.tex` |
| `scripts/zfj_tex.py` | 转义与表格渲染，导出脚本调用 |
| `scripts/build_report.py` | 导出 → 编译 → 全部检查，一条命令 |
| `scripts/checks/` | 环境检查、渲染检查、版式量测、第一人称、无 Word / Markdown 文件 |

## 用法

```bash
python scripts/check_environment.py                      # Step 0
python scripts/new_report.py <报告目录>                   # 建工程
python scripts/build_report.py <报告目录> --draft drafts/公司研究_<日期>.tex
python scripts/build_report.py <报告目录> --name <公司>_首次覆盖_<日期> [--pre-ipo]
```

`build_report.py` 任一项 FAIL 不交付。

## 本地安装

```bash
rsync -a --exclude '.DS_Store' --exclude '__pycache__' initial-coverage-institutional-tex/ ~/.claude/skills/initial-coverage-institutional-tex/
```

之后说「用 tex 给某公司写一份首次覆盖」「出一份 tex 版机构研报」就能触发。
