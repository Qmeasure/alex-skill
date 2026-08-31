#!/usr/bin/env python3
"""检查系统字体文件中的思源宋体及相似候选。"""

from pathlib import Path


FAILURE_MESSAGE = "无法保证存在思源宋体环境"
EXPECTED_FAMILY = "Source Han Serif CN"
SIMILAR_NAME_PARTS = (
    "source han serif",
    "sourcehanserif",
    "noto serif cjk",
    "思源宋体",
)


def check_source_han_serif():
    """返回 (PASS/REVIEW/FAIL, 说明)。"""
    try:
        from matplotlib import font_manager

        font_paths = {
            *font_manager.findSystemFonts(fontext="ttf"),
            *font_manager.findSystemFonts(fontext="otf"),
        }
    except Exception:
        return "FAIL", FAILURE_MESSAGE

    candidates = []
    for font_path in sorted(font_paths):
        resolved_path = Path(font_path)
        if not resolved_path.is_file():
            continue
        try:
            family = font_manager.FontProperties(
                fname=str(resolved_path)
            ).get_name()
        except Exception:
            continue
        searchable = f"{family} {resolved_path.name}".lower()
        if any(part in searchable for part in SIMILAR_NAME_PARTS):
            candidates.append((family, resolved_path))

    exact_matches = [
        (family, path)
        for family, path in candidates
        if family == EXPECTED_FAMILY
    ]
    if exact_matches:
        family, path = exact_matches[0]
        return "PASS", f"{family} ({path})"

    if candidates:
        unique_candidates = {}
        for family, path in candidates:
            unique_candidates.setdefault(family, path)
        return "REVIEW", "发现可能相关字体，请判断：" + "; ".join(
            f"{family} ({path})"
            for family, path in unique_candidates.items()
        )

    return "FAIL", FAILURE_MESSAGE


def main():
    status, message = check_source_han_serif()
    print(f"[{status}] Font: {message}")
    if status == "PASS":
        return 0
    if status == "REVIEW":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
