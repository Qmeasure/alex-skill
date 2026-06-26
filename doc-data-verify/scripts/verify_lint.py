#!/usr/bin/env python3
"""核查表自检 lint —— doc-data-verify skill 的交付前阻断门。

只兜机械可检的违规:留白、占位符、非法状态、缺更新值/来源/截止时间、记忆型对冲词。
命中即非零退出,逐条要求清除。

诚实声明:catch 不住"看起来合理的错数"(URL 真假、数值对不对、口径错没错),
那一类只能靠异源验证和逐条核对,不是这个脚本的职责。

用法:
    python verify_lint.py <核查表.md> [<更多.md/目录> ...]
    传目录则递归扫其中的 .md。脚本自动在文件里找含「核查结果」「来源URL」表头的表。

退出码:有命中 = 1,干净 = 0,无表可检 = 2。
"""

import os
import re
import sys

# 合法状态
VALID_STATUS = {"一致", "不一致", "已过期", "缺失", "冲突"}
# 需要给更新值 + 来源的状态
NEEDS_UPDATE = {"不一致", "已过期"}

# 占位符 / 留白替身(违反完整性强制)。"未找到公开数据"是被允许的正当标注,不在此列。
PLACEHOLDER = re.compile(r"待补|待定|TODO|tbd|xxx|placeholder|暂无|^\s*[?？]\s*$|^\s*[-—]\s*$", re.I)
# 记忆型对冲词(数值精度的 约/近/超过/左右 不算)
MEMORY_HEDGE = re.compile(r"我记得|印象中|应该是|大概是|差不多|估计是|可能是|貌似")
# 笼统来源(没有真链接又不是检索路径说明)
VAGUE_SOURCE = re.compile(r"公司公告|网络资料|网上|资料显示|据悉|据传")
SANCTIONED_NOTFOUND = "未找到公开数据"
URL_RE = re.compile(r"https?://")


def split_row(line):
    """切一行 markdown 表格,去掉首尾空管线产生的空串。"""
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return cells


def is_separator(cells):
    return all(re.fullmatch(r":?-{2,}:?", c or "-") for c in cells) and cells


def find_columns(header):
    """从表头按关键词定位列下标。返回 dict 或 None。"""
    idx = {}
    for i, h in enumerate(header):
        if "原文" in h:
            idx["orig"] = i
        elif "核查结果" in h or "结果" in h or "状态" in h:
            idx["status"] = i
        elif "最新" in h:
            idx["new"] = i
        elif "URL" in h.upper() or "来源" in h or "链接" in h:
            idx.setdefault("url", i)
        elif "截止" in h or "时间" in h:
            idx["cutoff"] = i
        elif "备注" in h or "说明" in h:
            idx["note"] = i
    need = {"orig", "status", "new", "url", "cutoff"}
    return idx if need.issubset(idx) else None


def check_table(rows, start_lineno, cols):
    hits = []
    for off, cells in rows:
        lineno = start_lineno + off
        # 列数不够,整行算结构破损
        maxi = max(cols.values())
        if len(cells) <= maxi:
            hits.append((lineno, "结构", f"列数不足(需 ≥{maxi + 1},实得 {len(cells)})", " | ".join(cells)))
            continue

        def cell(key):
            return cells[cols[key]] if key in cols else ""

        orig, status, new, url, cutoff = (cell("orig"), cell("status"),
                                          cell("new"), cell("url"), cell("cutoff"))
        note = cell("note")
        row_txt = " | ".join(cells)
        notfound = SANCTIONED_NOTFOUND in (new + note)

        # 1) 空单元格(完整性强制)。备注列允许空,其余必填。
        for key in ("orig", "status", "new", "url", "cutoff"):
            if not cell(key):
                hits.append((lineno, "留白", f"「{key}」列空着——完整性强制不许留白", row_txt))

        # 2) 占位符
        for key in ("orig", "status", "new", "url", "cutoff", "note"):
            v = cell(key)
            if v and PLACEHOLDER.search(v):
                hits.append((lineno, "占位符", f"「{key}」=‘{v}’ 像占位/留白替身——查不到要写「未找到公开数据」+检索路径", row_txt))

        # 3) 非法状态
        if status and status not in VALID_STATUS:
            hits.append((lineno, "状态非法", f"核查结果‘{status}’不在 {{一致/不一致/已过期/缺失/冲突}}", row_txt))

        # 4) 需更新却缺更新值 / 缺来源
        if status in NEEDS_UPDATE:
            if not new or new in ("同原文",):
                hits.append((lineno, "缺更新值", f"状态={status} 却没给最新数据", row_txt))
            if new and not URL_RE.search(url) and not notfound:
                hits.append((lineno, "缺来源", f"状态={status} 的更新值缺可点开 URL", row_txt))

        # 5) 来源既无 http 又不是「未找到」说明 → 笼统来源
        if url and not URL_RE.search(url) and not notfound:
            if VAGUE_SOURCE.search(url) or "检索" not in url:
                hits.append((lineno, "来源笼统", f"「来源URL」=‘{url}’ 不是真链接,也不是检索路径说明", row_txt))

        # 6) 记忆型对冲词
        for key in ("new", "url", "note"):
            v = cell(key)
            if v and MEMORY_HEDGE.search(v):
                hits.append((lineno, "记忆对冲", f"「{key}」含记忆型措辞‘{MEMORY_HEDGE.search(v).group()}’——要实搜来源,不靠记忆", row_txt))

    return hits


def scan_file(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError as e:
        print(f"[warn] 读不了 {path}: {e}", file=sys.stderr)
        return [], 0

    all_hits = []
    tables = 0
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.lstrip().startswith("|"):
            header = split_row(line)
            cols = find_columns(header)
            # 下一行应是分隔行
            if cols and i + 1 < n and lines[i + 1].lstrip().startswith("|") and is_separator(split_row(lines[i + 1])):
                tables += 1
                j = i + 2
                rows = []
                while j < n and lines[j].lstrip().startswith("|"):
                    rows.append((j - i, split_row(lines[j])))
                    j += 1
                all_hits += check_table(rows, i + 1, cols)
                i = j
                continue
        i += 1
    return all_hits, tables


def iter_md(paths):
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                for f in files:
                    if f.endswith(".md"):
                        yield os.path.join(root, f)
        elif os.path.isfile(p):
            yield p
        else:
            print(f"[warn] 路径不存在,跳过:{p}", file=sys.stderr)


def main(argv):
    paths = argv[1:]
    if not paths:
        print(__doc__)
        return 2

    total_hits = 0
    total_tables = 0
    for path in iter_md(paths):
        hits, tables = scan_file(path)
        total_tables += tables
        if not hits:
            continue
        total_hits += len(hits)
        print(f"\n● {path}")
        for lineno, kind, msg, snippet in hits:
            print(f"  [{kind}] L{lineno}  {msg}")

    print("\n" + "=" * 60)
    if total_tables == 0:
        print("没找到核查表(含「核查结果」「来源URL」表头的 markdown 表)。检查输入。")
        return 2
    if total_hits:
        print(f"核查表 lint 命中 {total_hits} 处(共扫 {total_tables} 张表)。逐条清除后再交付:")
        print("留白/占位 → 补数据或写「未找到公开数据」+检索路径;缺来源 → 补可点开 URL;")
        print("记忆对冲 → 实搜来源。清不掉不交付。")
        return 1
    print(f"核查表 lint 通过(共扫 {total_tables} 张表):未发现机械可检的违规。")
    print("注意:这不证明数据都对——URL 真假、数值对错靠异源验证逐条核。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
