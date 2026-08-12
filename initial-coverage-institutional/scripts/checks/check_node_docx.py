#!/usr/bin/env python3
"""检查 Node.js、npm 和 docx 包是否可以启动或加载。"""

import os
import shutil
import subprocess
from pathlib import Path


FAILURE_MESSAGE = "无法保证存在完整的 Node.js DOCX 环境"


def run_command(command, cwd=None, env=None):
    """运行命令，成功时返回第一行输出，失败时返回 None。"""
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
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


def check_node_docx():
    """返回 (是否通过, 说明)。"""
    node = shutil.which("node")
    npm = shutil.which("npm")
    if node is None or npm is None:
        return False, FAILURE_MESSAGE

    node_version = run_command([node, "--version"])
    npm_version = run_command([npm, "--version"])
    if node_version is None or npm_version is None:
        return False, FAILURE_MESSAGE

    skill_root = Path(__file__).resolve().parents[2]
    docx_skill_dir = skill_root / "anthropic_skills" / "docx"

    # docx 通常装在 npm 全局目录里。node 默认不解析全局 node_modules，
    # 必须显式把 `npm root -g` 加进 NODE_PATH，否则 require('docx') 会假失败。
    env = dict(os.environ)
    global_root = run_command([npm, "root", "-g"])
    if global_root:
        existing = env.get("NODE_PATH")
        env["NODE_PATH"] = f"{global_root}{os.pathsep}{existing}" if existing else global_root

    docx_result = run_command(
        [node, "-e", "require('docx'); console.log('docx resolvable')"],
        cwd=docx_skill_dir,
        env=env,
    )
    if docx_result is None:
        return False, FAILURE_MESSAGE

    return True, f"node {node_version}, npm {npm_version}, {docx_result}"


def main():
    passed, message = check_node_docx()
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] Node.js DOCX: {message}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
