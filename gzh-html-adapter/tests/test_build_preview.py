from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from build_preview import build_preview, default_output_path  # noqa: E402


BODY = (
    '<section style="max-width:100%;box-sizing:border-box;background:#FFFFFF;'
    'color:#1A1A1A;'
    'font-family:inherit;">'
    '<p style="margin:0;font-size:16px;line-height:1.75;color:#1A1A1A;">'
    '<span leaf="">正文</span></p></section>'
)


class BuildPreviewTests(unittest.TestCase):
    def test_shipped_sample_preview_matches_sample_body(self) -> None:
        body = SKILL_ROOT / "assets" / "sample-body.html"
        shipped = SKILL_ROOT / "assets" / "sample-preview.html"
        self.assertTrue(shipped.is_file(), "assets/sample-preview.html 缺失")

        with tempfile.TemporaryDirectory() as temp_dir:
            rebuilt = build_preview(body, Path(temp_dir) / "sample-preview.html")
            self.assertEqual(
                shipped.read_text(encoding="utf-8"),
                rebuilt.read_text(encoding="utf-8"),
                "样张预览页已过期，请重新运行 build_preview.py 生成 assets/sample-preview.html",
            )

    def test_default_output_name(self) -> None:
        source = Path("/tmp/文章_公众号正文.html")
        self.assertEqual(
            default_output_path(source),
            Path("/tmp/文章_公众号预览.html"),
        )

    def test_builds_preview_and_keeps_controls_outside_copy_region(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "文章_公众号正文.html"
            source.write_text(BODY, encoding="utf-8")

            output = build_preview(source)
            preview = output.read_text(encoding="utf-8")

            self.assertEqual(output.name, "文章_公众号预览.html")
            self.assertEqual(preview.count(BODY), 1)
            self.assertIn('id="gzh-content"', preview)
            self.assertIn('id="copy-button"', preview)
            self.assertIn('range.selectNodeContents(content)', preview)

            button_position = preview.index('id="copy-button"')
            content_position = preview.index('id="gzh-content"')
            self.assertLess(button_position, content_position)

            copied_region = preview[content_position : preview.index("</main>")]
            self.assertNotIn("<button", copied_region)
            self.assertNotIn("<script", copied_region)

    def test_rejects_empty_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "空_公众号正文.html"
            source.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "正文文件为空"):
                build_preview(source)

    def test_rejects_unvalidated_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "非法_公众号正文.html"
            source.write_text(
                '<section style="color:inherit;"><img src="chart.png"></section>',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "正文校验未通过"):
                build_preview(source)


if __name__ == "__main__":
    unittest.main()
