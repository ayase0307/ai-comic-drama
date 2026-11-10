import unittest

from scripts.storyboard import export_asset_prompts as ex


class CharacterPromptTests(unittest.TestCase):
    def test_default_is_style14_with_master_composition(self):
        p = ex.compile_full_prompt({"type": "character", "description": "黑发女剑客"})
        self.assertIn(ex.MASTER_COMPOSITION, p)
        self.assertIn("realistic East Asian bone structure", p)
        self.assertIn("同一焦平面", p)

    def test_master_option_uses_master_composition_and_3d_style(self):
        p = ex.compile_full_prompt({"type": "character", "description": "黑发女剑客"}, ex.resolve_style("master"))
        self.assertIn(ex.MASTER_COMPOSITION, p)
        self.assertIn("高级3D漫剧写实厚涂", p)
        self.assertIn("同一焦平面", p)
        self.assertIn("无文字，无水印", p)

    def test_style_option_replaces_render_and_skin_but_keeps_composition(self):
        style = ex.resolve_style("6")
        p = ex.compile_full_prompt({"type": "character", "description": "黑发女剑客"}, style)
        self.assertIn(ex.MASTER_COMPOSITION, p)
        self.assertIn(ex.load_style_anchor(6)["anchor"], p)
        self.assertIn(ex.NUMBERED_STYLE_NOTE, p)
        self.assertNotIn("次表面散射", p)

    def test_semi_real_preset_keeps_master_layout(self):
        p = ex.compile_full_prompt({"type": "character", "description": "x"}, ex.resolve_style("semi-real"))
        self.assertIn(ex.MASTER_COMPOSITION, p)
        self.assertIn("Unreal Engine 5", p)
        self.assertNotIn("高级3D漫剧写实厚涂", p)

    def test_unknown_style_token_raises(self):
        with self.assertRaises(ValueError):
            ex.resolve_style("watercolor")

    def test_fox_preset_keeps_v2_layout(self):
        p = ex.compile_full_prompt({"type": "character", "description": "九尾狐仙"}, ex.resolve_style("fox"))
        self.assertIn("0-35%", p)
        self.assertIn("杰作", p)
        self.assertIn(ex.MASTER_COMPOSITION, p)

    def test_appendage_rule_added_when_present(self):
        p = ex.compile_full_prompt({"type": "character", "description": "狐女", "appendage": "狐尾 9 条，尾椎"},
                                   ex.resolve_style("fox"))
        self.assertIn("附肢", p)
        self.assertIn("9", p)

    def test_prop_v2_has_no_hand(self):
        p = ex.compile_full_prompt({"type": "prop", "description": "银色长枪"})
        self.assertIn("2x2", p)
        self.assertIn("不要", p)
        self.assertNotIn("手掌", p)

    def test_template_version_is_sheet_v2(self):
        self.assertEqual(ex.TEMPLATE_VERSION, "sheet-v2")

    def test_back_rule_not_duplicated_when_desc_has_back_features(self):
        p = ex.compile_full_prompt({"type": "character", "description": "x；背面特徵：后领高"})
        self.assertNotIn(ex.MASTER_BACK_RULE, p)
        self.assertIn(ex.MASTER_BACK_RULE, ex.compile_full_prompt({"type": "character", "description": "x"}))

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
            self.assertEqual(ex.read_style_index(f), "6")
            self.assertEqual(len(ex.parse_assets_markdown(f)), 1)

    def test_runner_flags_prompts_without_template_marker(self):
        from scripts.storyboard import run_codex_asset_gen as r
        items = [{"type": "character", "filename": "a.png"},
                 {"type": "character", "filename": "b.png", "template": ex.TEMPLATE_VERSION},
                 {"type": "scene", "filename": "s.png"}]
        self.assertEqual(r.stale_character_prompts(items), ["a.png"])


CARD_NO_STYLE = CARD.replace("- **style_index**：`6`" + chr(10), "")


class StyleGateTests(unittest.TestCase):
    def _run(self, text, *extra):
        import contextlib, io, tempfile, pathlib
        from unittest import mock
        with tempfile.TemporaryDirectory() as td:
            f = pathlib.Path(td) / "assets.md"
            f.write_text(text, encoding="utf-8")
            err, out = io.StringIO(), io.StringIO()
            with mock.patch("sys.argv", ["x", "--assets-md", str(f), "--no-gate", *extra]),                  contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
                try:
                    ex.main()
                    code = 0
                except SystemExit as e:
                    code = e.code
            return code, err.getvalue()

    def test_missing_style_uses_default_style14_with_reminder(self):
        # 2026-10-23 起預設 14 號「古風寫實厚塗・電影感」：不再停下，但提醒與使用者確認
        code, err = self._run(CARD_NO_STYLE)
        self.assertEqual(code, 0)
        self.assertIn("預設風格 14 號", err)

    def test_explicit_style_passes_gate(self):
        code, _ = self._run(CARD_NO_STYLE, "--style", "master")
        self.assertEqual(code, 0)


class SheetV2MechanismTests(unittest.TestCase):
    def test_bindings_box_follows_template(self):
        from scripts.storyboard import generate_bindings as gb
        self.assertEqual(gb.face_crop_box({}, None, "sheet-v2"), gb.FACE_PANEL_BOX_V2)
        self.assertEqual(gb.face_crop_box({}, None, ""), gb.FACE_PANEL_BOX)
        self.assertEqual(gb.face_crop_box({"template": "sheet-v2"}), gb.FACE_PANEL_BOX_V2)

    def test_mask_fills_region_with_background(self):
        import tempfile, pathlib
        from PIL import Image
        from scripts.storyboard import crop_sheet
        with tempfile.TemporaryDirectory() as td:
            src = pathlib.Path(td) / "sheet.png"
            Image.new("RGB", (256, 144), (200, 200, 200)).save(src)
            code = crop_sheet.main(["--image", str(src), "--root", td,
                                    "--out-dir", td, "--mask", "0,0,0.35,0.6319",
                                    "--prefix", "t"])
            self.assertEqual(code, 0)
            out = pathlib.Path(td) / "t-masked.png"
            self.assertTrue(out.is_file())
            px = Image.open(out).getpixel((10, 10))
            self.assertTrue(all(abs(v - 200) < 5 for v in px[:3]))


if __name__ == "__main__":
    unittest.main()
