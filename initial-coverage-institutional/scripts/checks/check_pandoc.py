#!/usr/bin/env python3
"""检查 Pandoc 二进制是否可以启动。"""

import shutil
import subprocess


FAILURE_MESSAGE = "无法保证存在 Pandoc 环境"


def check_pandoc():
    """返回 (是否通过, 说明)。"""
    pandoc = shutil.which("pandoc")
    if pandoc is None:
        return False, FAILURE_MESSAGE

    try:
        result = subprocess.run(
            [pandoc, "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, FAILURE_MESSAGE

    if result.returncode != 0:
        return False, FAILURE_MESSAGE

    output = (result.stdout or result.stderr).strip()
    detail = output.splitlines()[0] if output else "启动成功"
    return True, detail


def main():
    passed, message = check_pandoc()
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] Pandoc: {message}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
