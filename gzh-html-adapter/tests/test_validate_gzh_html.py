from __future__ import annotations

import sys
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from validate_gzh_html import validate_html  # noqa: E402


ROOT_STYLE = (
    "max-width:100%;box-sizing:border-box;background:#FFFFFF;"
    "color:#1A1A1A;font-family:inherit;"
)
BLOCK_STYLE = (
    "margin:1.2em 0;padding:.9em;color:#1A1A1A;background:#FFFFFF;"
    "border:1px solid #D8E2F0;box-sizing:border-box;"
)
TEXT_STYLE = "margin:0;font-size:16px;line-height:1.75;color:#1A1A1A;"
CAPTION_STYLE = "margin:0;font-size:13px;line-height:1.6;color:#666666;"
TABLE_STYLE = (
    "width:100%;border-collapse:collapse;table-layout:fixed;"
    "font-size:14px;color:#1A1A1A;"
)
CELL_STYLE = (
    "padding:.55em .5em;border:1px solid #D8E2F0;vertical-align:top;"
    "color:#1A1A1A;background:#FFFFFF;"
)
ROW_STYLE = "color:#1A1A1A;"
TRACK_STYLE = (
    "width:100%;height:14px;background:#F2F6FC;box-sizing:border-box;color:#1A1A1A;"
)


def leaf(text: str) -> str:
    return f'<span leaf="">{text}</span>'


def table(rows: list[tuple[str, str]]) -> str:
    body = "".join(
        f'<tr style="{ROW_STYLE}">'
        f'<td style="{CELL_STYLE}">{leaf(label)}</td>'
        f'<td style="{CELL_STYLE}">{leaf(value)}</td>'
        "</tr>"
        for label, value in rows
    )
    return (
        f'<table style="{TABLE_STYLE}">'
        f'<tbody style="{ROW_STYLE}">{body}</tbody>'
        "</table>"
    )


def fill(width: str, color: str) -> str:
    return (
        f'<section style="width:{width};height:14px;background:{color};'
        f'color:#FFFFFF;box-sizing:border-box;">{leaf(" ")}</section>'
    )


def compliant_fragment() -> str:
    headings = (
        '<h2 style="margin:1.6em 0 .6em;padding-left:10px;'
        'border-left:4px solid #2B6EF2;font-size:19px;line-height:1.4;'
        f'font-weight:700;color:#1B3A6B;">{leaf("一级小标题")}</h2>'
        '<h3 style="margin:1.4em 0 .5em;font-size:17px;line-height:1.5;'
        f'font-weight:700;color:#1B3A6B;">{leaf("二级小标题")}</h3>'
        '<h4 style="margin:1.2em 0 .4em;font-size:16px;line-height:1.6;'
        f'font-weight:700;color:#1A1A1A;">{leaf("三级小标题")}</h4>'
    )
    quote = (
        '<blockquote style="margin:1.2em 0;padding:.8em 1em;background:#F2F6FC;'
        'color:#1A1A1A;border-left:3px solid #6FA0E8;font-size:15px;'
        'line-height:1.7;box-sizing:border-box;">'
        f'<p style="{TEXT_STYLE}">{leaf("引文")}</p></blockquote>'
    )
    lists = (
        '<ul style="margin:0 0 1em;padding-left:1.4em;color:#1A1A1A;">'
        f'<li style="{TEXT_STYLE}">{leaf("条目")}</li></ul>'
        '<ol style="margin:0 0 1em;padding-left:1.4em;color:#1A1A1A;">'
        f'<li style="{TEXT_STYLE}">{leaf("条目")}</li></ol>'
    )
    rule = '<hr style="border:none;border-top:1px solid #D8E2F0;margin:1.6em 0;" />'
    kpi = (
        f'<section style="{BLOCK_STYLE}">'
        f'<p style="{TEXT_STYLE}">{leaf("关键指标")}</p>'
        f'{table([("指标", "数值")])}'
        "</section>"
    )
    data_table = (
        f'<section style="{BLOCK_STYLE}">'
        f'<p style="{TEXT_STYLE}">{leaf("数据表")}</p>'
        f'{table([("类别", "数值")])}'
        "</section>"
    )
    horizontal_bar = (
        f'<section style="{BLOCK_STYLE}">'
        f'<p style="{TEXT_STYLE}">{leaf("横向条形图")}</p>'
        f'<section style="{TRACK_STYLE}">{fill("64%", "#2B6EF2")}</section>'
        f'<p style="{TEXT_STYLE}">{leaf("类别：数值")}</p>'
        "</section>"
    )
    negative_bar = (
        f'<section style="{BLOCK_STYLE}">'
        f'<p style="{TEXT_STYLE}">'
        f'{leaf("乙公司　")}'
        f'<span leaf="" style="color:#C0392B;">下降 14.2</span></p>'
        f'<section style="{TRACK_STYLE}">{fill("86%", "#C0392B")}</section>'
        "</section>"
    )
    stacked_bar = (
        f'<section style="{BLOCK_STYLE}">'
        f'<p style="{TEXT_STYLE}">{leaf("堆叠条形图")}</p>'
        f'<section style="width:100%;font-size:0;color:#1A1A1A;">'
        f'<span style="display:inline-block;width:40%;height:14px;'
        f'background:#2B6EF2;color:#FFFFFF;"></span>'
        f'<span style="display:inline-block;width:60%;height:14px;'
        f'background:#6FA0E8;color:#FFFFFF;"></span>'
        "</section>"
        f'<p style="{TEXT_STYLE}">{leaf("分项及数值")}</p>'
        "</section>"
    )
    progress = (
        f'<section style="{BLOCK_STYLE}">'
        f'<p style="{TEXT_STYLE}">{leaf("进度图：实际值与目标值")}</p>'
        f'<section style="{TRACK_STYLE}border:1px solid #D8E2F0;">'
        f'{fill("75.5%", "#2B6EF2")}</section>'
        "</section>"
    )
    timeline = (
        f'<section style="{BLOCK_STYLE}">'
        f'<p style="{TEXT_STYLE}">{leaf("时间线")}</p>'
        f'{table([("日期", "事件")])}'
        "</section>"
    )
    link = (
        f'<p style="{TEXT_STYLE}">'
        f'<a href="https://example.com/source" '
        f'style="color:#2B6EF2;text-decoration:underline;word-break:break-all;">'
        f'{leaf("来源")}</a></p>'
        f'<p style="{CAPTION_STYLE}">{leaf("数据来源：原文第三节。")}</p>'
    )
    return (
        f'<section style="{ROOT_STYLE}">'
        f"{headings}{quote}{lists}{rule}{kpi}{data_table}{horizontal_bar}"
        f"{negative_bar}{stacked_bar}{progress}{timeline}{link}"
        "</section>"
    )


