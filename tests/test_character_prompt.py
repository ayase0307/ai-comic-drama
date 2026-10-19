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


if __name__ == "__main__":
    unittest.main()
