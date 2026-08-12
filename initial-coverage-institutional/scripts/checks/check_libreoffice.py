#!/usr/bin/env python3
"""检查 LibreOffice 二进制是否存在且可以启动。"""

import shutil
import subprocess


def find_libreoffice():
    """返回 PATH 中的 soffice 路径，找不到时返回 None。"""
    return shutil.which("soffice")


def check_libreoffice():
    """返回 (是否通过, 说明)。"""
    executable = find_libreoffice()
    if executable is None:
        return False, "无法保证存在 LibreOffice 环境"

    try:
        result = subprocess.run(
            [str(executable), "--headless", "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, "无法保证存在 LibreOffice 环境"

    output = (result.stdout or result.stderr).strip()
    if result.returncode != 0:
        return False, "无法保证存在 LibreOffice 环境"

    detail = output.splitlines()[0] if output else "启动成功"
    return True, f"{detail} ({executable})"


def main():
    passed, message = check_libreoffice()
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] LibreOffice: {message}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
