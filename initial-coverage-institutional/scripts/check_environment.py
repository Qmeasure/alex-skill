#!/usr/bin/env python3
"""运行 initial-coverage-institutional 的全部本地环境检查。"""

import subprocess
import sys
from pathlib import Path


CHECK_SCRIPTS = (
    "check_libreoffice.py",
    "check_python_package_manager.py",
    "check_python_packages.py",
    "check_embedded_skills.py",
    "check_node_docx.py",
    "check_pandoc.py",
    "check_pdftoppm.py",
    "check_source_han_serif.py",
    "check_brand_assets.py",
)


def run_check(path):
    """运行单项检查并返回其退出码和可见输出。"""
    try:
        result = subprocess.run(
            [sys.executable, "-B", str(path)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 1, f"[FAIL] {path.stem}: 无法保证完成该项环境检查"

    output = (result.stdout or result.stderr).strip()
    if not output:
        output = f"[FAIL] {path.stem}: 无法保证完成该项环境检查"

    if result.returncode not in (0, 1, 2):
        return 1, output
    return result.returncode, output


def main():
    checks_dir = Path(__file__).resolve().parent / "checks"
    has_failure = False
    has_review = False

    for script_name in CHECK_SCRIPTS:
        returncode, output = run_check(checks_dir / script_name)
        print(output)
        if returncode == 1:
            has_failure = True
        elif returncode == 2:
            has_review = True

    if has_failure:
        print("[FAIL] Environment: 无法保证存在完整的运行环境")
        return 1
    if has_review:
        print("[REVIEW] Environment: 存在需要 Agent 判断的环境检查项")
        return 2

    print("[PASS] Environment: 所有本地环境检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
