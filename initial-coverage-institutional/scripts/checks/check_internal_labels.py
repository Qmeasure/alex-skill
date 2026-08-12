#!/usr/bin/env python3
"""内部代号门：断言交付物里 0 处 O 池 / V 池 / T 池。

这一项存在的理由：O/V/T 是 `references/同业与产业链横向比较.md` 的建池代号，
读者没读过那份方法论，看到「O 池经营对标」只会一头雾水。它最容易漏在
章节标题、图注和表格的层级列里——这些位置写稿时不当成正文，肉眼扫也容易跳过。

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

FAILURE = "无法保证交付物中不含内部建池代号"

PATTERNS = [
    # 「O 池」「V池」——主要形态。「利润池」「资金池」不会命中：代号是 ASCII 字母，通用词前面是汉字。
    re.compile(r"[OVT]\s*池"),
    # 「O/V/T 三池」「O/V/T」连写
    re.compile(r"[OVT]\s*/\s*[OVT]\s*(?:/\s*[OVT])?"),
    # sheet 名 `O_经营对标`、表注 `V = 估值可比`——单字母代号后接下划线或等号再接汉字
    re.compile(r"[OVT]\s*[_=]\s*[一-鿿]"),
]

REPLACEMENTS = {
    "O 池 / O_": "经营对标公司（样本只有一两家时直接写公司名）",
    "V 池 / V_": "可比公司",
    "T 池 / T_": "产业链公司 / 零部件公司",
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
    ap.add_argument("files", nargs="+", help="要检查的 .docx / .xlsx（也接受纯文本文件）")
    ap.add_argument("--show", type=int, default=10, help="最多打印多少条命中")
    args = ap.parse_args()

    all_hits = []
    for f in args.files:
        all_hits += scan(Path(f))

    if not all_hits:
        print(f"PASS  内部代号门：{len(args.files)} 个交付物中 0 处 O/V/T 池")
        return 0

    print(f"FAIL  {FAILURE}：命中 {len(all_hits)} 处")
    for part, line_no, line in all_hits[: args.show]:
        print(f"  {part} 第 {line_no} 行：{line}")
    if len(all_hits) > args.show:
        print(f"  …… 另有 {len(all_hits) - args.show} 处，用 --show 调大查看")
    print("\n改成读者能读懂的说法：")
    for k, v in REPLACEMENTS.items():
        print(f"  {k} → {v}")
    print("表格层级列的 V/T/目标 → 估值可比 / 产业链 / 目标公司；「利润池」是通用术语，不在此列。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
