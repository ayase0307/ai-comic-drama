import unittest

from scripts.storyboard import export_asset_prompts as ex


class CharacterPromptTests(unittest.TestCase):
    def test_default_uses_master_composition_and_3d_style(self):
        p = ex.compile_full_prompt({"type": "character", "description": "黑发女剑客"})
        self.assertIn(ex.MASTER_COMPOSITION, p)
        self.assertIn("高级3D漫剧写实厚涂", p)
        self.assertIn("同一焦平面", p)
        self.assertIn("无文字，无水印", p)

    def test_style_option_replaces_render_and_skin_but_keeps_composition(self):
        style = ex.load_style_anchor(6)
        p = ex.compile_full_prompt({"type": "character", "description": "黑发女剑客"}, style)
        self.assertIn(ex.MASTER_COMPOSITION, p)
        self.assertIn(style["anchor"], p)
        self.assertNotIn("次表面散射", p)

    def test_unknown_style_index_raises(self):
        with self.assertRaises(ValueError):
            ex.load_style_anchor(99)


CARD = """## 風格錨點
- **style_index**：`6`
## 角色
### C-lin　林
- **固定描述片段**：`young woman, black hair`
- **設定板描述**：`二十岁女剑客，身高168cm，七头半`
- **背面特徵**：`后领高立、露背U型、长发束尾`
- **設定圖**：`images/C-lin_sheet_v1.png`
### C-blank　空白
- **固定描述片段**：`<性別年齡>`
"""


class CardFormatTests(unittest.TestCase):
    def test_template_card_format_is_parsed_with_master_slots(self):
        assets = ex.parse_card_assets(CARD)
        self.assertEqual(len(assets), 1)  # 未填的範本佔位卡被略過
        self.assertEqual(assets[0]["filename"], "C-lin_sheet_v1.png")
        self.assertIn("身高168cm", assets[0]["description"])
        self.assertIn("背面特徵：后领高立", assets[0]["description"])

    def test_style_index_read_from_assets_md(self):
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as td:
            f = pathlib.Path(td) / "assets.md"
            f.write_text(CARD, encoding="utf-8")
            self.assertEqual(ex.read_style_index(f), 6)
            self.assertEqual(len(ex.parse_assets_markdown(f)), 1)

    def test_runner_flags_prompts_without_template_marker(self):
        from scripts.storyboard import run_codex_asset_gen as r
        items = [{"type": "character", "filename": "a.png"},
                 {"type": "character", "filename": "b.png", "template": ex.TEMPLATE_VERSION},
                 {"type": "scene", "filename": "s.png"}]
        self.assertEqual(r.stale_character_prompts(items), ["a.png"])


if __name__ == "__main__":
    unittest.main()
