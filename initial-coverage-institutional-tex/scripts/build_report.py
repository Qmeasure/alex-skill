#!/usr/bin/env python3
"""一条命令完成：Excel 导出 → Tectonic 编译 → 全部交付前检查。任一项不过，退出码非 0。

终稿：
    python scripts/build_report.py <报告目录> --name <公司>_首次覆盖_<日期> [--pre-ipo]
阶段 1 / 3 的独立稿件（只编译并做文字类检查，不做首页和 Key data 检查）：
    python scripts/build_report.py <报告目录> --draft drafts/公司研究_<日期>.tex

检查项：
  1. 交付目录里没有 .md / .docx / .doc
  2. Excel「报告数字」「报告表格」导出（data/ 下恰好一个 .xlsx，或用 --xlsx 指定）
  3. Tectonic 编译成功；日志里无缺字、无超过 1pt 的 Overfull
  4. check_render.py：页数、空白页、首页元素、首页未溢出、文字不越出版心
  5. check_layout.py：页眉线、右栏竖线、正文窄栏、图宽、字体、配色、每页品牌标识
  6. check_first_person.py：正文 0 处「我们」；check_tex_rules.py：正文里没有禁止的写法
  7. anti_fabrication_lint.py：画图脚本、底稿 CSV、稿件 tex
（编译有 900 秒超时；data/ 下有多个候选工作簿时要用 --xlsx 指定）
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
CHECKS = SCRIPTS / "checks"
OVERFULL_TOL = 1.0


def run(label, cmd, cwd=None, timeout=900):
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"{label} 超时（{timeout} 秒）"
    out = (proc.stdout + proc.stderr).strip()
    return proc.returncode == 0, out


def pick_workbook(report, given):
    """联动模型：--xlsx 指定，否则 data/ 下唯一的 *_盈利预测模型_*.xlsx（跳过 ~$ 锁文件）。"""
    if given:
        return (given if given.is_file() else None), f"找不到 {given}"
    cands = [p for p in sorted((report / "data").glob("*.xlsx")) if not p.name.startswith("~$")]
    models = [p for p in cands if "盈利预测" in p.name] or cands
    if len(models) == 1:
        return models[0], ""
    if not models:
        return None, "data/ 下没有 .xlsx"
    return None, "data/ 下有多个候选工作簿（" + "、".join(p.name for p in models) + "），用 --xlsx 指定"


def compile_tex(report, tex_file, pdf_name):
    """用 Tectonic 编译；以报告根目录为搜索路径，稿件和终稿共用 style/、figures/、tables/。"""
    tex_file = Path(tex_file)
    outdir = report / (tex_file.parent if tex_file.parent != Path(".") else Path("."))
    cmd = ["tectonic", "-X", "compile", "--keep-logs", "-Z", f"search-path={report}",
           "--outdir", str(outdir), str(report / tex_file)]
    ok, out = run("tectonic", cmd, cwd=report)
    log = outdir / (tex_file.stem + ".log")
    pdf = outdir / (tex_file.stem + ".pdf")
    if not ok or not pdf.is_file():
        errs = [ln for ln in out.splitlines() if ln.startswith("error")]
        return False, "编译失败：" + " | ".join(errs[:5]), None, log
    final = outdir / f"{pdf_name}.pdf"
    if final != pdf:
        shutil.move(pdf, final)
    return True, f"{final.name}", final, log


def check_log(log):
    text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    missing = re.findall(r"Missing character: There is no (\S+) \(U\+[0-9A-Fa-f]+\) in font", text)
    overs = [float(x) for x in re.findall(r"Overfull \\hbox \(([\d.]+)pt too wide\)", text)]
    bad_over = [x for x in overs if x > OVERFULL_TOL]
    vover = re.findall(r"Overfull \\vbox \(([\d.]+)pt too high\)", text)
    problems = []
    if missing:
        chars = sorted(set(missing))
        problems.append(f"缺字 {len(missing)} 处：{''.join(chars)[:30]}")
    if bad_over:
        problems.append(f"Overfull \\hbox 超过 {OVERFULL_TOL}pt 共 {len(bad_over)} 处，最大 {max(bad_over):.1f}pt")
    if vover:
        problems.append(f"Overfull \\vbox {len(vover)} 处（有块比页面还高，首页或表格没收住）")
    return not problems, "；".join(problems) or "无缺字、无越界盒子"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("report", type=Path)
    ap.add_argument("--name", help="终稿 PDF 文件名（不含扩展名）")
    ap.add_argument("--draft", help="只编译这份阶段稿件（相对报告目录的路径）")
    ap.add_argument("--xlsx", type=Path, help="联动模型路径，默认 data/ 下唯一的 .xlsx")
    ap.add_argument("--pre-ipo", action="store_true")
    ap.add_argument("--pages-min", type=int, default=25)
    ap.add_argument("--pages-max", type=int, default=45)
    args = ap.parse_args()
    report = args.report.resolve()
    py = sys.executable
    results = []

    ok, out = run("no-word-md", [py, str(CHECKS / "check_no_word_md.py"), str(report)])
    results.append(("无 Word / Markdown 文件", ok, out.splitlines()[-1] if out else ""))

    if not args.draft:
        xlsx, why = pick_workbook(report, args.xlsx)
        if xlsx is None:
            results.append(("Excel 导出", False, why))
        else:
            ok, out = run("export", [py, str(SCRIPTS / "export_excel_to_tex.py"), str(xlsx), str(report)])
            results.append(("Excel 导出", ok, out.splitlines()[-1] if out else ""))

    if all(r[1] for r in results):
        tex = args.draft or "main.tex"
        name = Path(tex).stem if args.draft else (args.name or "main")
        ok, detail, pdf, log = compile_tex(report, tex, name)
        results.append(("Tectonic 编译", ok, detail))
        if ok:
            ok, detail = check_log(log)
            results.append(("编译日志", ok, detail))
            if not args.draft:
                cmd = [py, str(CHECKS / "check_render.py"), str(pdf),
                       "--pages-min", str(args.pages_min), "--pages-max", str(args.pages_max)]
                if args.pre_ipo:
                    cmd.append("--pre-ipo")
                ok, out = run("render", cmd)
                results.append(("渲染检查", ok, out))
                ok, out = run("layout", [py, str(CHECKS / "check_layout.py"), str(pdf)])
                results.append(("版式量测", ok, out))
            srcs = [str(report / args.draft)] if args.draft else [str(report)]
            ok, out = run("first-person", [py, str(CHECKS / "check_first_person.py"), *srcs])
            results.append(("第一人称", ok, out.splitlines()[-1] if out else ""))
            if not args.draft:
                ok, out = run("tex-rules", [py, str(CHECKS / "check_tex_rules.py"), str(report)])
                results.append(("tex 禁止项", ok, out))
            lint_in = [p for p in [report / "figures" / "build_charts.py",
                                   *sorted((report / "data" / "_data").glob("*.csv")),
                                   *sorted((report / "drafts").glob("*.tex")),
                                   *sorted((report / "chapters").glob("*.tex"))] if p.is_file()]
            ok, out = run("lint", [py, str(SCRIPTS / "anti_fabrication_lint.py"), *map(str, lint_in)])
            results.append(("反编造 lint", ok, out.splitlines()[-1] if out else ""))

    width = max(len(r[0]) for r in results)
    for label, ok, detail in results:
        head = f"[{'PASS' if ok else 'FAIL'}] {label:<{width}}"
        lines = detail.splitlines() or [""]
        print(f"{head}  {lines[0]}")
        for extra in lines[1:]:
            print(f"{'':<{len(head)}}  {extra}")
    if all(r[1] for r in results):
        print("[PASS] 全部检查通过，可以交付")
        return 0
    print("[FAIL] 有检查未通过，不交付")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
