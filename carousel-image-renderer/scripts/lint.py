#!/usr/bin/env python3
"""Emit mechanical style diagnostics for carousel Markdown."""

import argparse
import json
import re
from pathlib import Path


AI_BLACKLISTED_PHRASES = (
    "证据最完整的落点",
    "先说清楚",
)


def error(code, message, **details):
    return {"code": code, "severity": "error", "message": message, **details}


def warning(code, message, **details):
    return {"code": code, "severity": "warning", "message": message, **details}


def parse_front_matter(text):
    if not text.startswith("---\n"):
        return {}, {}, text, 0, []
    close = text.find("\n---\n", 4)
    if close == -1:
        return {}, {}, text, 0, [error(
            "E_FRONT_MATTER_PARSE",
            "Front matter starts with --- but has no closing --- line.",
            line=1,
            actual="---",
            expected="A closing --- line after the front matter fields",
            action="Add the closing --- line or remove the opening one.",
        )]
    meta = {}
    meta_lines = {}
    findings = []
    for line_number, line in enumerate(text[4:close].split("\n"), start=2):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        sep = line.find(":")
        if sep == -1:
            findings.append(error(
                "E_FRONT_MATTER_PARSE",
                f"Invalid front matter on line {line_number}: expected key: value.",
                line=line_number,
                actual=line,
                expected="Front matter lines use key: value syntax",
                action="Fix the line to key: value form or remove it.",
            ))
            continue
        key = line[:sep].strip()
        value = line[sep + 1:].strip().strip("\"'")
        meta[key] = value
        meta_lines[key] = line_number
    body_start = close + 5
    return meta, meta_lines, text[body_start:], text[:body_start].count("\n"), findings


def mask_matches(pattern, text):
    """Remove matched content without changing later line numbers."""
    return pattern.sub(lambda match: "\n" * match.group(0).count("\n"), text)


def strip_directives_content(body, directive):
    pattern = re.compile(
        rf"^:::{directive}(?:\s.*)?$\n(.*?\n)^:::$",
        re.MULTILINE | re.DOTALL,
    )
    return mask_matches(pattern, body)


def strip_code_blocks(body):
    pattern = re.compile(r"^(`{3,}|~{3,}).*?\n.*?^\1\s*$", re.MULTILINE | re.DOTALL)
    return mask_matches(pattern, body)


def split_sections(body):
    parts = re.split(r"^:::(?:section|pagebreak)(?:\s.*)?$", body, flags=re.MULTILINE)
    return [part for part in parts if part.strip()]


def count_numbers(text):
    clean = strip_code_blocks(text)
    clean = re.sub(r"^:::\w+.*$", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"^:::$", "", clean, flags=re.MULTILINE)
    return len(re.findall(r"\d[\d,.]*%?", clean))


