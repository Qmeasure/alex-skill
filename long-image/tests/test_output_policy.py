import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "render_mobile_share.py"
SPEC = importlib.util.spec_from_file_location("render_mobile_share", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def neutral_data():
    return {
        "output_policy": "single",
        "title": "HBM扩产图谱",
        "subtitle": "base die、IPO进度与产能预测",
        "meta": {"source": "公开资料", "date": "2026-07-13"},
        "sections": [
            {
                "title": "供给判断",
                "tag": "供给判断",
                "cards": [
                    {
                        "label": "产能口径",
                        "text": "只看DRAM投片会高估短期供给，这是运营口径判断。",
                    }
                ],
            }
        ],
    }


class OutputPolicyTests(unittest.TestCase):
    def test_brand_defaults_match_research_report_cta(self):
        brand_path = SCRIPT.parents[1] / "assets" / "brand.json"
        brand = json.loads(brand_path.read_text(encoding="utf-8"))
        self.assertEqual(brand["footer_title"], "完整研报加入智富界交流群")
        self.assertEqual(brand["qr_label"], "扫码加入研报交流")
        self.assertEqual(brand["footer_points"], [])
        background_path = SCRIPT.parents[1] / brand["footer_background"]
        self.assertTrue(background_path.is_file())
        png = background_path.read_bytes()
        self.assertEqual(struct.unpack(">II", png[16:24]), (1080, 400))

    def test_footer_uses_layered_background_and_fixed_height(self):
        html = MODULE.render_html(MODULE.single_variant(neutral_data()), "single")
        self.assertIn('class="footer-background"', html)
        self.assertIn("height:400px", html)
        self.assertIn("margin:70px -72px 0", html)
        self.assertIn("left:116px;top:114px;width:535px", html)
        self.assertIn("left:780px;top:55px;width:194px", html)
        self.assertIn("font-size:42px", html)
        self.assertIn('class="footer-intro-line"', html)
        self.assertNotIn("text-shadow", html)
        self.assertIn("完整研报加入智富界交流群", html)
        self.assertIn('<div class="header-qr-label">扫码加入研报交流</div>', html)
        self.assertIn('<div class="qr-label">扫码加入研报交流</div>', html)
        self.assertRegex(html, r'<img class="header-qr-image"[^>]+alt="扫码加入研报交流">')
        self.assertRegex(html, r'<img class="qr-image"[^>]+alt="扫码加入研报交流">')
        self.assertNotIn('class="bottom-safe-area"', html)
        self.assertNotIn("AI IP 与 AI 员工", html)

    def test_footer_intro_uses_exact_two_browser_lines(self):
        html = MODULE.render_html(MODULE.single_variant(neutral_data()), "single")
        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / "footer-lines.html"
            html_path.write_text(html, encoding="utf-8")
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                page = browser.new_page(viewport={"width": 1080, "height": 1920})
                page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
                result = page.locator(".footer-intro").evaluate(
                    """element => {
                        return {
                            lines: element.innerText.split('\\n'),
                            renderedLineCount: [...element.children].reduce((count, line) => {
                                const range = document.createRange();
                                range.selectNodeContents(line);
                                return count + [...range.getClientRects()].filter(rect => rect.width > 0.5).length;
                            }, 0),
                        };
                    }"""
                )
                browser.close()
        self.assertEqual(
            result["lines"],
            [
                "智富界是一个聚焦AI产业、创业与投资的研究平台，",
                "帮助企业及用户看懂AI、用好AI、投资AI。",
            ],
        )
        self.assertEqual(result["renderedLineCount"], 2)

    def test_footer_points_override_remains_compatible(self):
        data = neutral_data()
        data["share"] = {
            "override_brand": True,
            "footer_points": [{"label": "人", "text": "兼容说明"}],
        }
        html = MODULE.render_html(MODULE.single_variant(data), "single")
        self.assertIn("兼容说明", html)

    def test_brand_empty_points_suppress_unoverridden_input_points(self):
        data = neutral_data()
        data["share"] = {"footer_points": [{"label": "旧", "text": "不应出现"}]}
        html = MODULE.render_html(MODULE.single_variant(data), "single")
        self.assertNotIn("不应出现", html)

    def test_render_png_crops_to_page_height(self):
        html = MODULE.render_html(MODULE.single_variant(neutral_data()), "single")
        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / "short.html"
            png_path = Path(temp_dir) / "short.png"
            html_path.write_text(html, encoding="utf-8")
            MODULE.render_png(html_path, png_path)
            png = png_path.read_bytes()
            width, height = struct.unpack(">II", png[16:24])
        self.assertEqual(width, 1080)
        self.assertLess(height, 1920)
        self.assertGreaterEqual(height, 470)

    def test_single_allows_neutral_industry_language(self):
        variant = MODULE.single_variant(neutral_data())
        html = MODULE.render_html(variant, "single")
        self.assertNotIn("内部研究版", html)

    def test_single_rejects_explicit_investment_advice(self):
        data = neutral_data()
        data["sections"][0]["cards"][0]["text"] = "评级买入，目标价100元。"
        with self.assertRaisesRegex(ValueError, "output_policy: dual"):
            MODULE.single_variant(data)

    def test_dual_labels_internal_and_filters_external(self):
        data = {
            "output_policy": "dual",
            "title": "标的研究",
            "external_title": "公司业务图谱",
            "meta": {"date": "2026-07-13"},
            "sections": [
                {
                    "title": "业务与判断",
                    "tag": "业务判断",
                    "audience": "both",
                    "cards": [
                        {"label": "业务事实", "text": "产品已经量产。", "audience": "both"},
                        {"label": "内部评级", "text": "买入，目标价100元。", "audience": "internal"},
                    ],
                }
            ],
        }
        internal_html = MODULE.render_html(MODULE.internal_variant(data), "internal")
        external_html = MODULE.render_html(MODULE.external_variant(data), "external")
        self.assertIn("内部研究版", internal_html)
        self.assertNotIn("内部研究版", external_html)
        self.assertNotIn("目标价100元", external_html)


    def test_preview_strip_renders_when_uris_present(self):
        data = neutral_data()
        data["_preview_uris"] = ["data:image/png;base64,iVBOR"]
        data["_preview_total_pages"] = 42
        html = MODULE.render_html(MODULE.single_variant(data), "single")
        self.assertIn('<section class="preview-strip">', html)
        self.assertIn("完整研报预览", html)
        self.assertIn("42", html)
        self.assertIn('<div class="preview-page">', html)

    def test_preview_strip_absent_without_uris(self):
        html = MODULE.render_html(MODULE.single_variant(neutral_data()), "single")
        self.assertNotIn('<section class="preview-strip">', html)
        self.assertNotIn('<div class="preview-page">', html)


if __name__ == "__main__":
    unittest.main()
