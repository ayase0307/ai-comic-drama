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


if __name__ == "__main__":
    unittest.main()
