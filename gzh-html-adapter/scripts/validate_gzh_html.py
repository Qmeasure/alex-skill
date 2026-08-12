#!/usr/bin/env python3
"""Validate a clean WeChat article fragment against this skill's rules."""

from __future__ import annotations

import argparse
import colorsys
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path


ALLOWED_TAGS = {
    "section",
    "p",
    "h2",
    "h3",
    "h4",
    "blockquote",
    "ul",
    "ol",
    "li",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "span",
    "strong",
    "em",
    "a",
    "br",
    "hr",
}

VOID_TAGS = {"br", "hr"}
STYLE_REQUIRED_TAGS = ALLOWED_TAGS - {"span", "br"}
TABLE_ATTRIBUTES = {"style", "colspan", "rowspan"}
ATTRIBUTE_ALLOWLIST = {
    "span": {"leaf", "style"},
    "a": {"href", "style"},
    "th": TABLE_ATTRIBUTES,
    "td": TABLE_ATTRIBUTES,
}

FORBIDDEN_TAGS = {
    "img",
    "picture",
    "source",
    "svg",
    "canvas",
    "video",
    "audio",
    "iframe",
    "object",
    "embed",
    "style",
    "script",
    "link",
    "div",
    "button",
    "form",
    "input",
}

FORBIDDEN_STYLE_PATTERNS = (
    (re.compile(r"url\s*\(", re.I), "CSS url()"),
    (re.compile(r"data\s*:", re.I), "data URI"),
    (re.compile(r"background-image\s*:", re.I), "background-image"),
    (re.compile(r"list-style-image\s*:", re.I), "list-style-image"),
    (re.compile(r"position\s*:\s*(?:absolute|fixed|sticky)", re.I), "禁用定位"),
    (re.compile(r"float\s*:", re.I), "float"),
    (re.compile(r"display\s*:\s*grid", re.I), "CSS Grid"),
    (re.compile(r"var\s*\(\s*--", re.I), "CSS 变量"),
    (re.compile(r"@(?:media|import|keyframes|supports)", re.I), "CSS @ 规则"),
    (re.compile(r"filter\s*:", re.I), "滤镜"),
)

FORBIDDEN_DOCUMENT_PATTERNS = (
    (re.compile(r"<!doctype", re.I), "正文不能包含 DOCTYPE"),
    (re.compile(r"<\s*/?\s*(?:html|head|body)\b", re.I), "正文不能包含文档外壳"),
    (re.compile(r"\b(?:src|srcset)\s*=", re.I), "正文不能包含媒体源属性"),
)

HTTP_LINK = re.compile(r"^https?://", re.I)