def lint(filepath):
    text = re.sub(r"\r\n?", "\n", Path(filepath).read_text(encoding="utf-8"))
    meta, meta_lines, body, body_line_offset, findings = parse_front_matter(text)
    body_no_code = strip_code_blocks(body)
    absolute_line = lambda line: body_line_offset + line

    for field in ("title", "subtitle", "kicker"):
        value = meta.get(field, "")
        for phrase in AI_BLACKLISTED_PHRASES:
            if phrase in value:
                findings.append(error(
                    "E_AI_BLACKLIST_PHRASE",
                    f'Visible copy contains blacklisted AI wording “{phrase}”.',
                    line=meta_lines.get(field),
                    actual=phrase,
                    action="Rewrite the visible copy without the blacklisted phrase.",
                ))

    blacklisted_body = strip_directives_content(body_no_code, "thumbnails")
    for line_number, line in enumerate(blacklisted_body.split("\n"), start=1):
        if line.strip().startswith(":::"):
            continue
        for phrase in AI_BLACKLISTED_PHRASES:
            if phrase in line:
                findings.append(error(
                    "E_AI_BLACKLIST_PHRASE",
                    f'Visible copy contains blacklisted AI wording “{phrase}”.',
                    line=absolute_line(line_number),
                    actual=phrase,
                    action="Rewrite the visible copy without the blacklisted phrase.",
                ))

    banned_kicker = ["解读", "深度分析", "研判", "点评"]
    kicker = meta.get("kicker", "")
    for word in banned_kicker:
        if word in kicker:
            findings.append(warning(
                "W_KICKER_SUBJECTIVE",
                f'Kicker contains subjective wording “{word}”.',
                line=meta_lines.get("kicker"),
                actual=kicker,
                expected="Neutral source, event, or document wording",
                action="Replace it with a neutral label such as 报道、速览、数据整理 or 市场动态.",
            ))

    numbered_lines = []
    for line_number, line in enumerate(body.split("\n"), start=1):
        if re.match(r"^(?:一|二|三|四|五|六|七|八|九|十)[、，,.]", line.strip()):
            numbered_lines.append(absolute_line(line_number))
    if len(numbered_lines) >= 3:
        findings.append(warning(
            "W_STRUCTURE_NUMBERING",
            "Rigid Chinese numbering appears to be the article's main structure.",
            line=numbered_lines[0],
            actual=f"{len(numbered_lines)} numbered lines",
            expected="Question-led sections unless the content is genuinely procedural",
            action="Review the structure; keep numbering only when it clarifies real steps or sequence.",
        ))

    for section_number, section in enumerate(split_sections(body), start=1):
        count = count_numbers(section)
        if count > 10:
            findings.append(warning(
                "W_NUMBER_PILEUP",
                "A section contains an unusually large number of numeric tokens.",
                section=section_number,
                actual=count,
                expected="No unrelated numeric pile-up",
                action="Keep the numbers if they form a necessary comparison; otherwise retain only those that advance the argument.",
            ))

    for line_number, line in enumerate(body.split("\n"), start=1):
        if re.match(r"^#\s+", line):
            findings.append(warning(
                "W_BODY_H1",
                "The body contains an H1 heading even though the cover owns the article title.",
                line=absolute_line(line_number),
                actual=line.strip()[:80],
                expected="Body headings use H2–H6 or :::section",
                action="Demote or remove the body H1 unless the duplication is intentional.",
            ))

    ai_contrastive = re.compile(
        r"(?:不是|并非|不取决于|不在于|不会.*?而).*?(?:而是|而取决于|而在于|而会)"
    )
    for line_number, line in enumerate(body_no_code.split("\n"), start=1):
        stripped = line.strip()
        if stripped.startswith(":::") or stripped.startswith("|"):
            continue
        if ai_contrastive.search(stripped):
            findings.append(warning(
                "W_AI_CONTRASTIVE",
                "Copy contains a mechanically recognizable contrastive AI-style pattern.",
                line=absolute_line(line_number),
                actual=stripped[:80],
                expected="A direct causal or comparative statement without a formulaic 不是…而是 frame",
                action="Rewrite the sentence directly; keep it only when the contrast is genuinely necessary and natural.",
            ))

    risk_keywords = ["风险", "下跌", "暴跌", "亏损", "爆仓", "崩盘", "套牢", "追高"]
    body_outside_risk = strip_directives_content(body_no_code, "risk")
    for keyword in risk_keywords:
        for line_number, line in enumerate(body_outside_risk.split("\n"), start=1):
            if keyword in line and not line.strip().startswith(":::"):
                findings.append(warning(
                    "W_RISK_OUTSIDE_BLOCK",
                    f'Risk-related wording “{keyword}” appears outside :::risk.',
                    line=absolute_line(line_number),
                    actual=line.strip()[:80],
                    expected="Risk-related copy is reviewed and placed in :::risk",
                    action="Move it into :::risk when it is a negative fact, downside scenario, or risk conclusion; otherwise verify the context and accept the warning.",
                ))

    for line_number, line in enumerate(body_no_code.split("\n"), start=1):
        if "信源" in line:
            findings.append(warning(
                "W_BODY_SOURCE_WORD",
                'Rendered copy contains the internal word “信源”.',
                line=absolute_line(line_number),
                actual=line.strip()[:80],
                expected="Reader-facing source wording",
                action="Rewrite it as the specific institution, report, announcement, material, or source type.",
            ))

    contextless_source = re.compile(
        r"(?:对话|节目|访谈)(?:中|里|提到|指出|给出|拆出|援引|使用|用)"
        r"|(?:根据|按照|来自)(?:这场|本次|上述)?(?:对话|节目|访谈)"
    )
    for line_number, line in enumerate(body_no_code.split("\n"), start=1):
        stripped = line.strip()
        if stripped.startswith(":::"):
            continue
        if contextless_source.search(stripped):
            findings.append(warning(
                "W_CONTEXTLESS_INTERVIEW_REFERENCE",
                "Rendered copy refers to an interview or program without reader-facing context.",
                line=absolute_line(line_number),
                actual=stripped[:80],
                expected="Facts and analysis stated directly unless the named speaker or medium is essential",
                action="Remove the interview wrapper and integrate the supported fact or viewpoint into the article's own narrative.",
            ))

    source_block_re = re.compile(r"^:::source\s*$\n(.*?)\n^:::$", re.MULTILINE | re.DOTALL)
    for match in source_block_re.finditer(body):
        content = " ".join(match.group(1).split())
        if re.search(r"独家报道|信源|均来自|本文来自|整理自", content):
            line_number = body[:match.start()].count("\n") + 1
            findings.append(warning(
                "W_SOURCE_FILLER_ATTRIBUTION",
                ":::source repeats filler attribution already owned by the cover kicker.",
                line=absolute_line(line_number),
                actual=content[:80],
                expected=":::source only explains a body-specific statistical definition",
                action="Remove the block or replace it with the relevant measurement definition.",
            ))

    self_referential = re.compile(r"(?:没人|无人|不算|没有人)(?:叫|称|称作|称为|说).{1,6}的.{1,6}")
    lines = body.split("\n")
    for index, line in enumerate(lines):
        if line.strip() == ":::section" and index + 1 < len(lines):
            title_line = lines[index + 1].strip()
            if title_line and not title_line.startswith(":::") and self_referential.search(title_line):
                findings.append(warning(
                    "W_SECTION_SELF_REFERENCE",
                    "Section title uses a self-referential naming formula.",
                    line=absolute_line(index + 2),
                    actual=title_line[:80],
                    expected="A direct statement of the section's actual question or finding",
                    action="Replace the formula with the concrete subject, change, or consequence.",
                ))

    return findings


