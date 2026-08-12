#!/usr/bin/env python3
"""检查机构版式所需的品牌资产（logo、二维码）是否存在且是可用的 PNG。"""

import struct
from pathlib import Path


FAILURE_MESSAGE = "无法保证存在完整的品牌资产（assets/brand/ 下的 logo 与二维码）"

REQUIRED_ASSETS = (
    "assets/brand/zhifujie-logo.png",
    "assets/brand/zhifujie-qrcode.png",
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def read_png_size(path):
    """读 PNG 头部返回 (宽, 高)；不是合法 PNG 返回 None。"""
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
    except OSError:
        return None

    if len(header) < 24 or not header.startswith(PNG_SIGNATURE):
        return None
    if header[12:16] != b"IHDR":
        return None

    width, height = struct.unpack(">II", header[16:24])
    if width <= 0 or height <= 0:
        return None
    return width, height


def check_brand_assets():
    """返回 (是否通过, 说明)。"""
    skill_root = Path(__file__).resolve().parents[2]
    described = []

    for relative_path in REQUIRED_ASSETS:
        path = skill_root / relative_path
        if not path.is_file():
            return False, FAILURE_MESSAGE

        size = read_png_size(path)
        if size is None:
            return False, FAILURE_MESSAGE

        described.append(f"{path.name} {size[0]}x{size[1]}")

    return True, ", ".join(described)


def main():
    passed, message = check_brand_assets()
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] Brand assets: {message}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
