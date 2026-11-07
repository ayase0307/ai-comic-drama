import pathlib, sys, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))
sys.path.insert(0, str(ROOT / "scripts"))
import export_asset_prompts as ex


class AssetStyleTests(unittest.TestCase):
    def prompts(self, token):
        st = ex.resolve_style(token)
        return {t: ex.compile_full_prompt({"type": t, "description": "X"}, st) for t in ("creature", "scene", "prop")}

    def test_no_hardcoded_photoreal_for_default(self):
        for t, p in self.prompts(None).items():
            self.assertNotIn("Photorealistic-stylized", p, t)
            self.assertNotIn("3D animated series prop", p, t)

    def test_style_changes_env_prompts(self):
        self.assertNotEqual(self.prompts(None)["scene"], self.prompts("semi-real")["scene"])
        self.assertIn("not a photograph", self.prompts("semi-real")["creature"])

    def test_semi_real_anchor_excludes_photo(self):
        st = ex.resolve_style("semi-real")
        self.assertIn("NOT a photograph", st["line"])
        self.assertNotIn("pore", st["line"] + st["quality"])
        self.assertTrue(st["needs_reference"].endswith(".jpg"))
        self.assertTrue((ROOT / st["needs_reference"]).exists())


class AssetSheetLayoutTests(unittest.TestCase):
    """P2-4（導演大師對照）：道具板 2×2＋45° 比例參照格、場景主圖四面關係條款。"""

    def test_prop_sheet_is_2x2_with_scale_reference(self):
        p = ex.compile_full_prompt({"type": "prop", "description": "a bronze dagger"})
        self.assertIn("2x2 grid", p)
        self.assertIn("45-degree three-quarter view", p)
        self.assertIn("same real-world scale", p)
        self.assertIn("adult human hand", p)
        self.assertIn("not a character", p)

    def test_scene_plate_locks_layout_relationships(self):
        p = ex.compile_full_prompt({"type": "scene", "description": "an old post office hall"})
        self.assertIn("locks the space's layout relationships", p)
        self.assertIn("three clear depth layers", p)
        self.assertIn("without inventing new walls", p)

    def test_character_prompt_has_no_prop_layout(self):
        p = ex.compile_full_prompt({"type": "character", "description": "x"})
        self.assertNotIn("2x2 grid", p)


if __name__ == "__main__":
    unittest.main()
