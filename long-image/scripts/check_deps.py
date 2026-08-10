#!/usr/bin/env python3
"""Pre-flight dependency check for long-image skill. Zero external deps."""

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PACKAGES = [
    ("playwright", "playwright", "HTML → PNG 渲染"),
    ("PIL", "Pillow", "缩略图处理"),
    ("pdf2image", "pdf2image", "PDF 页数检测与缩略图生成"),
]

REQUIRED_ASSETS = [
    ("assets/brand.json", "品牌配置"),
    ("assets/footer-tech-blue.png", "底栏背景"),
    ("assets/zhifujie-qr.png", "二维码"),
]

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"


def tag_pass(label: str) -> None:
    print(f"  {GREEN}✓{RESET} {label}")


def tag_fail(label: str, hint: str = "") -> None:
    msg = f"  {RED}?{RESET} {label} — 无法确认存在"
    if hint:
        msg += f"  {YELLOW}→ {hint}{RESET}"
    print(msg)


def tag_warn(label: str, hint: str = "") -> None:
    msg = f"  {YELLOW}~{RESET} {label}"
    if hint:
        msg += f"  {YELLOW}→ {hint}{RESET}"
    print(msg)


def check_python() -> bool:
    v = sys.version_info
    label = f"Python {v.major}.{v.minor}.{v.micro}"
    if v >= (3, 10):
        tag_pass(label)
        return True
    tag_fail(label, "需要 Python 3.10+")
    return False


def check_package_manager() -> str | None:
    if shutil.which("uv"):
        tag_pass("uv (包管理器)")
        return "uv"
    if shutil.which("pip") or shutil.which("pip3"):
        tag_warn("uv 未找到，回退到 pip", "推荐安装 uv: https://docs.astral.sh/uv/")
        return "pip"
    tag_fail("uv 或 pip", "至少需要一个包管理器")
    return None


def check_package(import_name: str, pip_name: str, purpose: str) -> bool:
    try:
        importlib.import_module(import_name)
        tag_pass(f"{pip_name} ({purpose})")
        return True
    except ImportError:
        tag_fail(f"{pip_name} ({purpose})", f"uv pip install {pip_name}")
        return False


def check_chromium() -> bool:
    try:
        result = subprocess.run(
            [sys.executable, "-c",
             "from playwright.sync_api import sync_playwright;"
             "p=sync_playwright().start();"
             "b=p.chromium.launch();"
             "b.close();p.stop()"],
            capture_output=True, timeout=30,
        )
        if result.returncode == 0:
            tag_pass("Playwright Chromium 浏览器")
            return True
        tag_fail("Playwright Chromium 浏览器", "可尝试 playwright install chromium")
        return False
    except Exception:
        tag_fail("Playwright Chromium 浏览器", "可尝试 playwright install chromium")
        return False


def check_assets() -> list[str]:
    missing = []
    for rel_path, purpose in REQUIRED_ASSETS:
        full = SKILL_ROOT / rel_path
        if full.exists():
            tag_pass(f"{rel_path} ({purpose})")
        else:
            tag_fail(f"{rel_path} ({purpose})")
            missing.append(rel_path)
    return missing


def check_render_script() -> bool:
    path = SKILL_ROOT / "scripts" / "render_mobile_share.py"
    if path.exists():
        tag_pass("scripts/render_mobile_share.py")
        return True
    tag_fail("scripts/render_mobile_share.py")
    return False


def main() -> int:
    print(f"\n{BOLD}long-image 依赖检查{RESET}")
    print(f"  skill 路径: {SKILL_ROOT}\n")

    errors = 0

    print(f"{BOLD}[运行环境]{RESET}")
    if not check_python():
        errors += 1
    if check_package_manager() is None:
        errors += 1

    print(f"\n{BOLD}[Python 包]{RESET}")
    playwright_ok = True
    for import_name, pip_name, purpose in REQUIRED_PACKAGES:
        if not check_package(import_name, pip_name, purpose):
            errors += 1
            if import_name == "playwright":
                playwright_ok = False

    print(f"\n{BOLD}[浏览器]{RESET}")
    if playwright_ok:
        if not check_chromium():
            errors += 1
    else:
        tag_fail("Playwright Chromium 浏览器", "需先确认 playwright 可用")
        errors += 1

    print(f"\n{BOLD}[品牌资产]{RESET}")
    errors += len(check_assets())

    print(f"\n{BOLD}[渲染脚本]{RESET}")
    if not check_render_script():
        errors += 1

    print()
    if errors == 0:
        print(f"{GREEN}{BOLD}全部通过，可以开始生成长图。{RESET}\n")
        return 0
    else:
        print(f"{RED}{BOLD}{errors} 项无法确认，无法保证相关依赖存在。{RESET}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