class ValidateWechatHtmlTests(unittest.TestCase):
    def test_accepts_all_supported_native_chart_structures(self) -> None:
        result = validate_html(compliant_fragment())
        self.assertTrue(result.ok, result.errors)

    def test_accepts_shipped_sample_body(self) -> None:
        sample = SKILL_ROOT / "assets" / "sample-body.html"
        result = validate_html(sample.read_text(encoding="utf-8"))
        self.assertTrue(result.ok, result.errors)

    def test_rejects_all_image_and_active_content_paths(self) -> None:
        forbidden = {
            "img": '<img src="chart.png">',
            "picture": "<picture></picture>",
            "svg": "<svg></svg>",
            "canvas": "<canvas></canvas>",
            "script": "<script></script>",
            "style": "<style></style>",
            "external-style": '<link rel="stylesheet" href="theme.css">',
            "button": "<button>复制</button>",
            "css-url": '<section style="background:url(chart.png);"></section>',
            "background-image": (
                '<section style="background-image:linear-gradient(#FFFFFF,#F2F6FC);">'
                "</section>"
            ),
            "data-uri": (
                '<section style="background-image:url(data:image/png;base64,AA);">'
                "</section>"
            ),
            "forbidden-position": (
                '<section style="position:absolute;color:#1A1A1A;"></section>'
            ),
        }
        for name, payload in forbidden.items():
            with self.subTest(name=name):
                html = (
                    f'<section style="{ROOT_STYLE}">'
                    f'<section style="{BLOCK_STYLE}">{payload}</section>'
                    "</section>"
                )
                self.assertFalse(validate_html(html).ok)

    def test_rejects_missing_inline_style(self) -> None:
        html = f'<section style="{ROOT_STYLE}"><p>{leaf("正文")}</p></section>'
        self.assertFalse(validate_html(html).ok)

    def test_rejects_unwrapped_text(self) -> None:
        html = f'<section style="{ROOT_STYLE}"><p style="{TEXT_STYLE}">正文</p></section>'
        self.assertFalse(validate_html(html).ok)

    def test_rejects_colors_outside_the_palette(self) -> None:
        offenders = (
            "color:#2f6f8f;",
            "background:#f7f8fb;color:#1A1A1A;",
            "border:1px solid #c7d4e3;color:#1A1A1A;",
            "color:rgb(47,111,143);",
            "color:teal;",
        )
        for style in offenders:
            with self.subTest(style=style):
                html = (
                    f'<section style="{ROOT_STYLE}">'
                    f'<p style="margin:0;{style}">{leaf("正文")}</p>'
                    "</section>"
                )
                self.assertFalse(validate_html(html).ok)

    def test_rejects_h1_because_the_title_belongs_in_the_backend_field(self) -> None:
        html = (
            f'<section style="{ROOT_STYLE}">'
            '<h1 style="margin:0;font-size:22px;font-weight:700;color:#1B3A6B;">'
            f'{leaf("文章标题")}</h1>'
            "</section>"
        )
        result = validate_html(html)
        self.assertFalse(result.ok)
        self.assertTrue(
            any("h1" in error for error in result.errors), result.errors
        )

    def test_rejects_any_css_color_name(self) -> None:
        names = ("white", "teal", "whitesmoke", "papayawhip", "rebeccapurple")
        for name in names:
            with self.subTest(name=name):
                html = (
                    f'<section style="{ROOT_STYLE}">'
                    f'<p style="margin:0;color:{name};">{leaf("正文")}</p>'
                    "</section>"
                )
                self.assertFalse(validate_html(html).ok)

    def test_ignores_keywords_in_properties_that_carry_no_color(self) -> None:
        html = (
            f'<section style="{ROOT_STYLE}">'
            f'<p style="margin:0;color:#1A1A1A;font-weight:bold;'
            f'text-decoration:underline;text-align:justify;">{leaf("正文")}</p>'
            "</section>"
        )
        result = validate_html(html)
        self.assertTrue(result.ok, result.errors)

    def test_accepts_palette_colors_written_in_any_notation(self) -> None:
        equivalents = ("#1A1A1A", "#1a1a1a", "rgb(26,26,26)")
        for value in equivalents:
            with self.subTest(value=value):
                html = (
                    f'<section style="{ROOT_STYLE}">'
                    f'<p style="margin:0;color:{value};">{leaf("正文")}</p>'
                    "</section>"
                )
                result = validate_html(html)
                self.assertTrue(result.ok, result.errors)

    def test_rejects_semi_transparent_colors_outside_shadows(self) -> None:
        html = (
            f'<section style="{ROOT_STYLE}">'
            f'<p style="margin:0;color:rgba(43,110,242,.5);">{leaf("正文")}</p>'
            "</section>"
        )
        self.assertFalse(validate_html(html).ok)

    def test_accepts_translucent_black_shadow(self) -> None:
        html = (
            f'<section style="{ROOT_STYLE}">'
            f'<section style="{BLOCK_STYLE}box-shadow:0 2px 8px rgba(0,0,0,.15);">'
            f'{leaf("分组块")}</section>'
            "</section>"
        )
        result = validate_html(html)
        self.assertTrue(result.ok, result.errors)

    def test_enforces_heading_colors(self) -> None:
        wrong = {
            "h2": 'color:#2B6EF2;',
            "h3": 'color:#1A1A1A;',
            "h4": 'color:#1B3A6B;',
            "h2-missing": "font-weight:700;",
        }
        for name, style in wrong.items():
            tag = name.split("-")[0]
            with self.subTest(name=name):
                html = (
                    f'<section style="{ROOT_STYLE}">'
                    f'<{tag} style="margin:0;{style}">{leaf("标题")}</{tag}>'
                    "</section>"
                )
                self.assertFalse(validate_html(html).ok)

    def test_accepts_specified_heading_colors(self) -> None:
        correct = {"h2": "#1B3A6B", "h3": "#1B3A6B", "h4": "#1A1A1A"}
        for tag, color in correct.items():
            with self.subTest(tag=tag):
                html = (
                    f'<section style="{ROOT_STYLE}">'
                    f'<{tag} style="margin:0;font-weight:700;color:{color};">'
                    f'{leaf("标题")}</{tag}>'
                    "</section>"
                )
                result = validate_html(html)
                self.assertTrue(result.ok, result.errors)

    def test_rejects_background_without_color(self) -> None:
        payloads = (
            '<p style="margin:0;background:#F2F6FC;">',
            '<p style="margin:0;background-color:#F2F6FC;">',
            '<p style="margin:0;background:linear-gradient(90deg,#FFFFFF,#F2F6FC);">',
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                html = (
                    f'<section style="{ROOT_STYLE}">'
                    f'{payload}{leaf("正文")}</p>'
                    "</section>"
                )
                self.assertFalse(validate_html(html).ok)

    def test_rejects_alert_red_as_table_header_background(self) -> None:
        html = (
            f'<section style="{ROOT_STYLE}">'
            f'<table style="{TABLE_STYLE}"><thead style="color:#FFFFFF;">'
            f'<tr style="color:#FFFFFF;">'
            f'<th style="background:#C0392B;color:#FFFFFF;padding:.6em .5em;">'
            f'{leaf("表头")}</th>'
            "</tr></thead></table></section>"
        )
        self.assertFalse(validate_html(html).ok)

    def test_accepts_deep_blue_block_and_allowed_root_gradients(self) -> None:
        html = (
            '<section style="max-width:100%;box-sizing:border-box;'
            'background:linear-gradient(135deg,#FFFFFF 0%,#F2F6FC 100%);'
            'font-family:inherit;color:#1A1A1A;">'
            '<section style="margin:1em 0;padding:1em;background:#1B3A6B;'
            'color:#FFFFFF;border:1px solid #D8E2F0;'
            'box-shadow:0 2px 8px rgba(0,0,0,.15);">'
            f'{leaf("局部深色强调")}</section></section>'
        )
        result = validate_html(html)
        self.assertTrue(result.ok, result.errors)

    def test_accepts_allowed_root_backgrounds(self) -> None:
        backgrounds = (
            "#FFFFFF",
            "#ffffff",
            "rgb(255,255,255)",
            "linear-gradient(135deg,#FFFFFF 0%,#F2F6FC 100%)",
            "radial-gradient(circle at top,#FFFFFF,#F2F6FC)",
        )
        for background in backgrounds:
            with self.subTest(background=background):
                html = (
                    '<section style="max-width:100%;box-sizing:border-box;'
                    f'background:{background};color:#1A1A1A;'
                    'font-family:inherit;"></section>'
                )
                result = validate_html(html)
                self.assertTrue(result.ok, result.errors)

    def test_accepts_white_background_color_declaration(self) -> None:
        html = (
            '<section style="max-width:100%;background-color:#FFFFFF;'
            'color:#1A1A1A;font-family:inherit;"></section>'
        )
        result = validate_html(html)
        self.assertTrue(result.ok, result.errors)

    def test_rejects_missing_dark_and_off_token_root_backgrounds(self) -> None:
        styles = (
            "max-width:100%;box-sizing:border-box;color:#1A1A1A;font-family:inherit",
            "max-width:100%;background:#111827;color:#FFFFFF;font-family:inherit",
            (
                "max-width:100%;background:#f7f8fb;color:#1A1A1A;"
                "font-family:inherit"
            ),
            (
                "max-width:100%;background:linear-gradient(90deg,#FFFFFF,#334155);"
                "color:#1A1A1A;font-family:inherit"
            ),
            (
                "max-width:100%;background:linear-gradient(90deg,#FFFFFF,#F2F6FC);"
                "background-color:#F7F8FB;color:#1A1A1A;font-family:inherit"
            ),
            (
                "max-width:100%;background:color-mix(in srgb,white 80%,blue);"
                "color:#1A1A1A;font-family:inherit"
            ),
        )
        for style in styles:
            with self.subTest(style=style):
                self.assertFalse(validate_html(f'<section style="{style}"></section>').ok)

    def test_rejects_non_inherited_font_family(self) -> None:
        html = (
            f'<section style="{ROOT_STYLE}">'
            f'<p style="{TEXT_STYLE}font-family:Arial;">{leaf("正文")}</p>'
            "</section>"
        )
        self.assertFalse(validate_html(html).ok)

    def test_rejects_document_shell_and_multiple_roots(self) -> None:
        document = (
            "<!DOCTYPE html><html><body>"
            f'<section style="{ROOT_STYLE}"></section>'
            "</body></html>"
        )
        self.assertFalse(validate_html(document).ok)

        multiple = (
            f'<section style="{ROOT_STYLE}"></section>'
            f'<section style="{ROOT_STYLE}"></section>'
        )
        self.assertFalse(validate_html(multiple).ok)

    def test_rejects_relative_or_active_links(self) -> None:
        for href in ("/relative", "#anchor", "javascript:alert(1)", "data:text/plain,x"):
            with self.subTest(href=href):
                html = (
                    f'<section style="{ROOT_STYLE}">'
                    f'<a href="{href}" style="color:inherit;">{leaf("链接")}</a>'
                    "</section>"
                )
                self.assertFalse(validate_html(html).ok)


if __name__ == "__main__":
    unittest.main()
