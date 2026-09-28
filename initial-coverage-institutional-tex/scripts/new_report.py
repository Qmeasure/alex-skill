#!/usr/bin/env python3
"""新建一份报告的 tex 工程：拷贝版式模板和品牌资产。

    python scripts/new_report.py <报告目录>

目录已存在且非空时拒绝覆盖。拷贝后结构：
  main.tex  style/  front/  chapters/  drafts/draft.tex  brand/
  tables/ data/ figures/（空，分别由导出脚本、阶段 2/3、阶段 4 写入）
"""

import shutil
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    dst = Path(sys.argv[1])
    if dst.exists() and any(dst.iterdir()):
        print(f"[FAIL] {dst} 已存在且非空，不覆盖")
        return 1
    shutil.copytree(SKILL / "assets" / "tex-template", dst, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(".DS_Store"))
    shutil.copytree(SKILL / "assets" / "brand", dst / "brand", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(".DS_Store"))
    for sub in ("tables", "data/_data", "figures"):
        (dst / sub).mkdir(parents=True, exist_ok=True)
    print(f"[PASS] 已新建报告工程：{dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
