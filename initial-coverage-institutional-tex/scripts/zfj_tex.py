#!/usr/bin/env python3
"""生成符合智富界版式的 LaTeX 片段：文本转义、宏定义、表格。

export_excel_to_tex.py 调用这里的函数把 Excel 写成 tex；版式常量与
assets/tex-template/style/zfj-report.sty 一一对应，两边改一处要同步另一处。
"""

import re

DXA_BP = 0.05                 # 1 DXA = 1/20 Word 磅 = 0.05bp（Word 的磅就是 TeX 的 bp）
TEXT_W = 527.24               # 版心 18.6cm = \textwidth（原 Word 版 10546 DXA）
HALF_TABLE_BP = TEXT_W / 2 - 6.0  # Key data 半宽表：半个版心扣 6bp 内边距

# 三种表：正文表 / Key data 主表 / Key data 半宽表
TABLE_MODES = {
    "standard": {"width_pt": TEXT_W, "colsep": 6.0, "rowsep": 4.0,
                 "font": 8, "note": 7},
    "compact": {"width_pt": TEXT_W, "colsep": 4.5, "rowsep": 1.5,
                "font": 7.5, "note": 7},
    "half": {"width_pt": HALF_TABLE_BP, "colsep": 3.5, "rowsep": 1.5,
             "font": 7.5, "note": 6.5},
}
MODE_ALIASES = {"标准": "standard", "紧凑": "compact", "半宽": "half",
                "standard": "standard", "compact": "compact", "half": "half"}

_SPECIAL = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
    "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}


def escape(text):
    """把普通文本转成 LaTeX 安全文本。None 变空串。"""
    if text is None:
        return ""
    return "".join(_SPECIAL.get(ch, ch) for ch in str(text))


def inline(text):
    """转义文本，并把 **加粗** 标记换成 \\textbf{}。"""
    parts = re.split(r"(\*\*[^*]+\*\*)", str(text))
    out = []
    for part in parts:
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            out.append(r"\textbf{" + escape(part[2:-2]) + "}")
        else:
            out.append(escape(part))
    return "".join(out)


def cell(text, align="c"):
    """表格单元格文本。连续 2 个以上的西文/数字字符包进 \\zfjtok：放不下时先借用内边距，
    再放不下才逐字符折行，与 Word 的处理顺序一致。"""
    text = "" if text is None else str(text)
    out, pos = [], 0
    for m in re.finditer(r"[A-Za-z0-9.,%+\-/()xX]{2,}", text):
        out.append(escape(text[pos:m.start()]))
        tok = m.group(0)
        broken = r"\allowbreak{}".join(escape(ch) for ch in tok)
        out.append(rf"\zfjtok{{{align}}}{{{escape(tok)}}}{{{broken}}}")
        pos = m.end()
    out.append(escape(text[pos:]))
    return "".join(out)


def macro_name_ok(name):
    return bool(re.fullmatch(r"[A-Za-z]+", name or ""))


def render_macros(pairs, source_note):
    """pairs: [(宏名, 已格式化的文本)] → keyfigures.tex 内容。"""
    lines = [f"% {source_note}", "% 生成物，勿手改；改数先改 Excel，再重跑导出脚本。"]
    for name, value in pairs:
        if not macro_name_ok(name):
            raise ValueError(f"宏名只能用英文字母：{name!r}")
        lines.append(rf"\newcommand{{\{name}}}{{{escape(value)}}}")
    return "\n".join(lines) + "\n"


def _widths_pt(widths_dxa, ncols, width_pt):
    if not widths_dxa:
        return [width_pt / ncols] * ncols
    if len(widths_dxa) != ncols:
        raise ValueError(f"列宽个数 {len(widths_dxa)} 与列数 {ncols} 不一致")
    total = float(sum(widths_dxa))
    return [width_pt * w / total for w in widths_dxa]