def main():
    parser = argparse.ArgumentParser(description="Mechanical style checks for carousel Markdown.")
    parser.add_argument("input", help="UTF-8 Markdown input")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    try:
        findings = lint(args.input)
    except Exception as error:
        failure = {
            "code": "E_LINT_INPUT",
            "severity": "error",
            "message": "The lint input could not be read or processed.",
            "actual": str(error),
            "action": "Confirm the path points to readable UTF-8 Markdown, then rerun lint.py.",
        }
        if args.json:
            print(json.dumps({"ok": False, "errors": [failure], "warnings": []}, ensure_ascii=False, indent=2))
        else:
            print(f"Error {failure['code']}: {failure['message']} {failure['actual']}")
        return 1

    errors = [item for item in findings if item["severity"] == "error"]
    warnings = [item for item in findings if item["severity"] == "warning"]
    if args.json:
        print(json.dumps({
            "ok": not errors,
            "errors": errors,
            "warnings": warnings,
            "count": len(findings),
        }, ensure_ascii=False, indent=2))
    elif findings:
        for item in findings:
            location = f" line {item['line']}" if item.get("line") else ""
            label = "Error" if item["severity"] == "error" else "Warning"
            print(f"  {label} {item['code']}{location}: {item['message']}")
        if warnings:
            print("\nReview each warning; warnings do not fail delivery by themselves.")
    else:
        print("No mechanical style warnings found.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
