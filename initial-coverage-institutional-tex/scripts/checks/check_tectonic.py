#!/usr/bin/env python3
"""环境检查：Tectonic 可用，且能用 ctexart + 思源宋体编译出 PDF。

本机没有 TeX Live，Tectonic 是唯一的编译引擎；首次编译会按需联网拉宏包。
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FAILURE = "无法保证存在可用的 TeX 编译环境"
SAMPLE = r"""\documentclass{ctexart}
\setCJKmainfont{Source Han Serif CN}[BoldFont={Source Han Serif CN Bold}]
\usepackage{xfp,tabularray,eso-pic,graphicx,xcolor,enumitem,hyperref}
\begin{document}
智富界 \textbf{首次覆盖} 2026 \fpeval{1+1}
\end{document}
"""


def main():
    exe = shutil.which("tectonic")
    if exe is None:
        print(f"[FAIL] Tectonic: 未找到 tectonic 命令（brew install tectonic），{FAILURE}")
        return 1
    ver = subprocess.run([exe, "--version"], capture_output=True, text=True).stdout.strip()
    with tempfile.TemporaryDirectory() as td:
        tex = Path(td) / "probe.tex"
        tex.write_text(SAMPLE, encoding="utf-8")
        try:
            proc = subprocess.run([exe, "-X", "compile", str(tex)], cwd=td, capture_output=True,
                                  text=True, timeout=600, check=False)
        except subprocess.TimeoutExpired:
            print(f"[FAIL] Tectonic: 样张编译超时，{FAILURE}")
            return 1
        pdf = Path(td) / "probe.pdf"
        if proc.returncode != 0 or not pdf.is_file():
            err = [ln for ln in (proc.stdout + proc.stderr).splitlines() if ln.startswith("error")]
            print(f"[FAIL] Tectonic: 样张编译失败 {' | '.join(err[:3])}，{FAILURE}")
            return 1
        fonts = subprocess.run(["pdffonts", str(pdf)], capture_output=True, text=True).stdout \
            if shutil.which("pdffonts") else ""
    if fonts and "SourceHanSerifCN" not in fonts:
        print(f"[FAIL] Tectonic: 样张未嵌入思源宋体，{FAILURE}")
        return 1
    print(f"[PASS] Tectonic: {ver}，ctexart + 思源宋体样张编译通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
