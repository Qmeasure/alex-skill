#!/usr/bin/env python3
"""断言正文不出现第一人称「我们」。

扫描报告目录下 front/、chapters/ 的 .tex（或直接给出的 .tex 文件），去掉注释和
TeX 命令名后统计。研报只写结论，不写研究过程，第一人称一律改成无主语或「本报告」。
    python check_first_person.py <报告目录或 .tex 文件> [...]
"""

import re
import sys
from pathlib import Path

WORDS = ("我们",)


def tex_files(arg):
    p = Path(arg)
    if p.is_file():
        return [p]
    return sorted(q for sub in ("front", "chapters") for q in (p / sub).glob("*.tex"))


def strip_tex(text):
    text = re.sub(r"(?<!\\)%.*", "", text)          # 注释
    return re.sub(r"\\[A-Za-z@]+\*?", " ", text)     # 命令名


def main():
    files = [f for a in sys.argv[1:] for f in tex_files(a)]
    if not files:
        print("[FAIL] FirstPerson: 没有可检查的 .tex 文件")
        return 1
    hits = []
    for f in files:
        for n, line in enumerate(strip_tex(f.read_text(encoding="utf-8")).splitlines(), 1):
            for w in WORDS:
                if w in line:
                    hits.append(f"{f.name}:{n} {line.strip()[:40]}")
    if hits:
        print("\n".join(hits[:20]))
        print(f"[FAIL] FirstPerson: {len(hits)} 处第一人称")
        return 1
    print(f"[PASS] FirstPerson: {len(files)} 个文件 0 处「我们」")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
