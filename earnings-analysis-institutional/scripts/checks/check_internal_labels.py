#!/usr/bin/env python3
"""工作代号门：断言交付物里 0 处 beat / miss / seg_A / cons 这类底稿用语。

这一项存在的理由：`_data` 底稿和 Excel 里为了处理方便会用短代号，
读者没读过底稿，看到「seg_A 高于 cons 3.2%」只会一头雾水。它最容易漏在
章节标题、图注、表头和 Excel sheet 名里——这些位置写稿时不当成正文，肉眼扫也容易跳过。

代号只允许留在 `_data` 底稿。DOCX 和 xlsx 都是交付物，都要干净。

**图注是盲区**：图下方的「来源：……」小字如果由 matplotlib 画进 PNG，就是像素不是文字，
这个脚本扫不到。所以生成图表的脚本本身也要一起传进来扫。

用法：
    python check_internal_labels.py 报告.docx 模型.xlsx build_charts.py
    python check_internal_labels.py 报告.docx --show 20
"""

import argparse
import re
import sys
import zipfile
from pathlib import Path

FAILURE = "无法保证交付物中不含底稿工作代号"

# 词边界要求前后不是字母，避免误伤 "beats"、"consumer"、"missing" 这类正常词
def _w(word):
    return re.compile(r"(?<![A-Za-z])" + word + r"(?![A-Za-z])", re.IGNORECASE)


PATTERNS = [
    _w("beat"), _w("miss"),
    _w("cons"), _w("consensus"),
    _w("est"),
    # 分部占位：seg_A / seg1 / 分部1 / 分部A
    re.compile(r"(?<![A-Za-z])seg[_\-]?[A-Za-z0-9](?![A-Za-z])", re.IGNORECASE),
    re.compile(r"分部\s*[A-Za-z0-9]\b"),
    # staging 批次号：staging_20260814 / batch_03
    re.compile(r"(?<![A-Za-z])(staging|batch)[_\-]?\d+", re.IGNORECASE),
    # 列名式：Q3'26A_vs_est、rev_vs_cons
    re.compile(r"_vs_[A-Za-z]+", re.IGNORECASE),
]

REPLACEMENTS = {
    "beat / miss": "高于预期 / 低于预期",
    "cons / consensus": "一致预期",
    "est / 我方est": "本报告此前预测",
    "seg_A / 分部1": "分部的真实披露名称",
    "staging_* / batch_*": "删掉，不进成品",
    "*_vs_est 这类列名": "「vs 本报告预测」",
}

# DOCX 里要扫的部件：正文、页眉页脚（品牌横幅和右栏都在这里）、脚注
DOCX_PARTS = ("word/document.xml", "word/header", "word/footer", "word/footnotes.xml")
# XLSX：sheet 名在 workbook；单元格文字视写法在 sharedStrings 或 worksheet 内联
XLSX_PARTS = ("xl/sharedStrings.xml", "xl/workbook.xml", "xl/worksheets/")


def xml_text(raw):
    """把 OOXML 片段还原成纯文本：段落边界补换行，其余标签去掉。"""
    s = raw.decode("utf-8", "ignore")
    s = re.sub(r"</w:p>|</w:tr>|</si>|<sheet ", "\n\\g<0>", s)
    s = re.sub(r"<[^>]+>", "", s)
    return s


def sheet_names(raw):
    """workbook.xml 的 sheet 名在属性里，去标签会丢，单独抽。"""
    s = raw.decode("utf-8", "ignore")
    return "\n".join(re.findall(r'<sheet[^>]*\sname="([^"]*)"', s))


def scan(path):
    """返回命中列表 [(部件, 行号, 该行内容)]。"""
    hits = []
    if not path.exists():
        return [("<文件不存在>", 0, str(path))]

    suffix = path.suffix.lower()
    if suffix in (".docx", ".xlsx"):
        parts = DOCX_PARTS if suffix == ".docx" else XLSX_PARTS
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if not name.startswith(parts):
                    continue
                raw = z.read(name)
                text = sheet_names(raw) if name == "xl/workbook.xml" else xml_text(raw)
                for i, line in enumerate(text.splitlines(), 1):
                    if any(pat.search(line) for pat in PATTERNS):
                        hits.append((f"{path.name}::{name}", i, line.strip()[:120]))
    else:
        text = path.read_text("utf-8", "ignore")
        for i, line in enumerate(text.splitlines(), 1):
            if any(pat.search(line) for pat in PATTERNS):
                hits.append((path.name, i, line.strip()[:120]))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", help="要检查的 .docx / .xlsx / 图表脚本（也接受纯文本文件）")
    ap.add_argument("--show", type=int, default=10, help="最多打印多少条命中")
    args = ap.parse_args()

    all_hits = []
    for f in args.files:
        all_hits += scan(Path(f))

    if not all_hits:
        print(f"PASS  工作代号门：{len(args.files)} 个交付物中 0 处底稿用语")
        return 0

    print(f"FAIL  {FAILURE}：命中 {len(all_hits)} 处")
    for part, line_no, line in all_hits[: args.show]:
        print(f"  {part} 第 {line_no} 行：{line}")
    if len(all_hits) > args.show:
        print(f"  …… 另有 {len(all_hits) - args.show} 处，用 --show 调大查看")
    print("\n改成读者能读懂的说法：")
    for k, v in REPLACEMENTS.items():
        print(f"  {k} → {v}")
    print("年份记号 A / E（3QFY2026A、4QFY2026E）是行业通用写法，不在此列。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
