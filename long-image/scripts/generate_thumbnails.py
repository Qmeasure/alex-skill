#!/usr/bin/env python3
"""Generate or import page thumbnails and update the input JSON.

Usage:
    # Auto-convert from PDF/DOCX source:
    python scripts/generate_thumbnails.py input.json --source report.pdf
    python scripts/generate_thumbnails.py input.json --source report.docx

    # Import pre-made images (for HTML sources or agent-generated thumbnails):
    python scripts/generate_thumbnails.py input.json --import img1.png img2.png ...

    # Options:
    --pages N        Number of thumbnails to show (default: 4)
    --thumb-width N  Embedded thumbnail width in px (default: 240)
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"


def convert_pdf_to_thumbnails(
    pdf_path: Path, thumb_dir: Path, pages: int
) -> tuple[int, int]:
    """Convert first N pages of a PDF to PNG thumbnails. Returns (generated, total)."""
    from pdf2image import convert_from_path
    from pdf2image.pdf2image import pdfinfo_from_path

    total = pdfinfo_from_path(str(pdf_path)).get("Pages", 0)
    count = min(pages, total) if total else pages
    images = convert_from_path(str(pdf_path), first_page=1, last_page=count, dpi=150)
    for i, img in enumerate(images):
        img.save(thumb_dir / f"page_{i + 1:02d}.png", "PNG")
    return len(images), total


def convert_docx_to_pdf(docx_path: Path, output_dir: Path) -> Path:
    """Convert DOCX to PDF via LibreOffice headless."""
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
    result = subprocess.run(
        [
            soffice,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_dir),
            str(docx_path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"LibreOffice 转换失败 (exit {result.returncode}):\n{result.stderr}"
        )
    pdf_name = docx_path.stem + ".pdf"
    pdf_path = output_dir / pdf_name
    if not pdf_path.exists():
        raise RuntimeError(f"LibreOffice 转换后未找到输出文件: {pdf_path}")
    return pdf_path


def import_images(image_paths: list[Path], thumb_dir: Path) -> int:
    """Copy pre-made images into the thumbnail directory. Returns count."""
    for i, src in enumerate(image_paths):
        if not src.exists():
            raise FileNotFoundError(f"图片不存在: {src}")
        dest = thumb_dir / f"page_{i + 1:02d}.png"
        if src.suffix.lower() == ".png":
            shutil.copy2(src, dest)
        else:
            from PIL import Image

            Image.open(src).save(dest, "PNG")
    return len(image_paths)


def update_json(
    input_path: Path,
    thumb_dir_name: str,
    pages: int,
    thumb_width: int,
    total_pages: int,
) -> None:
    """Write docx_preview into the input JSON."""
    data = json.loads(input_path.read_text(encoding="utf-8"))
    data["docx_preview"] = {
        "dir": thumb_dir_name,
        "pages": pages,
        "thumb_width": thumb_width,
        "total_pages": total_pages,
    }
    input_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate or import page thumbnails for long-image."
    )
    parser.add_argument("input", help="Input JSON file.")
    parser.add_argument(
        "--source",
        help="Source document (PDF or DOCX) to auto-convert.",
    )
    parser.add_argument(
        "--import",
        nargs="+",
        dest="import_images",
        metavar="IMG",
        help="Pre-made image files to import as thumbnails.",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=4,
        help="Number of thumbnails to generate/show (default: 4).",
    )
    parser.add_argument(
        "--thumb-width",
        type=int,
        default=240,
        help="Embedded thumbnail width in px (default: 240).",
    )
    args = parser.parse_args()

    if not args.source and not args.import_images:
        print(f"{RED}必须指定 --source 或 --import 之一。{RESET}")
        return 1
    if args.source and args.import_images:
        print(f"{RED}--source 和 --import 不能同时使用。{RESET}")
        return 1

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"{RED}输入文件不存在: {input_path}{RESET}")
        return 1

    thumb_dir_name = "_page_thumbs"
    thumb_dir = input_path.parent / thumb_dir_name
    thumb_dir.mkdir(parents=True, exist_ok=True)

    # Clean existing thumbnails
    for old in thumb_dir.glob("page_*.png"):
        old.unlink()

    try:
        if args.import_images:
            # --import mode
            image_paths = [Path(p) for p in args.import_images]
            count = import_images(image_paths, thumb_dir)
            total = count
            show = min(args.pages, count)
            print(f"{GREEN}{BOLD}已导入 {count} 张缩略图到 {thumb_dir}{RESET}")

        else:
            # --source mode
            source = Path(args.source)
            if not source.exists():
                print(f"{RED}源文件不存在: {source}{RESET}")
                return 1

            ext = source.suffix.lower()

            if ext == ".pdf":
                count, total = convert_pdf_to_thumbnails(
                    source, thumb_dir, args.pages
                )
                show = count
                print(
                    f"{GREEN}{BOLD}已从 PDF 生成 {count} 张缩略图"
                    f"（共 {total} 页）{RESET}"
                )

            elif ext in (".docx", ".doc"):
                with tempfile.TemporaryDirectory() as tmp:
                    tmp_dir = Path(tmp)
                    print(f"  正在通过 LibreOffice 转换 DOCX → PDF ...")
                    pdf_path = convert_docx_to_pdf(source, tmp_dir)
                    count, total = convert_pdf_to_thumbnails(
                        pdf_path, thumb_dir, args.pages
                    )
                    show = count
                print(
                    f"{GREEN}{BOLD}已从 DOCX 生成 {count} 张缩略图"
                    f"（共 {total} 页）{RESET}"
                )

            else:
                print(
                    f"{RED}不支持的源文件格式: {ext}{RESET}\n"
                    f"PDF/DOCX 使用 --source，其他格式请用 --import 导入已有图片。"
                )
                return 1

        update_json(input_path, thumb_dir_name, show, args.thumb_width, total)
        print(f"  已更新 {input_path.name} 的 docx_preview 字段。")

    except Exception as exc:
        print(f"{RED}{BOLD}缩略图生成失败: {exc}{RESET}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