def render_table(spec, source_note):
    """spec 字段：
    id, caption(可空，空则不进「图表 N」序列), mode(standard/compact/half),
    widths(DXA 列表，可空), head(list), rows(list of list), hi(高亮行下标列表),
    note(口径小字，可空), first_left(默认 True)
    """
    mode = MODE_ALIASES.get(spec.get("mode") or "standard")
    if mode is None:
        raise ValueError(f"表 {spec.get('id')} 的模式只能是 标准/紧凑/半宽")
    m = TABLE_MODES[mode]
    head = [str(h) for h in (spec.get("head") or [])]
    rows = [list(r) for r in spec["rows"]]
    if not head and mode == "standard":
        raise ValueError(f"表 {spec.get('id')} 是正文表，必须有表头")
    ncols = len(head) or max(len(r) for r in rows)
    hr = 1 if head else 0          # 表头行数
    for i, r in enumerate(rows):
        if len(r) != ncols:
            raise ValueError(f"表 {spec.get('id')} 第 {i + 1} 行有 {len(r)} 列，表头 {ncols} 列")
    hi = set(spec.get("hi") or [])
    note = spec.get("note")
    first_left = spec.get("first_left", True)

    widths = _widths_pt(spec.get("widths"), ncols, m["width_pt"])
    colsep = m["colsep"]
    cols = []
    for i, w in enumerate(widths):
        align = "l" if (i == 0 and first_left) else "c"
        cols.append(f"Q[{align},m,wd={w - 2 * colsep:.3f}bp]")

    nrows = hr + len(rows) + (1 if note else 0)
    font = f"\\zfjcellfont{{{m['font']}}}"
    keys = [
        f"width={sum(widths):.3f}bp",
        "colspec={" + "".join(cols) + "}",
        f"colsep={colsep}bp", f"rowsep={m['rowsep']}bp",
        f"cells={{font={font}}}",
    ]
    if head:
        keys += ["rowhead=1", f"row{{1}}={{halign=c,bg=zfjDeep,fg=white,font={font}\\bfseries}}"]
    off = hr + 1                   # 第一行数据在 tabularray 里的行号
    plain_tint = [i + off for i in range(len(rows)) if i % 2 == 1 and i not in hi]
    if plain_tint:
        keys.append("row{" + ",".join(map(str, plain_tint)) + "}={bg=zfjTint}")
    if hi:
        keys.append("row{" + ",".join(str(i + off) for i in sorted(hi)) +
                    f"}}={{bg=zfjTint,font={font}\\bfseries}}")
    keys.append("hline{1,Z}={0.48bp,zfjDeep}")
    if nrows > 1:
        keys.append("hline{2-Y}={0.25bp,zfjRule}")
    if note:
        span_wd = sum(widths) - 2 * colsep
        keys.append(f"cell{{{nrows}}}{{1}}={{c={ncols}}}{{halign=l,wd={span_wd:.3f}bp,"
                    f"font=\\zfjcellfont{{{m['note']}}},fg=zfjGray}}")

    out = [f"% {source_note}", "% 生成物，勿手改；改数先改 Excel，再重跑导出脚本。"]
    caption = spec.get("caption")
    if caption:
        out.append(rf"\zfjtablecaption{{{escape(caption)}}}")
    # 正文表可跨页，用 longtblr；Key data 页的表在两栏盒子里，用 tblr 包进 \hbox
    env = "longtblr" if mode == "standard" else "tblr"
    out.append(rf"\zfjtablebegin\zfjtablefont{{{m['font']}}}{{{colsep}}}")
    out.append((r"\hbox{" if env == "tblr" else "") + rf"\begin{{{env}}}{{")
    out.extend("  " + k + "," for k in keys)
    out.append("}")
    def aligns(i):
        return "l" if (i == 0 and first_left) else "c"
    if head:
        out.append(" & ".join(cell(h) for h in head) + r" \\")
    for r in rows:
        out.append(" & ".join(cell(c, aligns(i)) for i, c in enumerate(r)) + r" \\")
    if note:
        out.append(escape(note) + " &" * (ncols - 1) + r" \\")
    out.append(rf"\end{{{env}}}" + ("}" if env == "tblr" else ""))
    out.append(r"\zfjtableend" if mode == "standard" else r"\zfjtablekeyend")
    return "\n".join(out) + "\n"
