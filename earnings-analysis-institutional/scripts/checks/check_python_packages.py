#!/usr/bin/env python3
"""检查完整的 Python 包依赖是否均可导入。"""

import importlib
import importlib.metadata
import shutil
import subprocess


REQUIRED_PACKAGES = (
    ("matplotlib", "matplotlib"),
    ("pandas", "pandas"),
    ("openpyxl", "openpyxl"),
    ("python-docx", "docx"),
    ("markitdown", "markitdown"),
    ("defusedxml", "defusedxml"),
    ("lxml", "lxml"),
)

FAILURE_MESSAGE = "无法保证存在完整的 Python 依赖环境"


def check_python_packages():
    """返回 (是否通过, 说明)。"""
    versions = []

    for distribution_name, import_name in REQUIRED_PACKAGES:
        try:
            importlib.import_module(import_name)
            version = importlib.metadata.version(distribution_name)
        except Exception:
            return False, FAILURE_MESSAGE
        versions.append(f"{distribution_name} {version}")

    markitdown = shutil.which("markitdown")
    if markitdown is None:
        return False, FAILURE_MESSAGE

    try:
        result = subprocess.run(
            [markitdown, "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, FAILURE_MESSAGE

    if result.returncode != 0:
        return False, FAILURE_MESSAGE

    return True, ", ".join(versions)


def main():
    passed, message = check_python_packages()
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] Python packages: {message}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
