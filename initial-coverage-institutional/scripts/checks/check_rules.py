#!/usr/bin/env python3
"""版式线条门：断言页眉线和首页右栏竖线真的存在，且正文里没有多余竖线。

这一项存在的理由：这两条线原本只写在规范里、只靠「渲染后逐项看」把关。
本项目里凡是没有脚本断言的版式项，最后都是靠人眼才发现出错的。
它们在 OOXML 里是明确的边框元素，不用渲染就能查。

断言三项：
  1. 页眉线   —— 至少一个 word/header*.xml 有 pBdr 下边框，深蓝 #1B3A6B、粗细 4。
                 首页页眉按规范留空，不要求它也带线，所以是「至少一个」而非「每个」。
  2. 右栏竖线 —— document.xml 里恰好一处 tcBorders 带深蓝左边框，即首页右栏那条。
  3. 无多余竖线 —— 正文表格一律只用横向分隔和隔行底色；深蓝左/右竖边框多于一处即判失败。

用法：
    python check_rules.py 报告.docx
"""

import argparse
import re
import sys
import zipfile
from pathlib import Path

FAILURE = "无法保证版式线条符合规范"

DEEP = "1B3A6B"          # 深蓝，页眉线与右栏竖线共用
RULE_SZ = "4"            # 0.5pt

# 页眉线：pBdr 里的 bottom，深蓝、粗细 4。属性顺序不固定，逐属性匹配。
HEADER_RULE = re.compile(
    r"<w:bottom\b(?=[^>]*w:val=\"single\")(?=[^>]*w:color=\"%s\")(?=[^>]*w:sz=\"%s\")" % (DEEP, RULE_SZ),
    re.I,
)
# 竖线：tcBorders 里的 left/right，深蓝
V_RULE = re.compile(
    r"<w:(left|right)\b(?=[^>]*w:val=\"single\")(?=[^>]*w:color=\"%s\")" % DEEP, re.I
)


def check(docx):
    results = []
    with zipfile.ZipFile(docx) as z:
        names = z.namelist()

        # 1. 页眉线
        headers = [n for n in names if re.fullmatch(r"word/header\d*\.xml", n)]
        with_rule = []
        for n in headers:
            body = z.read(n).decode("utf-8", "ignore")
            for pbdr in re.findall(r"<w:pBdr>.*?</w:pBdr>", body, re.S):
                if HEADER_RULE.search(pbdr):
                    with_rule.append(n)
                    break
        ok = bool(with_rule)
        results.append((
            "页眉线", ok,
            f"{'、'.join(sorted(with_rule))} 带深蓝下边框（#{DEEP}, sz={RULE_SZ}）" if ok
            else f"{len(headers)} 个页眉部件中没有一个带深蓝下边框（#{DEEP}, sz={RULE_SZ}）",
        ))

        # 2/3. 竖线
        doc = z.read("word/document.xml").decode("utf-8", "ignore")
        vlines = [tb for tb in re.findall(r"<w:tcBorders>.*?</w:tcBorders>", doc, re.S)
                  if V_RULE.search(tb)]
        n_v = len(vlines)
        results.append((
            "首页右栏竖线", n_v >= 1,
            "在位" if n_v >= 1 else f"document.xml 里没有深蓝竖边框，首页右栏与摘要之间缺分隔线",
        ))
        results.append((
            "无多余竖线", n_v <= 1,
            "全文仅首页右栏一条" if n_v <= 1
            else f"深蓝竖边框出现 {n_v} 处，正文表格不得加竖框（只用横向分隔和隔行底色）",
        ))
    return results


def main():
    ap = argparse.ArgumentParser(description="版式线条门")
    ap.add_argument("docx", type=Path)
    args = ap.parse_args()

    if not args.docx.is_file():
        print(f"[FAIL] Rules: {FAILURE}（文件不存在：{args.docx}）")
        return 1

    results = check(args.docx)
    for label, ok, detail in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {label}: {detail}")

    if all(ok for _, ok, _ in results):
        print("[PASS] Rules: 页眉线与右栏竖线符合规范")
        return 0
    print(f"[FAIL] Rules: {FAILURE}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
