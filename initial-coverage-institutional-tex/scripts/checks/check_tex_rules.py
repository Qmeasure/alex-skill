#!/usr/bin/env python3
"""断言 tex 源码没有违反版式标准的禁止项。

    python check_tex_rules.py <报告目录>

扫描 front/ 与 chapters/ 的 .tex（去掉注释后），以及 main.tex：
  - 正文里写 \\newpage（分页用 \\zfjpagebreak）、\\color / \\textcolor / \\fontsize / \\selectfont
  - 手写表格环境 tabular / tblr / longtblr / tabularx（表格由 Excel 导出到 tables/）
  - 裸 URL（链接用 \\href）
  - 旧配色 1F4E5F / 2F5965
  - emoji
  - main.tex 的 \\documentclass 带 fontset，或任何地方用了 \\setmainfont
"""

import re
import sys
from pathlib import Path

RULES = [
    (r"\\newpage\b|\\clearpage\b", "用了 \\newpage / \\clearpage，分页改用 \\zfjpagebreak"),
    (r"\\(color|textcolor|fontsize|selectfont)\b", "正文里写了颜色或字号命令，用版式包提供的命令"),
    (r"\\begin\{(tabular|tabularx|tblr|longtblr)\}", "手写了表格，表格要写进 Excel「报告表格」再导出"),
    (r"(?<!\\href\{)(?<!\\url\{)https?://", "裸 URL，用 \\href{链接}{文字}"),
    (r"1F4E5F|2F5965", "旧配色"),
    (r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", "emoji"),
    (r"\\setmainfont", "改了西文字体，西文用 ctex 默认"),
]


def strip_comments(text):
    return re.sub(r"(?<!\\)%.*", "", text)


def main():
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_dir():
        print("[FAIL] TexRules: 用法 check_tex_rules.py <报告目录>")
        return 1
    root = Path(sys.argv[1])
    files = sorted(q for sub in ("front", "chapters") for q in (root / sub).glob("*.tex"))
    hits = []
    for f in files:
        for n, line in enumerate(strip_comments(f.read_text(encoding="utf-8")).splitlines(), 1):
            for pat, msg in RULES:
                if re.search(pat, line):
                    hits.append(f"{f.relative_to(root)}:{n} {msg}")
    main_tex = root / "main.tex"
    if main_tex.is_file():
        m = strip_comments(main_tex.read_text(encoding="utf-8"))
        if re.search(r"\\documentclass\[[^\]]*fontset", m):
            hits.append("main.tex \\documentclass 带了 fontset 选项")
        if "\\setmainfont" in m:
            hits.append("main.tex 改了西文字体")
    if hits:
        print("\n".join(hits[:20]))
        print(f"[FAIL] TexRules: {len(hits)} 处违反版式标准的写法")
        return 1
    print(f"[PASS] TexRules: {len(files)} 个文件没有禁止项")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
