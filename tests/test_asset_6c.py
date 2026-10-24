import json, pathlib, shutil, sys, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))
import export_asset_prompts as ex
import build_stage_review as bsr


class T(unittest.TestCase):
    def test_avoid_field(self):
        d = ROOT / "tmp" / "t6c"; shutil.rmtree(d, ignore_errors=True); d.mkdir(parents=True)
        a = d / "assets.md"
        a.write_text("### C-zhang 張志文\n參考圖：`images/z.png`\n反美化：不帥、蠟黃、非偶像臉\n```text\nthin sallow teen\n```\n", encoding="utf-8")
        assets = ex.parse_assets_markdown(a)
        p = ex.compile_full_prompt(assets[0])
        self.assertIn("不帥、蠟黃、非偶像臉", p)
        shutil.rmtree(d, ignore_errors=True)

    def test_no_avoid_unchanged(self):
        p = ex.compile_full_prompt({"type": "character", "description": "x"})
        self.assertNotIn("負面約束", p)

    def test_scenes_without_master(self):
        d = ROOT / "tmp" / "t6c2"; shutil.rmtree(d, ignore_errors=True)
        (d / "adapt").mkdir(parents=True); (d / "images").mkdir()
        (d / "images" / "a.png").write_bytes(b"x")
        (d / "adapt" / "bible.json").write_text(json.dumps({"locations": [{"location_id": "S-a", "image_file": "images/a.png"}]}))
        (d / "layer2-ep01.json").write_text(json.dumps({"shots": [{"asset_refs": {"scene_id": "S-a"}}, {"asset_refs": {"scene_id": "S-b"}}]}))
        self.assertEqual(bsr.scenes_without_master(d), ["S-b"])
        shutil.rmtree(d, ignore_errors=True)

if __name__ == "__main__":
    unittest.main()
