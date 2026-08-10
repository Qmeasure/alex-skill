#!/usr/bin/env python3
"""Run the deterministic post-JSON pipeline: check thumbnails → render → verify.

Usage:
    python scripts/pipeline.py input.json [--output-dir DIR] [--html-only]

Chains check_thumbnails, render_mobile_share, and verify_output in sequence.
Stops at the first failure. Renders and verifies the output in one command.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent

RED = "\033[91m"
GREEN = "\033[92m"
BOLD = "\033[1m"
RESET = "\033[0m"


def run_step(label: str, cmd: list[str]) -> bool:
    separator = "─" * 50
    print(f"\n{BOLD}{separator}{RESET}")
    print(f"{BOLD}▶ {label}{RESET}")
    print(f"{BOLD}{separator}{RESET}\n")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"\n{RED}{BOLD}✗ {label} 失败 (exit {result.returncode}){RESET}")
        return False
    return True


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the full post-JSON pipeline: check → render → verify."
    )
    parser.add_argument("input", help="Input JSON file.")
    parser.add_argument(
        "--output-dir",
        help="Output directory. Defaults to the input directory.",
    )
    parser.add_argument(
        "--html-only",
        action="store_true",
        help="Debug only: skip PNG output in render step.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"{RED}输入文件不存在: {input_path}{RESET}")
        return 1

    python = sys.executable
    output_args = ["--output-dir", args.output_dir] if args.output_dir else []

    steps = [
        (
            "缩略图检查",
            [python, str(SCRIPTS_DIR / "check_thumbnails.py"), str(input_path)],
        ),
        (
            "渲染",
            [python, str(SCRIPTS_DIR / "render_mobile_share.py"), str(input_path)]
            + output_args
            + (["--html-only"] if args.html_only else []),
        ),
        (
            "输出验收",
            [python, str(SCRIPTS_DIR / "verify_output.py"), str(input_path)]
            + output_args,
        ),
    ]

    for label, cmd in steps:
        if not run_step(label, cmd):
            print(f"\n{RED}{BOLD}Pipeline 在「{label}」步骤中止。{RESET}\n")
            return 1

    print(f"\n{GREEN}{BOLD}Pipeline 全部通过。{RESET}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
