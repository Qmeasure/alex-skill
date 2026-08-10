#!/usr/bin/env python3
"""Set generation date in the input JSON. Must be run only when explicitly requested by the user."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

RED = "\033[91m"
GREEN = "\033[92m"
BOLD = "\033[1m"
RESET = "\033[0m"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Set meta.date and share.badge in the input JSON. "
        "Defaults to today; use --date to specify a different date.",
    )
    parser.add_argument("input", help="Input JSON file.")
    parser.add_argument(
        "--date",
        help="Date in YYYY-MM-DD format. Defaults to today.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"{RED}输入文件不存在: {input_path}{RESET}")
        return 1

    target = args.date or date.today().strftime("%Y-%m-%d")
    try:
        date.fromisoformat(target)
    except ValueError:
        print(f"{RED}日期格式无效: {target}（需要 YYYY-MM-DD）{RESET}")
        return 1

    data = json.loads(input_path.read_text(encoding="utf-8"))
    data.setdefault("meta", {})["date"] = target
    data.setdefault("share", {})["badge"] = target.replace("-", ".")
    input_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"{GREEN}{BOLD}日期已设置: meta.date={target}  share.badge={target.replace('-', '.')}{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