# 固定蓝白色板。详见 references/visual-system.md，改动必须同步那份文档。
PALETTE = frozenset(
    {
        "#1b3a6b",  # 深蓝
        "#2b6ef2",  # 主蓝
        "#6fa0e8",  # 中蓝
        "#f2f6fc",  # 浅蓝底
        "#d8e2f0",  # 边框蓝
        "#1a1a1a",  # 正文黑
        "#666666",  # 次要灰
        "#9a9a9a",  # 弱化灰
        "#c0392b",  # 警示红
        "#e0a458",  # 琥珀
        "#ffffff",  # 白
    }
)
DEEP_BLUE = "#1b3a6b"
BODY_BLACK = "#1a1a1a"
ALERT_RED = "#c0392b"
ROOT_BACKGROUND_TOKENS = {"#ffffff", "#f2f6fc"}
HEADING_COLOR_RULES = {"h2": DEEP_BLUE, "h3": DEEP_BLUE, "h4": BODY_BLACK}
BACKGROUND_PROPERTIES = {"background", "background-color"}
SHADOW_PROPERTIES = {"box-shadow", "text-shadow"}
COLOR_PROPERTIES = {
    "color",
    "border",
    "border-top",
    "border-right",
    "border-bottom",
    "border-left",
    "outline",
} | BACKGROUND_PROPERTIES | SHADOW_PROPERTIES
# 颜色属性里合法但不是颜色的取值。不在这里、也不是色板色值的写法一律报错，
# 这样 papayawhip 之类没被枚举的颜色名不会静默通过。
NON_COLOR_KEYWORDS = {
    "inherit",
    "currentcolor",
    "initial",
    "unset",
    "revert",
    "none",
    "transparent",
    "auto",
    "solid",
    "dashed",
    "dotted",
    "double",
    "groove",
    "ridge",
    "inset",
    "outset",
    "hidden",
    "thin",
    "medium",
    "thick",
    "repeat",
    "no-repeat",
    "center",
    "cover",
    "contain",
    "border-box",
    "padding-box",
    "content-box",
}
HEX_COLOR = re.compile(r"^#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$", re.I)
COLOR_FUNCTION = re.compile(r"^(rgba?|hsla?)\((.*)\)$", re.I)
COLOR_TOKEN = re.compile(
    r"#[0-9a-f]{3,8}\b|(?:rgba?|hsla?)\([^)]*\)",
    re.I,
)
GRADIENT_START = re.compile(
    r"^(?:repeating-)?(?:linear|radial|conic)-gradient\(",
    re.I,
)
GRADIENT_WORDS = {
    "at",
    "bottom",
    "ch",
    "circle",
    "cm",
    "closest-corner",
    "closest-side",
    "conic-gradient",
    "deg",
    "ellipse",
    "farthest-corner",
    "farthest-side",
    "from",
    "grad",
    "in",
    "left",
    "linear-gradient",
    "em",
    "ex",
    "rad",
    "radial-gradient",
    "rem",
    "repeating-conic-gradient",
    "repeating-linear-gradient",
    "repeating-radial-gradient",
    "right",
    "px",
    "mm",
    "pc",
    "pt",
    "to",
    "top",
    "turn",
    "vh",
    "vmax",
    "vmin",
    "vw",
}
# 色板只用十六进制和 rgb()/hsl() 表达，颜色名一律不接受。这里只保留
# transparent，供背景解析判断「没有实际底色」。
NAMED_COLORS = {
    "transparent": (255, 255, 255, 0),
}


def _parse_percentage_or_number(value: str, *, scale: float) -> float:
    value = value.strip()
    if value.endswith("%"):
        return float(value[:-1]) * scale / 100
    return float(value)


def _parse_alpha(value: str) -> float:
    alpha = _parse_percentage_or_number(value, scale=1)
    return min(1, max(0, alpha))


def _parse_color(value: str) -> tuple[float, float, float, float] | None:
    value = value.strip().lower()
    if value in NAMED_COLORS:
        red, green, blue, alpha = NAMED_COLORS[value]
        return red / 255, green / 255, blue / 255, float(alpha)

    hex_match = HEX_COLOR.fullmatch(value)
    if hex_match:
        digits = hex_match.group(1)
        if len(digits) in {3, 4}:
            digits = "".join(character * 2 for character in digits)
        alpha = int(digits[6:8], 16) / 255 if len(digits) == 8 else 1
        return (
            int(digits[0:2], 16) / 255,
            int(digits[2:4], 16) / 255,
            int(digits[4:6], 16) / 255,
            alpha,
        )

    function_match = COLOR_FUNCTION.fullmatch(value)
    if not function_match:
        return None

    name, body = function_match.groups()
    parts = [part for part in re.split(r"\s*[,/]\s*|\s+", body.strip()) if part]
    try:
        if name.startswith("rgb") and len(parts) in {3, 4}:
            channels = [
                _parse_percentage_or_number(part, scale=255) / 255
                for part in parts[:3]
            ]
            alpha = _parse_alpha(parts[3]) if len(parts) == 4 else 1
            if any(channel < 0 or channel > 1 for channel in channels):
                return None
            return channels[0], channels[1], channels[2], alpha

        if name.startswith("hsl") and len(parts) in {3, 4}:
            hue_text = parts[0].removesuffix("deg")
            hue = float(hue_text) % 360 / 360
            if not parts[1].endswith("%") or not parts[2].endswith("%"):
                return None
            saturation = float(parts[1][:-1]) / 100
            lightness = float(parts[2][:-1]) / 100
            if not 0 <= saturation <= 1 or not 0 <= lightness <= 1:
                return None
            red, green, blue = colorsys.hls_to_rgb(hue, lightness, saturation)
            alpha = _parse_alpha(parts[3]) if len(parts) == 4 else 1
            return red, green, blue, alpha
    except ValueError:
        return None
    return None


