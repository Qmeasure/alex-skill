#!/usr/bin/env python3
"""断言交付目录里没有 Word 或 Markdown 文件。

本 skill 全流程只产出 tex、PDF、Excel、CSV、PNG；阶段稿件也是 tex。
    python check_no_word_md.py <报告目录>
"""

import sys
from pathlib import Path

BANNED = {".md", ".markdown", ".docx", ".doc", ".docm", ".dotx", ".rtf"}


def main():
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_dir():
        print("[FAIL] NoWordMd: 用法 check_no_word_md.py <报告目录>")
        return 1
    root = Path(sys.argv[1])
    hits = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in BANNED
                  and not p.name.startswith("~$"))
    if hits:
        for p in hits[:20]:
            print(f"  {p.relative_to(root)}")
        print(f"[FAIL] NoWordMd: 交付目录里有 {len(hits)} 个 Word / Markdown 文件")
        return 1
    print("[PASS] NoWordMd: 交付目录里 0 个 Word / Markdown 文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
