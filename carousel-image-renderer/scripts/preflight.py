#!/usr/bin/env python3
"""Check rendering environment dependencies. Zero external dependencies."""

import json
import os
import platform
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent


def check_node():
    node = shutil.which("node")
    if node:
        return {"status": "found", "path": node}
    return {"status": "uncertain", "message": "node not found in PATH; cannot guarantee Node.js is available"}


def check_playwright():
    cwd = Path.cwd()
    candidates = [
        os.environ.get("PLAYWRIGHT_MODULE"),
        os.environ.get("CODEX_NODE_MODULES") and str(Path(os.environ["CODEX_NODE_MODULES"]) / "playwright"),
        str(cwd / "node_modules" / "playwright"),
        str(SKILL_DIR / "node_modules" / "playwright"),
        str(SKILL_DIR.parent / "node_modules" / "playwright"),
    ]
    home = Path.home()
    candidates.append(str(home / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "node_modules" / "playwright"))

    for candidate in candidates:
        if candidate and Path(candidate).is_dir():
            return {"status": "found", "path": candidate}

    return {"status": "uncertain", "message": "playwright not found at known locations; cannot guarantee it is available"}


def check_browser():
    system = platform.system()
    candidates = []

    env_exe = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
    if env_exe:
        candidates.append(env_exe)

    if system == "Darwin":
        candidates += [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
    elif system == "Windows":
        pf = os.environ.get("PROGRAMFILES", "")
        if pf:
            candidates.append(str(Path(pf) / "Google" / "Chrome" / "Application" / "chrome.exe"))
        lpf = os.environ.get("PROGRAMFILES(X86)", "")
        if lpf:
            candidates.append(str(Path(lpf) / "Google" / "Chrome" / "Application" / "chrome.exe"))
        candidates.append(str(Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe"))
    elif system == "Linux":
        candidates += ["/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"]

    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return {"status": "found", "path": candidate}

    return {"status": "uncertain", "message": "no system browser found; Playwright may use its managed browser if installed"}


def main():
    results = {
        "node": check_node(),
        "playwright": check_playwright(),
        "browser": check_browser(),
    }

    all_found = all(r["status"] == "found" for r in results.values())

    for name, result in results.items():
        if result["status"] == "found":
            print(f"[FOUND] {name}: {result['path']}")
        else:
            print(f"[UNCERTAIN] {name}: {result['message']}")

    if all_found:
        print("\nAll dependencies confirmed.")
    else:
        print("\nSome dependencies could not be confirmed. This does not mean they are missing.")

    sys.exit(0)


if __name__ == "__main__":
    main()