def _gradient_colors(value: str) -> list[tuple[float, float, float, float]] | None:
    if not GRADIENT_START.match(value.strip()) or not value.strip().endswith(")"):
        return None

    colors: list[tuple[float, float, float, float]] = []
    residue = COLOR_TOKEN.sub(" ", value.lower())
    for token in re.findall(r"[a-z][a-z-]*", residue):
        if token in GRADIENT_WORDS:
            continue
        color = _parse_color(token)
        if color is None:
            return None
        colors.append(color)

    for token in COLOR_TOKEN.findall(value):
        color = _parse_color(token)
        if color is None:
            return None
        colors.append(color)
    return colors or None


def _hex_from_color(color: tuple[float, float, float, float]) -> str | None:
    red, green, blue, alpha = color
    if alpha == 0:
        return "transparent"
    if alpha != 1:
        return None
    return "#%02x%02x%02x" % (round(red * 255), round(green * 255), round(blue * 255))


def _normalize_color(value: str) -> str | None:
    """把颜色写法归一成 #rrggbb 或 transparent，半透明返回 None。"""
    color = _parse_color(value)
    if color is None:
        return None
    return _hex_from_color(color)


def _bare_words(value: str) -> list[str]:
    """取出一条声明里不属于颜色函数、长度和渐变方位的裸词。"""
    residue = COLOR_TOKEN.sub(" ", value.lower())
    return [
        word
        for word in re.findall(r"[a-z][a-z-]*", residue)
        if word not in GRADIENT_WORDS
    ]


def _is_shadow_black(value: str) -> bool:
    color = _parse_color(value)
    if color is None:
        return False
    red, green, blue, _ = color
    return red == green == blue == 0


def _carries_color(property_name: str) -> bool:
    return (
        property_name in COLOR_PROPERTIES
        or property_name.endswith("-color")
        or property_name.startswith("background-")
    )


def _declarations(style: str) -> list[tuple[str, str]]:
    parsed: list[tuple[str, str]] = []
    for declaration in style.split(";"):
        declaration = declaration.strip()
        if not declaration or ":" not in declaration:
            continue
        property_name, value = (part.strip() for part in declaration.split(":", 1))
        parsed.append((property_name.lower(), value))
    return parsed


def _root_background_error(style: str | None) -> str | None:
    if not style:
        return "根 <section> 必须声明可解析的浅色背景"

    background: str | None = None
    background_color: str | None = None
    for declaration in style.split(";"):
        if ":" not in declaration:
            continue
        property_name, value = (part.strip() for part in declaration.split(":", 1))
        if property_name.lower() == "background":
            background = value
            background_color = None
        elif property_name.lower() == "background-color":
            background_color = value

    if not background and not background_color:
        return "根 <section> 必须声明可解析的浅色背景"

    colors: list[tuple[float, float, float, float]] | None = None
    if background:
        colors = _gradient_colors(background)

    if colors is not None and background_color:
        solid = _parse_color(background_color)
        if solid is None:
            return "根 <section> 的背景无法解析或不是明确颜色"
        colors.append(solid)
    elif colors is None:
        solid_value = background_color or background
        solid = _parse_color(solid_value or "")
        colors = [solid] if solid is not None else None

    if not colors or all(color[3] == 0 for color in colors):
        return "根 <section> 的背景无法解析或不是明确颜色"
    for color in colors:
        if _hex_from_color(color) not in ROOT_BACKGROUND_TOKENS:
            return "根 <section> 的背景只能使用 #FFFFFF 或 #F2F6FC，含二者构成的原生渐变"
    return None


