#!/usr/bin/env python3
"""Post-render verification for long-image outputs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

EXPECTED_WIDTH = 1080

SENSITIVE_RE = re.compile(
    r"评级|买入|卖出|持有|增持|减持|推荐|推票|建仓|加仓|减仓|仓位|止损|止盈|交易指令|投资建议|"
    r"目标价|目标市值|发行价|隐含价|隐含市值|"
    r"(?<![A-Za-z])IPO(?![A-Za-z])|"
    r"安全边际|上行空间|下行空间|买点|卖点|"
    r"(?:价值|股价|估值|市值|标的).{0,8}(?:低估|高估)|(?:低估|高估).{0,8}(?:价值|股价|估值|市值|标的)|"
    r"(?:给予|对应|合理).{0,6}(?:估值|PE|P/E)|"
    r"(?:Bull|Base|Bear)\s*(?:case|情景)|概率加权|"
    r"盈利预测|营收预测|利润预测|EPS\s*预测|"
    r"预计.{0,6}(?:营收|收入|利润|出货)|预测.{0,6}(?:营收|收入|利润|出货)|"
    r"20\d{2}[EF]",
    flags=re.IGNORECASE,
)

AUDIENCE_LABEL_RE = re.compile(
    r"内部研究版|内部版|外部版|外部公开版|Internal\s*(?:Only|Version)|External\s*(?:Only|Version)",
    flags=re.IGNORECASE,
)

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"


def tag_pass(label: str) -> None:
    print(f"  {GREEN}✓{RESET} {label}")


def tag_fail(label: str, detail: str = "") -> None:
    msg = f"  {RED}✗{RESET} {label}"
    if detail:
        msg += f"  {YELLOW}→ {detail}{RESET}"
    print(msg)


class TextExtractor(HTMLParser):
    """Extract visible text from HTML, skipping <style> and <script>."""

    def __init__(self) -> None:
        super().__init__()
        self._pieces: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("style", "script"):
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script"):
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._pieces.append(data)

    def get_text(self) -> str:
        return " ".join(self._pieces)


def extract_text(html_content: str) -> str:
    parser = TextExtractor()
    parser.feed(html_content)
    return parser.get_text()


class QRExtractor(HTMLParser):
    """Extract all img src values that look like QR codes."""

    def __init__(self) -> None:
        super().__init__()
        self.qr_sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "img":
            return
        attr_dict = dict(attrs)
        cls = attr_dict.get("class", "")
        src = attr_dict.get("src", "")
        # Only match class names for QR detection; skip src content for data URIs
        # to avoid false positives from base64-encoded thumbnails that randomly
        # contain the substring "qr".
        src_has_qr = not src.startswith("data:") and "qr" in src.lower()
        if src and ("qr" in cls.lower() or src_has_qr):
            self.qr_sources.append(src)


def extract_qr_sources(html_content: str) -> list[str]:
    parser = QRExtractor()
    parser.feed(html_content)
    return parser.qr_sources


def check_png_dimensions(png_path: Path) -> bool:
    try:
        from PIL import Image
    except ImportError:
        tag_fail(f"{png_path.name} 尺寸", "Pillow 不可用，跳过图片检查")
        return False

    img = Image.open(png_path)
    w, h = img.size
    ok = True

    if w == EXPECTED_WIDTH:
        tag_pass(f"{png_path.name} 宽度 {w}px")
    else:
        tag_fail(f"{png_path.name} 宽度 {w}px", f"期望 {EXPECTED_WIDTH}px")
        ok = False

    if h > w:
        tag_pass(f"{png_path.name} 高度 {h}px（竖向长图）")
    else:
        tag_fail(f"{png_path.name} 高度 {h}px", "高度应大于宽度")
        ok = False

    return ok


def check_sensitive_content(html_path: Path) -> bool:
    text = extract_text(html_path.read_text(encoding="utf-8"))
    matches = list(SENSITIVE_RE.finditer(text))
    if not matches:
        tag_pass(f"{html_path.name} 敏感词扫描通过")
        return True
    unique = sorted(set(m.group() for m in matches))
    tag_fail(f"{html_path.name} 发现敏感词", "、".join(unique[:8]))
    return False


def check_audience_labels(html_path: Path, mode: str) -> bool:
    text = extract_text(html_path.read_text(encoding="utf-8"))
    found = AUDIENCE_LABEL_RE.findall(text)

    if mode == "internal":
        if "内部研究版" in text:
            tag_pass(f"{html_path.name} 包含「内部研究版」标签")
            return True
        tag_fail(f"{html_path.name} 缺少「内部研究版」标签")
        return False

    if mode == "external":
        if not found:
            tag_pass(f"{html_path.name} 无受众标签")
            return True
        tag_fail(f"{html_path.name} 包含受众标签", "、".join(found[:4]))
        return False

    if mode == "single":
        if not found:
            tag_pass(f"{html_path.name} 无受众标签")
            return True
        tag_fail(f"{html_path.name} 包含受众标签", "、".join(found[:4]))
        return False

    return True


def check_qr_consistency(html_path: Path) -> bool:
    sources = extract_qr_sources(html_path.read_text(encoding="utf-8"))
    if len(sources) < 2:
        tag_fail(f"{html_path.name} 二维码数量 ({len(sources)})", "期望顶部和底部各一个")
        return False
    unique = set(sources)
    if len(unique) == 1:
        tag_pass(f"{html_path.name} 顶部/底部二维码一致")
        return True
    tag_fail(f"{html_path.name} 顶部/底部二维码不一致", f"发现 {len(unique)} 个不同来源")
    return False


def check_file_count(output_dir: Path, stem: str, policy: str) -> tuple[bool, list[Path], list[Path]]:
    ok = True
    pngs: list[Path] = []
    htmls: list[Path] = []

    if policy == "single":
        expected_pngs = [output_dir / f"{stem}.png"]
        expected_htmls = [output_dir / f"{stem}.html"]
        unexpected = [
            output_dir / f"{stem}-internal.png",
            output_dir / f"{stem}-external.png",
        ]
    else:
        expected_pngs = [
            output_dir / f"{stem}-internal.png",
            output_dir / f"{stem}-external.png",
        ]
        expected_htmls = [
            output_dir / f"{stem}-internal.html",
            output_dir / f"{stem}-external.html",
        ]
        unexpected = [output_dir / f"{stem}.png"]

    for p in expected_pngs:
        if p.exists():
            tag_pass(f"{p.name} 存在")
            pngs.append(p)
        else:
            tag_fail(f"{p.name}", "期望的输出文件未找到")
            ok = False

    for h in expected_htmls:
        if h.exists():
            tag_pass(f"{h.name} 存在")
            htmls.append(h)
        else:
            tag_fail(f"{h.name}", "期望的输出文件未找到")
            ok = False

    for u in unexpected:
        if u.exists():
            tag_fail(f"{u.name} 不应存在", f"{policy} 模式不应生成此文件")
            ok = False

    return ok, pngs, htmls


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify rendered long-image outputs.")
    parser.add_argument("input", help="Input JSON file (same as passed to render).")
    parser.add_argument("--output-dir", help="Output directory. Defaults to the input directory.")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"{RED}输入文件不存在: {input_path}{RESET}")
        return 1

    data = json.loads(input_path.read_text(encoding="utf-8"))
    policy = data.get("output_policy")
    if policy not in ("single", "dual"):
        print(f"{RED}输入 JSON 缺少有效的 output_policy（single/dual）{RESET}")
        return 1

    output_dir = Path(args.output_dir) if args.output_dir else input_path.parent
    stem = input_path.stem
    errors = 0

    print(f"\n{BOLD}long-image 输出验收{RESET}")
    print(f"  模式: {policy}  输入: {input_path.name}\n")

    # --- 文件检查 ---
    print(f"{BOLD}[输出文件]{RESET}")
    file_ok, pngs, htmls = check_file_count(output_dir, stem, policy)
    if not file_ok:
        errors += 1

    # --- 图片尺寸 ---
    if pngs:
        print(f"\n{BOLD}[图片尺寸]{RESET}")
        for p in pngs:
            if not check_png_dimensions(p):
                errors += 1

    # --- 受众标签 ---
    if htmls:
        print(f"\n{BOLD}[受众标签]{RESET}")
        if policy == "single":
            for h in htmls:
                if not check_audience_labels(h, "single"):
                    errors += 1
        else:
            for h in htmls:
                mode = "internal" if "-internal" in h.stem else "external"
                if not check_audience_labels(h, mode):
                    errors += 1

    # --- External 敏感词 ---
    external_htmls = [h for h in htmls if "-external" in h.stem]
    if external_htmls:
        print(f"\n{BOLD}[External 敏感词扫描]{RESET}")
        for h in external_htmls:
            if not check_sensitive_content(h):
                errors += 1

    # --- 二维码一致性 ---
    if htmls:
        print(f"\n{BOLD}[二维码]{RESET}")
        for h in htmls:
            if not check_qr_consistency(h):
                errors += 1

    # --- 汇总 ---
    print()
    if errors == 0:
        print(f"{GREEN}{BOLD}全部通过。仍建议目视确认排版与可读性。{RESET}\n")
        return 0
    else:
        print(f"{RED}{BOLD}{errors} 项未通过，请检查后再交付。{RESET}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
