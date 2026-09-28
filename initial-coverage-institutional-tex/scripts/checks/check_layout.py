#!/usr/bin/env python3
"""版式量测：在编译出的 PDF 上量格式标准里的参数，逐项断言。

    python check_layout.py 报告.pdf

坐标单位是 PDF 的 bp（= Word 的磅）。断言项：
  1. 页眉线：第 2 页起每页一条 0.48bp 深蓝横线，上沿约 41.5bp；首页没有
  2. 右栏竖线：首页恰好一条深蓝竖线，x≈413.8；其余页没有深蓝竖线
  3. 正文窄栏：正文字号的黑色行从左缩进处起、右端不超过左缩进 + 12.7cm
  4. 图宽：正文页的图宽为 18.6cm 或 9.3cm，不缩小居中
  5. 字体：只用思源宋体和 Latin Modern
  6. 配色：文字与填充只用规定色值；旧色 1F4E5F / 2F5965 不出现
  7. 品牌标识：首页左上 logo + 智富界；第 2 页起右上 logo + 智富界
  8. 页码：每页右下角是本页页码
  9. 首页不越出下边距
"""

import sys
from pathlib import Path

import fitz

PAGE_H = 841.89
MARGIN_L = 34.016          # 1.2cm
BODY_LEFT = MARGIN_L + 7.1            # 左缩进 142 DXA
BODY_RIGHT = BODY_LEFT + 359.9         # 行宽 12.7cm
FULL_W, HALF_W = 527.24, 263.62
DEEP = (0x1B, 0x3A, 0x6B)
TEXT_COLORS = {0x000000, 0x1B3A6B, 0x2B6EF2, 0x666666, 0xFFFFFF}
FILL_COLORS = {DEEP, (0x2B, 0x6E, 0xF2), (0xF2, 0xF6, 0xFC), (0xD9, 0xD9, 0xD9), (0xFF, 0xFF, 0xFF),
               (0, 0, 0)}
OLD_COLORS = {(0x1F, 0x4E, 0x5F), (0x2F, 0x59, 0x65)}
BODY_SIZE = 9.12            # 9pt 经 0.24bp 吸附
TOL = 1.0
HANG_PUNCT = "，。、；：！？）」』》”’"
OPEN_PUNCT = "（「『《“‘"


def rgb(c):
    return tuple(round(x * 255) for x in c) if c else None


def near(c, ref, tol=3):
    return c is not None and all(abs(a - b) <= tol for a, b in zip(c, ref))


def drawings(page):
    """返回 (矩形, 颜色) 列表：填充矩形与描边线统一处理。"""
    out = []
    for d in page.get_drawings():
        col = rgb(d.get("fill")) or rgb(d.get("color"))
        r = d["rect"]
        if d.get("fill") is None and d.get("width"):
            w = d["width"]
            if r.height < 0.01:
                r = fitz.Rect(r.x0, r.y0 - w / 2, r.x1, r.y1 + w / 2)
            elif r.width < 0.01:
                r = fitz.Rect(r.x0 - w / 2, r.y0, r.x1 + w / 2, r.y1)
        out.append((r, col))
    return out


def lines(page):
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            if ln["spans"]:
                yield ln