@dataclass(frozen=True)
class ValidationResult:
    errors: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


class FragmentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.errors: list[str] = []
        self.stack: list[tuple[str, bool]] = []
        self.root_tags: list[str] = []
        self.root_style: str | None = None

    def handle_decl(self, decl: str) -> None:
        self.errors.append(f"正文不能包含声明：<!{decl}>")

    def handle_comment(self, data: str) -> None:
        return

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._handle_start(tag.lower(), attrs, closes_immediately=True)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._handle_start(tag.lower(), attrs, closes_immediately=tag.lower() in VOID_TAGS)

    def _handle_start(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
        *,
        closes_immediately: bool,
    ) -> None:
        if not self.stack:
            self.root_tags.append(tag)

        if tag == "h1":
            self.errors.append(
                "正文不能包含 <h1>：文章标题在公众号后台的标题栏单独填写，"
                "不写进正文。正文最高标题层级是 <h2>"
            )
        elif tag in FORBIDDEN_TAGS:
            self.errors.append(f"禁止标签：<{tag}>")
        elif tag not in ALLOWED_TAGS:
            self.errors.append(f"未允许的标签：<{tag}>")

        attr_map: dict[str, str] = {}
        allowed_attrs = ATTRIBUTE_ALLOWLIST.get(tag, {"style"})
        for raw_name, raw_value in attrs:
            name = raw_name.lower()
            value = raw_value or ""
            if name.startswith("on"):
                self.errors.append(f"<{tag}> 不能包含事件属性 {name}")
            elif name not in allowed_attrs:
                self.errors.append(f"<{tag}> 不能包含属性 {name}")
            attr_map[name] = value

        if tag in STYLE_REQUIRED_TAGS and not attr_map.get("style", "").strip():
            self.errors.append(f"<{tag}> 缺少非空内联 style")

        style = attr_map.get("style", "")
        if not self.stack and tag == "section":
            self.root_style = style
        if style:
            self._validate_style(tag, style)

        if tag == "span" and "leaf" in attr_map and attr_map["leaf"] != "":
            self.errors.append('<span leaf> 的 leaf 值必须为空字符串')

        if tag == "a":
            href = attr_map.get("href", "")
            if not HTTP_LINK.match(href):
                self.errors.append("<a> 的 href 必须是完整的 http:// 或 https:// 地址")

        is_leaf = tag == "span" and "leaf" in attr_map
        if not closes_immediately:
            self.stack.append((tag, is_leaf))

    def _validate_style(self, tag: str, style: str) -> None:
        for pattern, label in FORBIDDEN_STYLE_PATTERNS:
            if pattern.search(style):
                self.errors.append(f"<{tag}> 的 style 包含禁止项：{label}")

        declarations = _declarations(style)
        background_values: list[str] = []
        text_color: str | None = None

        for property_name, value in declarations:
            if property_name == "font-family":
                if value.strip().lower() != "inherit":
                    self.errors.append(f"<{tag}> 的 font-family 必须使用 inherit")
            if property_name in BACKGROUND_PROPERTIES:
                background_values.append(value)
            if property_name == "color":
                text_color = value
            self._validate_palette(tag, property_name, value)

        self._validate_color_roles(tag, background_values, text_color)

    def _validate_palette(self, tag: str, property_name: str, value: str) -> None:
        if not _carries_color(property_name):
            return

        is_shadow = property_name in SHADOW_PROPERTIES
        for token in COLOR_TOKEN.findall(value):
            if is_shadow and _is_shadow_black(token):
                continue
            normalized = _normalize_color(token)
            if is_shadow and normalized is None:
                # 阴影允许带透明度，只要底色在色板内。
                color = _parse_color(token)
                if color is not None:
                    normalized = _hex_from_color((*color[:3], 1.0))
            if normalized == "transparent":
                continue
            if normalized is None:
                self.errors.append(
                    f"<{tag}> 的 {property_name} 使用了无法解析或带透明度的颜色：{token}"
                )
            elif normalized not in PALETTE:
                self.errors.append(
                    f"<{tag}> 的 {property_name} 使用了色板外的颜色：{token}"
                )

        for word in _bare_words(value):
            if word not in NON_COLOR_KEYWORDS:
                self.errors.append(
                    f"<{tag}> 的 {property_name} 使用了颜色名或无法识别的取值：{word}。"
                    "颜色只能写成色板内的十六进制或 rgb()/hsl()"
                )

    def _validate_color_roles(
        self,
        tag: str,
        background_values: list[str],
        text_color: str | None,
    ) -> None:
        required = HEADING_COLOR_RULES.get(tag)
        if required is not None:
            declared = _normalize_color(text_color) if text_color else None
            if declared != required:
                self.errors.append(
                    f"<{tag}> 的 color 必须是 {required.upper()}，当前为 "
                    f"{text_color or '未声明'}"
                )

        opaque_backgrounds = [
            normalized
            for normalized in (
                _normalize_color(candidate) for candidate in background_values
            )
            if normalized not in (None, "transparent")
        ]
        gradient_backgrounds = [
            value for value in background_values if _gradient_colors(value) is not None
        ]

        if (opaque_backgrounds or gradient_backgrounds) and not text_color:
            self.errors.append(
                f"<{tag}> 声明了背景色却没有声明 color，深色模式下文字会失去对比"
            )

        if tag in {"th", "thead"} and ALERT_RED in opaque_backgrounds:
            self.errors.append(f"<{tag}> 的表头背景不能使用警示红 {ALERT_RED.upper()}")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in VOID_TAGS:
            return
        if not self.stack:
            self.errors.append(f"多余的结束标签：</{tag}>")
            return
        open_tag, _ = self.stack[-1]
        if open_tag != tag:
            self.errors.append(f"标签未正确闭合：<{open_tag}> 后遇到 </{tag}>")
            return
        self.stack.pop()

    def handle_data(self, data: str) -> None:
        if not data.strip():
            return
        if not self.stack:
            self.errors.append("根 <section> 外存在可见文字")
            return
        if not any(is_leaf for _, is_leaf in self.stack):
            parent = self.stack[-1][0]
            snippet = data.strip()[:24]
            self.errors.append(f"<{parent}> 中的文字未放入 <span leaf=\"\">：{snippet}")

    def finish(self) -> None:
        if self.stack:
            self.errors.append(f"存在未闭合标签：<{self.stack[-1][0]}>")
        if self.root_tags != ["section"]:
            self.errors.append("正文必须且只能有一个根 <section>")
        background_error = _root_background_error(self.root_style)
        if background_error:
            self.errors.append(background_error)


def validate_html(html: str) -> ValidationResult:
    errors: list[str] = []

    for pattern, message in FORBIDDEN_DOCUMENT_PATTERNS:
        if pattern.search(html):
            errors.append(message)

    parser = FragmentParser()
    try:
        parser.feed(html)
        parser.close()
        parser.finish()
    except Exception as exc:  # HTMLParser should not hide malformed input.
        errors.append(f"HTML 解析失败：{exc}")

    errors.extend(parser.errors)
    unique_errors = tuple(dict.fromkeys(errors))
    return ValidationResult(errors=unique_errors)


def main() -> int:
    parser = argparse.ArgumentParser(description="校验微信公众号正文 HTML")
    parser.add_argument("file", type=Path, help="公众号正文 HTML 文件")
    args = parser.parse_args()

    try:
        html = args.file.read_text(encoding="utf-8")
    except OSError as exc:
        parser.error(str(exc))

    result = validate_html(html)
    print(f"公众号正文校验：{args.file}")
    if result.ok:
        print("通过：正文结构、蓝白色板、标题用色、背景与文字配对和无图片规则均符合要求。")
        return 0

    print(f"发现 {len(result.errors)} 个问题：")
    for error in result.errors:
        print(f"- {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
