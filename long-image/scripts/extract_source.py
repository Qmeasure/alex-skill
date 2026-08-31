#!/usr/bin/env python3
"""Extract source document content for the long-image workflow.

PDF/DOCX → PaddleOCR API → Markdown + images
HTML      → copy as-is

Usage:
    python scripts/extract_source.py report.pdf
    python scripts/extract_source.py report.docx
    python scripts/extract_source.py page.html
    python scripts/extract_source.py report.pdf --output-dir workdir/
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]

PADDLEOCR_JOB_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
PADDLEOCR_MODEL = "PaddleOCR-VL-1.6"
POLL_INTERVAL = 5

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"


def load_env() -> None:
    """Load .env file from the skill root into os.environ."""
    env_path = SKILL_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_token() -> str:
    load_env()
    token = os.environ.get("PADDLEOCR_TOKEN", "")
    if not token:
        print(
            f"{RED}PADDLEOCR_TOKEN 未设置。请在 .env 文件中配置，"
            f"参考 .env.example。{RESET}"
        )
        sys.exit(1)
    return token


# ---------------------------------------------------------------------------
# PaddleOCR API
# ---------------------------------------------------------------------------

def submit_job(file_path: Path, token: str) -> str:
    """Submit a file to PaddleOCR API and return the job ID."""
    import requests

    headers = {"Authorization": f"bearer {token}"}
    data = {
        "model": PADDLEOCR_MODEL,
        "optionalPayload": json.dumps(
            {
                "useDocOrientationClassify": False,
                "useDocUnwarping": False,
                "useChartRecognition": False,
            }
        ),
    }
    with open(file_path, "rb") as f:
        resp = requests.post(
            PADDLEOCR_JOB_URL, headers=headers, data=data, files={"file": f}
        )
    if resp.status_code != 200:
        raise RuntimeError(
            f"PaddleOCR API 提交失败 (HTTP {resp.status_code}): {resp.text}"
        )
    return resp.json()["data"]["jobId"]


def poll_job(job_id: str, token: str) -> str:
    """Poll until the job completes. Returns the result JSONL URL."""
    import requests

    headers = {"Authorization": f"bearer {token}"}
    while True:
        resp = requests.get(f"{PADDLEOCR_JOB_URL}/{job_id}", headers=headers)
        resp.raise_for_status()
        data = resp.json()["data"]
        state = data["state"]

        if state == "pending":
            print("  状态: 排队中 ...")
        elif state == "running":
            progress = data.get("extractProgress", {})
            total = progress.get("totalPages", "?")
            done = progress.get("extractedPages", "?")
            print(f"  状态: 处理中 ({done}/{total} 页)")
        elif state == "done":
            progress = data["extractProgress"]
            print(
                f"  完成: {progress['extractedPages']} 页，"
                f"耗时 {progress.get('endTime', '?')}"
            )
            return data["resultUrl"]["jsonUrl"]
        elif state == "failed":
            raise RuntimeError(f"PaddleOCR 任务失败: {data.get('errorMsg', '未知')}")
        else:
            print(f"  未知状态: {state}")

        time.sleep(POLL_INTERVAL)


def download_results(
    jsonl_url: str, output_dir: Path, images_dir: Path
) -> list[str]:
    """Download JSONL results and return per-page markdown texts."""
    import requests

    resp = requests.get(jsonl_url)
    resp.raise_for_status()

    pages: list[str] = []
    page_num = 0

    for line in resp.text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        result = json.loads(line)["result"]
        for res in result["layoutParsingResults"]:
            md_text = res["markdown"]["text"]

            # Download images referenced in the markdown
            for img_ref, img_url in res["markdown"].get("images", {}).items():
                local_path = images_dir / img_ref
                local_path.parent.mkdir(parents=True, exist_ok=True)
                img_bytes = requests.get(img_url).content
                with open(local_path, "wb") as f:
                    f.write(img_bytes)
                # Rewrite image path in markdown to relative reference
                rel = os.path.relpath(local_path, output_dir).replace("\\", "/")
                md_text = md_text.replace(img_ref, rel)

            pages.append(md_text)
            page_num += 1

    return pages


def extract_pdf(source: Path, output_dir: Path) -> Path:
    """Extract PDF via PaddleOCR API. Returns path to source_content.md."""
    token = get_token()
    images_dir = output_dir / "_source_images"
    images_dir.mkdir(parents=True, exist_ok=True)

    print(f"  提交 PDF 到 PaddleOCR API ...")
    job_id = submit_job(source, token)
    print(f"  任务 ID: {job_id}")

    jsonl_url = poll_job(job_id, token)
    print(f"  下载提取结果 ...")
    pages = download_results(jsonl_url, output_dir, images_dir)

    # Merge pages into one markdown
    output_path = output_dir / "source_content.md"
    merged = []
    for i, page_md in enumerate(pages):
        merged.append(f"<!-- 第 {i + 1} 页 -->\n\n{page_md}")
    output_path.write_text("\n\n---\n\n".join(merged), encoding="utf-8")
    return output_path


def extract_docx(source: Path, output_dir: Path) -> Path:
    """Convert DOCX to PDF via LibreOffice, then extract via PaddleOCR API."""
    soffice = shutil.which("soffice")
    if not soffice:
        for candidate in (
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        ):
            if Path(candidate).exists():
                soffice = candidate
                break
    if not soffice:
        raise RuntimeError(
            "LibreOffice 未找到。请安装 LibreOffice 或将 soffice 加入 PATH。"
        )

    with tempfile.TemporaryDirectory() as tmp:
        print(f"  通过 LibreOffice 转换 DOCX → PDF ...")
        result = subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", tmp, str(source)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"LibreOffice 转换失败 (exit {result.returncode}):\n{result.stderr}"
            )
        pdf_path = Path(tmp) / (source.stem + ".pdf")
        if not pdf_path.exists():
            raise RuntimeError(f"LibreOffice 转换后未找到: {pdf_path}")
        return extract_pdf(pdf_path, output_dir)


def extract_html(source: Path, output_dir: Path) -> Path:
    """Copy HTML source as-is."""
    output_path = output_dir / "source_content.html"
    shutil.copy2(source, output_path)
    return output_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract source document content for long-image."
    )
    parser.add_argument("source", help="Source document (PDF, DOCX, or HTML).")
    parser.add_argument(
        "--output-dir",
        help="Output directory. Defaults to the source file's directory.",
    )
    args = parser.parse_args()

    source = Path(args.source)
    if not source.exists():
        print(f"{RED}源文件不存在: {source}{RESET}")
        return 1

    output_dir = Path(args.output_dir) if args.output_dir else source.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    ext = source.suffix.lower()

    print(f"\n{BOLD}提取源文档: {source.name}{RESET}\n")

    try:
        if ext == ".pdf":
            out = extract_pdf(source, output_dir)
        elif ext in (".docx", ".doc"):
            out = extract_docx(source, output_dir)
        elif ext in (".html", ".htm"):
            out = extract_html(source, output_dir)
        else:
            print(
                f"{YELLOW}未识别的格式 ({ext})，按 HTML 处理（原样复制）。{RESET}"
            )
            out = extract_html(source, output_dir)

        print(f"\n{GREEN}{BOLD}提取完成: {out}{RESET}\n")
        return 0

    except Exception as exc:
        print(f"\n{RED}{BOLD}提取失败: {exc}{RESET}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
