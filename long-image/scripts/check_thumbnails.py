#!/usr/bin/env python3
"""Pre-render gate: verify thumbnails exist before allowing rendering."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check that thumbnails have been generated. "
        "Exit 1 blocks the render pipeline.",
    )
    parser.add_argument("input", help="Input JSON file.")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"{RED}输入文件不存在: {input_path}{RESET}")
        return 1

    data = json.loads(input_path.read_text(encoding="utf-8"))

    preview = data.get("docx_preview")
    if not preview:
        print(
            f"{RED}{BOLD}缩略图未生成：JSON 中缺少 docx_preview 字段。{RESET}\n"
            f"请先完成步骤 4（生成缩略图）。"
        )
        return 1

    thumb_dir = input_path.parent / preview.get("dir", "_page_thumbs")
    expected = int(preview.get("pages", 4))

    if not thumb_dir.is_dir():
        print(f"{RED}{BOLD}缩略图目录不存在: {thumb_dir}{RESET}")
        return 1

    actual = len(list(thumb_dir.glob("page_*.png")))
    if actual < expected:
        print(
            f"{RED}{BOLD}缩略图数量不足：期望 {expected} 张，实际 {actual} 张。{RESET}\n"
            f"请补充生成缩略图后重试。"
        )
        return 1

    print(f"{GREEN}{BOLD}缩略图检查通过：{actual} 张缩略图就绪。{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
