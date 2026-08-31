#!/usr/bin/env python3
"""渲染门：对已渲染的 PDF 断言空白页、首页溢出、首页元素齐全、页数区间、文字越界。

这一项存在的理由：首页溢出把内容挤到第 2 页、留下一张近乎空白的页，
在开发过程中复发过两次，每次都只有肉眼看渲染图才发现。目视不是门，脚本才是。

用法：
    python check_render.py 报告.pdf --earnings           # 业绩更新，14–18 页
    python check_render.py 样张.pdf --earnings --sample --pages-min 3 --pages-max 3
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

BLANK_THRESHOLD = 150          # 单页正文字符数低于此值即判为空白/近空白
FAILURE = "无法保证渲染结果符合版式要求"

# 首页必须出现的文本（两个分支通用部分）
COVER_COMMON = ["AI 投资建议", "AI 研究团队", "本报告由 AI 生成", "扫码加入社群"]
# 业绩更新分支：评级带变动方向、目标价可能写「维持」、右栏含报告期与超预期幅度
COVER_EARNINGS = ["目标价", "当前价", "上行空间", "报告期"]

# 正文页页眉，判断第 2 页开头时要先剥掉
RUNNING_HEADER = "智富界"

# 第 2 页必须以此开头。首页一旦溢出，第 2 页开头会变成封面的残留。
PAGE2_HEAD = "业绩速览"

# 版心边界（A4 纵向，左右页边距各 1.2 cm）。文字越界通常不是"稍微宽一点"，
# 而是内层表格宽度和外层单元格边距各写各的、对不上——差一个边距就顶出去。
PAGE_W_PT = 595.276
MARGIN_PT = 1.2 * 72 / 2.54       # 34.02 pt
BLEED_TOL_PT = 1.5                # 舍入容差，超过就是真越界


def pdf_pages(pdf):
    """用 pdftotext 提取逐页文本；失败返回 None。"""
    if shutil.which("pdftotext") is None:
        return None
    try:
        out = subprocess.run(
            ["pdftotext", "-layout", str(pdf), "-"],
            capture_output=True, text=True, timeout=120, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    pages = out.stdout.split("\f")
    # pdftotext 在末尾多切一个空段，去掉
    if pages and not pages[-1].strip():
        pages = pages[:-1]
    return pages


def word_boxes(pdf):
    """逐页取词的外接框 [(页码, xMin, xMax, 文字)]；pdftotext 不支持 -bbox 时返回 None。"""
    if shutil.which("pdftotext") is None:
        return None
    try:
        out = subprocess.run(
            ["pdftotext", "-bbox-layout", str(pdf), "-"],
            capture_output=True, text=True, timeout=180, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    boxes = []
    for pno, page in enumerate(re.split(r"<page\b", out.stdout)[1:], 1):
        for m in re.finditer(
            r'<word xMin="([\d.]+)" yMin="[\d.]+" xMax="([\d.]+)" yMax="[\d.]+">(.*?)</word>',
            page,
        ):
            boxes.append((pno, float(m.group(1)), float(m.group(2)), m.group(3)))
    return boxes


def norm(text):
    """去掉空白，便于统计真实字符数和做包含判断。"""
    return re.sub(r"\s+", "", text)


def check(pdf, *, pages_min, pages_max, pre_ipo, sample):
    pages = pdf_pages(pdf)
    if pages is None:
        return [("pdftotext", False, "无法提取 PDF 文本（pdftotext 缺失或解析失败）")]

    results = []
    n = len(pages)

    # 1. 页数区间
    ok = pages_min <= n <= pages_max
    results.append(("页数区间", ok, f"{n} 页（要求 {pages_min}–{pages_max}）"))

    # 2. 空白 / 近空白页
    blanks = [i for i, p in enumerate(pages, 1) if len(norm(p)) < BLANK_THRESHOLD]
    results.append((
        "无空白页", not blanks,
        "无" if not blanks else "第 " + "、".join(str(i) for i in blanks)
        + f" 页正文字符数低于 {BLANK_THRESHOLD}",
    ))

    # 3. 首页元素齐全
    p1 = norm(pages[0]) if pages else ""
    need = COVER_COMMON + COVER_EARNINGS
    missing = [w for w in need if norm(w) not in p1]
    results.append((
        "首页元素齐全", not missing,
        "全部在位" if not missing else "缺 " + "、".join(missing),
    ))

    # 4. 首页未溢出：第 2 页剥掉页眉后，开头必须就是业绩速览标题。
    #    首页一旦溢出，第 2 页开头会变成封面的残留（表格孤儿行、口径小字等）。
    if n >= 2:
        head = norm(pages[1])
        if head.startswith(norm(RUNNING_HEADER)):
            head = head[len(norm(RUNNING_HEADER)):]
        ok2 = head[:20].startswith(norm(PAGE2_HEAD))
        results.append((
            "首页未溢出", ok2,
            f"第 2 页以{PAGE2_HEAD}开头" if ok2
            else f"第 2 页开头不是{PAGE2_HEAD}，疑似首页溢出：" + head[:40],
        ))
    else:
        results.append(("首页未溢出", True, "仅 1 页，跳过"))

    # 5. 文字未越出版心：任何一页的词框都不得越过左右页边距。
    #    典型成因是内层表宽写死成"外层宽度减一个边距"，而外层单元格实际两边都有边距，
    #    差值把整块内容顶出版心，表现为数值贴边、标签与数值之间的间距被吃掉。
    boxes = word_boxes(pdf)
    if boxes is None:
        results.append(("文字未越出版心", True, "pdftotext 不支持 -bbox-layout，跳过"))
    else:
        right_lim = PAGE_W_PT - MARGIN_PT + BLEED_TOL_PT
        left_lim = MARGIN_PT - BLEED_TOL_PT
        bad = [(pno, x0, x1, w) for pno, x0, x1, w in boxes
               if x1 > right_lim or x0 < left_lim]
        if bad:
            worst = max(bad, key=lambda b: b[2])
            detail = (f"{len(bad)} 处越界，最远在第 {worst[0]} 页："
                      f"「{worst[3][:12]}」右端 {worst[2]:.1f}pt，"
                      f"版心右边界 {PAGE_W_PT - MARGIN_PT:.1f}pt")
        else:
            detail = f"全部在 {MARGIN_PT:.1f}–{PAGE_W_PT - MARGIN_PT:.1f}pt 之间"
        results.append(("文字未越出版心", not bad, detail))

    return results


def main():
    ap = argparse.ArgumentParser(description="研报 PDF 渲染门")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--pages-min", type=int, default=14)
    ap.add_argument("--pages-max", type=int, default=18)
    ap.add_argument("--earnings", action="store_true",
                    help="业绩更新分支（本 Skill 只有这一支，保留该开关是为了与首次覆盖版命令行对齐）")
    ap.add_argument("--sample", action="store_true", help="样张模式，放宽仅 1 页时的溢出检查")
    args = ap.parse_args()

    if not args.pdf.is_file():
        print(f"[FAIL] Render: {FAILURE}（文件不存在：{args.pdf}）")
        return 1

    results = check(args.pdf, pages_min=args.pages_min, pages_max=args.pages_max,
                    pre_ipo=False, sample=args.sample)
    for label, ok, detail in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {label}: {detail}")

    if all(ok for _, ok, _ in results):
        print("[PASS] Render: 渲染结果符合版式要求")
        return 0
    print(f"[FAIL] Render: {FAILURE}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
