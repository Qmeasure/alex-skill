#!/usr/bin/env python3
"""按 uv > pip 的优先级检查 Python 包管理器是否可以启动。"""

import shutil
import subprocess
import sys


FAILURE_MESSAGE = "无法保证存在完整的 Python 依赖环境"


def run_version_command(command):
    """运行版本命令，成功时返回第一行输出，失败时返回 None。"""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0:
        return None

    output = (result.stdout or result.stderr).strip()
    return output.splitlines()[0] if output else "启动成功"


def check_python_package_manager():
    """返回 (是否通过, 说明)。"""
    uv = shutil.which("uv")
    if uv:
        version = run_version_command([uv, "--version"])
        if version:
            return True, f"uv: {version}"

    pip_version = run_version_command(
        [sys.executable, "-m", "pip", "--version"]
    )
    if pip_version:
        return True, f"pip: {pip_version}"

    return False, FAILURE_MESSAGE


def main():
    passed, message = check_python_package_manager()
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] Python package manager: {message}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
