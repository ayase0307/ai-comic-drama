import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))
import codex_storyboard_panels as cp  # noqa: E402

ASSETS = """## 角色
### C-ailu　艾露
- **固定描述片段**：`woman, low bun`
- **服裝**：`W-ailu-01`　白衣　固定片段：`white top`
- **設定圖**：`images/C-ailu_W01_sheet_v1.png`

### CREATURE-kaibuli　凱布利（異獸）
- **固定描述片段**：`giant black beetle`
- **設定圖**：`images/creature-kaibuli.png`

## 場景
### S-cellar　地窖
- **固定描述片段**：`earth cellar`
"""


class CodexPanelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.r = Path(self.tmp.name)
        for d in ("layer2", "images/ref", "adapt", "panels"):
            (self.r / d).mkdir(parents=True)
        (self.r / "assets.md").write_text(ASSETS, encoding="utf-8")
        (self.r / "adapt" / "bible.json").write_text(json.dumps({"characters": [{"character_id": "C-ailu", "canonical_name": "艾露", "aliases": ["師父"]}]}), encoding="utf-8")
        for p in ("images/ref/C-ailu_front.png", "images/creature-kaibuli.png", "images/scene-cellar-master.png"):
            (self.r / p).write_bytes(b"x")
        self.seg = self.r / "layer2" / "layer2-EP01-S05-a.json"
        self.seg.write_text(json.dumps({"segment_id": "EP01-S05-a", "metadata": {"aspect_ratio": "9:16"},
                                        "asset_refs": {"scene_id": "S-cellar"}, "style_lock": {"negative": "no text"},
                                        "shots": [{"shot_id": "EP01-S05-a-SH01", "character_ids": [],
                                                   "camera_optics": {"shot_size": "MS"},
                                                   "spatial_blocking": {"blocking_desc": "師父舉燈，黑色甲蟲擋在床前"}}]},
                                       ensure_ascii=False), encoding="utf-8")
        (self.r / "staging").mkdir()
        (self.r / "staging" / "codex-panel-refs.json").write_text(json.dumps({"keywords": {"CREATURE-kaibuli": ["甲蟲"]}}, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_plan_binds_alias_creature_and_scene_refs_in_order(self):
        job = cp.plan(self.r, [self.seg])[0]
        self.assertEqual(job["subjects"], ["C-ailu", "CREATURE-kaibuli"])
        self.assertEqual([Path(p).name for _, p in job["refs"]], ["C-ailu_front.png", "creature-kaibuli.png", "scene-cellar-master.png"])
        self.assertEqual(job["aspect"], "9:16")
        self.assertIn("<Picture 2> = 凱布利", job["prompt"])
        self.assertIn("Exactly 1 person", job["prompt"])

    def test_shot_override_wins(self):
        (self.r / "staging" / "codex-panel-refs.json").write_text(json.dumps({"shots": {"EP01-S05-a-SH01": []}}), encoding="utf-8")
        job = cp.plan(self.r, [self.seg])[0]
        self.assertEqual(job["subjects"], [])
        self.assertIn("No people in frame", job["prompt"])

    def test_main_writes_back_codex_backend_and_passes_model_and_aspect(self):
        from PIL import Image
        calls = []

        def fake_gen(target, prompt, out_dir, model=None, timeout_sec=0, codex_bin=None, aspect="16:9"):
            calls.append((model, aspect, len(target["refs"])))
            Image.new("RGB", (90, 160)).save(Path(out_dir) / target["filename"])
            return True
        import run_codex_asset_gen as rc
        with mock.patch.object(rc, "resolve_codex_executable", return_value="codex"), \
             mock.patch.object(rc, "validate_codex_cli"), mock.patch.object(rc, "generate_single_asset_codex", fake_gen):
            self.assertEqual(cp.main(["--root", str(self.r), "--model", "gpt-6-luna"]), 0)
        self.assertEqual(calls, [("gpt-6-luna", "9:16", 3)])
        d = json.loads(self.seg.read_text(encoding="utf-8"))
        s = d["shots"][0]
        self.assertEqual(s["sketch_generation"]["backend"], "codex")
        self.assertEqual(s["sketch_file"], "panels/panel-01-EP01-S05-a-SH01.png")
        self.assertTrue((self.r / "images" / "grid-EP01-S05-a.png").is_file())
        self.assertEqual(d["grid_preview_file"], "images/grid-EP01-S05-a.png")

    def test_model_is_required(self):
        with self.assertRaises(SystemExit):
            cp.main(["--root", str(self.r)])



class LabelFontEnvTests(unittest.TestCase):
    def test_new_env_name_wins_and_old_name_still_works(self):
        with tempfile.TemporaryDirectory() as d:
            new, old = Path(d) / "new.ttf", Path(d) / "old.ttf"
            new.write_bytes(b"x"); old.write_bytes(b"x")
            with mock.patch.dict("os.environ", {"STORYBOARD_FONT": str(new), "SVG_GRID_FONT": str(old)}):
                self.assertEqual(cp.label_font_path(), str(new))
            with mock.patch.dict("os.environ", {"SVG_GRID_FONT": str(old)}):
                import os
                os.environ.pop("STORYBOARD_FONT", None)
                self.assertEqual(cp.label_font_path(), str(old), "舊名 SVG_GRID_FONT 要相容")

if __name__ == "__main__":
    unittest.main()


class ExtrasPanelPromptTest(unittest.TestCase):
    def test_extras_replace_no_background_figures_rule(self):
        assets = {"C-a": {"name": "甲", "fixed": "woman"}, "EXTRAS-g": {"name": "群", "fixed": "disciples"}}
        shot = {"shot_id": "X-SH01"}
        labels = [("甲 (C-a)", "a.png"), ("群 (EXTRAS-g)", "g.png")]
        p = cp.build_panel_prompt(shot, {}, ["C-a", "EXTRAS-g"], assets, labels)
        self.assertNotIn("no background figures", p)
        self.assertNotIn("no extra people", p)
        self.assertIn("group reference <Picture 2>", p)
        solo = cp.build_panel_prompt(shot, {}, ["C-a"], assets, labels[:1])
        self.assertIn("Exactly 1 person(s)", solo)
