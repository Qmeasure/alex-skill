#!/usr/bin/env python3
"""检查内嵌 xlsx/docx Skill 的关键入口与直接资源是否可读。"""

from pathlib import Path


FAILURE_MESSAGE = "无法保证存在完整的内嵌 xlsx/docx Skill 环境"

REQUIRED_PATHS = (
    "anthropic_skills/xlsx/SKILL.md",
    "anthropic_skills/xlsx/LICENSE.txt",
    "anthropic_skills/xlsx/scripts/recalc.py",
    "anthropic_skills/xlsx/scripts/office/soffice.py",
    "anthropic_skills/docx/SKILL.md",
    "anthropic_skills/docx/LICENSE.txt",
    "anthropic_skills/docx/scripts/accept_changes.py",
    "anthropic_skills/docx/scripts/comment.py",
    "anthropic_skills/docx/scripts/merge_runs.py",
    "anthropic_skills/docx/scripts/office/soffice.py",
    "anthropic_skills/docx/scripts/office/validate.py",
    "anthropic_skills/docx/scripts/office/schemas",
)


def check_embedded_skills():
    """返回 (是否通过, 说明)。"""
    skill_root = Path(__file__).resolve().parents[2]

    for relative_path in REQUIRED_PATHS:
        path = skill_root / relative_path
        if not path.exists():
            return False, FAILURE_MESSAGE
        if path.is_file():
            try:
                with path.open("rb") as handle:
                    handle.read(1)
            except OSError:
                return False, FAILURE_MESSAGE

    return True, "xlsx, docx"


def main():
    passed, message = check_embedded_skills()
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] Embedded skills: {message}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