def check(pdf):
    doc = fitz.open(pdf)
    res = []

    # 1. 页眉线
    bad = []
    for i, page in enumerate(doc, 1):
        hdr = [r for r, c in drawings(page) if near(c, DEEP) and r.width > 500 and 40.5 < r.y0 < 43
               and r.height < 1]
        if (i == 1 and hdr) or (i > 1 and len(hdr) != 1):
            bad.append(i)
    res.append(("页眉线", not bad, "首页无、其余每页一条" if not bad else f"第 {bad[:8]} 页不符"))

    # 2. 右栏竖线
    bad = []
    for i, page in enumerate(doc, 1):
        vr = [r for r, c in drawings(page) if near(c, DEEP) and r.width < 1.5 and r.height > 20]
        if i == 1:
            if len(vr) != 1 or abs((vr[0].x0 + vr[0].x1) / 2 - 413.76) > 1.5 or vr[0].height < 300:
                bad.append(f"首页 {len(vr)} 条")
        elif vr:
            bad.append(f"第 {i} 页 {len(vr)} 条")
    res.append(("右栏竖线", not bad, "首页恰好一条且贯穿右栏，其余页没有竖线" if not bad else "；".join(bad)))

    # 3. 正文窄栏：第 3 页起所有正文字号的黑色行，左端不得早于正文左缩进，右端不得越过窄栏
    over, body_pages = [], 0
    for i, page in enumerate(doc, 1):
        if i <= 2:
            continue
        found = False
        for ln in lines(page):
            sp = ln["spans"][0]
            if abs(sp["size"] - BODY_SIZE) > 0.05 or sp["color"] != 0 or ln["bbox"][1] > 800:
                continue
            found = True
            text = "".join(x["text"] for x in ln["spans"]).rstrip()
            # 行尾标点、行首开标点被压成半宽时，字形外框会伸出半个字，墨迹仍在栏内
            allow = 0.8 * BODY_SIZE if text and text[-1] in HANG_PUNCT else 0
            lallow = 0.8 * BODY_SIZE if text and text.lstrip()[:1] in OPEN_PUNCT else 0
            if ln["bbox"][0] < BODY_LEFT - TOL - lallow or ln["bbox"][2] > BODY_RIGHT + TOL + allow:
                over.append(i)
                break
        body_pages += found
    ok = not over and (body_pages > 0 or len(doc) <= 2)
    res.append(("正文窄栏", ok,
                f"{body_pages} 页正文行宽都在 12.7cm 内" if ok else
                (f"第 {sorted(set(over))[:8]} 页有正文越出窄栏" if over else "第 3 页起没有正文行")))

    # 4. 图宽
    bad = []
    for i, page in enumerate(doc, 1):
        if i <= 2:
            continue
        for im in page.get_image_info():
            x0, y0, x1, _ = im["bbox"]
            if y0 < 45:      # 页眉 logo
                continue
            w = x1 - x0
            if not (abs(w - FULL_W) < 0.5 or abs(w - HALF_W) < 0.5):
                bad.append(f"p{i} {w:.1f}bp")
    res.append(("图宽", not bad, "全部为 18.6cm 或 9.3cm" if not bad else "、".join(bad[:8])))

    # 5. 字体
    names = {f[3] for p in doc for f in p.get_fonts()}
    odd = sorted(n for n in names if not any(k in n for k in ("SourceHanSerifCN", "LMRoman", "LMMono", "LMSans")))
    res.append(("字体", not odd, "只有思源宋体与 Latin Modern" if not odd else "出现 " + "、".join(odd[:5])))

    # 6. 配色
    bad_text, bad_fill = set(), set()
    for page in doc:
        for ln in lines(page):
            for sp in ln["spans"]:
                if sp["text"].strip() and sp["color"] not in TEXT_COLORS:
                    bad_text.add(f"{sp['color']:06X}")
        for r, c in drawings(page):
            if c and not any(near(c, f, 2) for f in FILL_COLORS):
                bad_fill.add("%02X%02X%02X" % c)
            if c and any(near(c, o, 2) for o in OLD_COLORS):
                bad_fill.add("旧色 %02X%02X%02X" % c)
    ok = not bad_text and not bad_fill
    res.append(("配色", ok, "文字与填充只用规定色值" if ok else
                f"文字色 {sorted(bad_text)[:5]} 填充色 {sorted(bad_fill)[:5]}"))

    # 7. 品牌标识
    bad = []
    for i, page in enumerate(doc, 1):
        txt_top = "".join(ln["spans"][0]["text"] for ln in lines(page) if ln["bbox"][1] < (110 if i == 1 else 45))
        imgs = page.get_image_info()
        if i == 1:
            logo = [im for im in imgs if im["bbox"][0] < 40 and 45 < im["bbox"][1] < 60
                    and abs((im["bbox"][2] - im["bbox"][0]) - 39.7) < 1]
        else:
            logo = [im for im in imgs if im["bbox"][1] < 45 and im["bbox"][0] > 480]
        if not logo or "智富界" not in txt_top:
            bad.append(i)
    res.append(("品牌标识", not bad, "每页都有 logo + 智富界" if not bad else f"第 {bad[:8]} 页缺"))

    # 8. 页码
    bad = []
    for i, page in enumerate(doc, 1):
        foot = [ln["spans"][0]["text"].strip() for ln in lines(page) if ln["bbox"][1] > 800]
        if str(i) not in foot:
            bad.append(i)
    res.append(("页码", not bad, "每页页码正确" if not bad else f"第 {bad[:8]} 页页码不对"))

    # 9. 首页不越出下边距
    p1 = doc[0]
    bottoms = [ln["bbox"][3] for ln in lines(p1) if ln["bbox"][1] < 800]
    bottoms += [im["bbox"][3] for im in p1.get_image_info()]
    limit = PAGE_H - 45.35
    low = max(bottoms) if bottoms else 0
    res.append(("首页下边距", low <= limit + TOL, f"首页内容最低到 {low:.1f}bp（下边界 {limit:.1f}bp）"))
    return res


def main():
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_file():
        print("[FAIL] Layout: 用法 check_layout.py 报告.pdf")
        return 1
    results = check(sys.argv[1])
    for label, ok, detail in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {label}: {detail}")
    if all(ok for _, ok, _ in results):
        print("[PASS] Layout: 版式参数全部符合")
        return 0
    print("[FAIL] Layout: 版式参数不符合，不交付")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
