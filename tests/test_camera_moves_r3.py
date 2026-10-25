"""PR-14 後續：第 3 輪（Loop Forge 配方）8 個 move_preset。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))
import camera_moves  # noqa: E402

DZ = {"subject": "<Subject 1>", "background": "a rusty water tower and rows of lit office towers"}
R3 = ["dolly_zoom", "dolly_zoom_reverse", "snorricam", "eyes_in", "aerial_pullback",
      "super_dolly_in", "yoyo_zoom", "split_screen_3"]


class R3PresetTests(unittest.TestCase):
    def test_all_eight_present_and_pass(self):
        for pid in R3:
            self.assertIn(pid, camera_moves.PRESETS)
            self.assertEqual(camera_moves.PRESETS[pid]["status"], "pass", pid)

    def test_aliases(self):
        cases = {"推拉變焦": "dolly_zoom", "dolly zoom 反向": "dolly_zoom_reverse", "Snorricam": "snorricam",
                 "eyes-in": "eyes_in", "高空後拉": "aerial_pullback", "super dolly in": "super_dolly_in",
                 "yo-yo zoom": "yoyo_zoom", "三格分割": "split_screen_3"}
        for name, pid in cases.items():
            self.assertEqual(camera_moves.find_preset(name), pid, name)

    def test_dolly_zoom_no_longer_experimental(self):
        clause, warn = camera_moves.expand_preset("dolly_zoom", DZ)
        self.assertEqual(warn, [])
        # LF 句型順序：先鎖主角大小位置、面向鏡頭、站定，再寫動詞對
        lock = clause.index("stay exactly constant")
        face = clause.index("faces the camera squarely")
        rooted = clause.index("rooted to one spot")
        verbs = clause.index("pushes in while simultaneously zooming out")
        self.assertLess(lock, face)
        self.assertLess(face, rooted)
        self.assertLess(rooted, verbs)
        self.assertIn("recede, shrink, and spread apart", clause)
        self.assertIn("rusty water tower", clause)

    def test_dolly_zoom_reverse_and_direction_slot(self):
        rev, _ = camera_moves.expand_preset("dolly_zoom_reverse", DZ)
        self.assertIn("pulls out while simultaneously zooming in", rev)
        self.assertIn("compress closer together", rev)
        via_dir, _ = camera_moves.expand_preset("dolly_zoom", dict(DZ, direction="reverse"))
        self.assertEqual(rev, via_dir)
        fwd, _ = camera_moves.expand_preset("dolly_zoom", dict(DZ, direction="forward"))
        self.assertIn("pushes in", fwd)
        with self.assertRaises(ValueError):
            camera_moves.expand_preset("dolly_zoom", dict(DZ, direction="sideways"))

    def test_dolly_zoom_requires_background(self):
        with self.assertRaises(ValueError):
            camera_moves.expand_preset("dolly_zoom", {"subject": "<Subject 1>"})

    def test_bg_plate_warns_for_strong_lf_moves(self):
        _, warn = camera_moves.expand_preset("dolly_zoom", DZ, bg_plate=True)
        self.assertTrue(any("砍半" in w for w in warn))
        _, warn = camera_moves.expand_preset("dutch_canted", {}, bg_plate=True)
        self.assertEqual(warn, [])

    def test_framing_mismatch_warns(self):
        _, warn = camera_moves.expand_preset("dolly_zoom", DZ, shot_size="ELS")
        self.assertTrue(any("開場構圖" in w for w in warn))
        _, warn = camera_moves.expand_preset("dolly_zoom", DZ, shot_size="ms")
        self.assertEqual(warn, [])

    def test_snorricam(self):
        clause, warn = camera_moves.expand_preset("snorricam", {"subject": "<Subject 1>"})
        self.assertIn("fixed rigidly to <Subject 1>", clause)
        self.assertIn("<Subject 1>'s face locked dead-centre", clause)
        self.assertIn("with every stride", clause)
        self.assertEqual(warn, [])
        _, warn = camera_moves.expand_preset("snorricam", {"subject": "the cart", "subject_kind": "object"})
        self.assertTrue(any("自己移動" in w for w in warn))

    def test_eyes_in_eye_and_object_detail(self):
        clause, _ = camera_moves.expand_preset("eyes_in", {"subject": "<Subject 1>"})
        self.assertIn("<Subject 1>'s right eye", clause)
        clause, _ = camera_moves.expand_preset("eyes_in", {"subject": "<Subject 1>", "eye": "左"})
        self.assertIn("left eye", clause)
        with self.assertRaises(ValueError):
            camera_moves.expand_preset("eyes_in", {"subject": "the bell", "subject_kind": "object"})
        clause, warn = camera_moves.expand_preset(
            "eyes_in", {"subject": "the bell", "subject_kind": "object", "detail": "the maker's mark"})
        self.assertIn("the maker's mark fills the entire frame", clause)
        self.assertTrue(any("只驗證過人物" in w for w in warn))

    def test_bad_subject_kind(self):
        with self.assertRaises(ValueError):
            camera_moves.expand_preset("snorricam", {"subject": "x", "subject_kind": "ghost"})

    def test_aerial_pullback(self):
        clause, _ = camera_moves.expand_preset("aerial_pullback", {"subject": "<Subject 1>", "location": "rooftop"})
        self.assertIn("pulls out with large amplitude at fast speed while pedestalling up", clause)
        self.assertIn("small lone figure", clause)
        self.assertIn("whole rooftop", clause)

    def test_super_dolly_in_space_slots_and_caution(self):
        slots = {"subject": "<Subject 1>", "space": "a narrow rooftop walkway",
                 "near_objects": "two rusty vent pipes", "further_objects": "air-conditioning units",
                 "ground": "the wet concrete"}
        clause, warn = camera_moves.expand_preset("super_dolly_in", slots, shot_size="ELS")
        self.assertIn("charging the entire length of a narrow rooftop walkway", clause)
        self.assertIn("two rusty vent pipes sweep outward", clause)
        self.assertTrue(any("同一地點" in w for w in warn))
        self.assertFalse(any("開場構圖" in w for w in warn))
        _, warn = camera_moves.expand_preset("super_dolly_in", slots, shot_size="MS")
        self.assertTrue(any("開場構圖" in w for w in warn))
        with self.assertRaises(ValueError):
            camera_moves.expand_preset("super_dolly_in", {"subject": "<Subject 1>"})

    def test_yoyo_requires_8_seconds(self):
        slots = {"subject": "<Subject 1>", "place": "on the concrete rooftop"}
        clause, warn = camera_moves.expand_preset("yoyo_zoom", slots, seconds=5)
        self.assertTrue(any("8 秒" in w for w in warn))
        self.assertIn("accelerating harder and harder", clause)
        self.assertIn("a tiny figure on the concrete rooftop", clause)
        _, warn = camera_moves.expand_preset("yoyo_zoom", slots, seconds=8)
        self.assertEqual(warn, [])
        self.assertEqual(camera_moves.required_seconds("yoyo_zoom", 5), 8)
        self.assertEqual(camera_moves.required_seconds("yoyo_zoom", 9), 10)
        self.assertEqual(camera_moves.required_seconds("溜溜球變焦"), 8)
        self.assertEqual(camera_moves.required_seconds("dolly_zoom", 5), 5)
        self.assertEqual(camera_moves.required_seconds("dolly_zoom", 6), 8)

    def test_split_screen_8_seconds_layout_only(self):
        slots = {"subject": "<Subject 1>", "action": "seated at a desk typing on a laptop",
                 "action_short": "typing", "panel_1_angle": "his left side in profile",
                 "panel_2_angle": "the front", "panel_3_angle": "behind"}
        clause, warn = camera_moves.expand_preset("split_screen_3", slots, seconds=5)
        self.assertIn("three equal vertical panels", clause)
        self.assertIn("solid black", clause)
        self.assertTrue(any("8 秒" in w for w in warn))
        self.assertTrue(any("layout-only" in w for w in warn))
        self.assertTrue(camera_moves.PRESETS["split_screen_3"]["layout_only"])
        self.assertEqual(camera_moves.required_seconds("split_screen_3", 5), 8)

    def test_no_curly_placeholders_left(self):
        for pid in R3:
            spec = camera_moves.PRESETS[pid]
            clause, _ = camera_moves.expand_preset(pid, {k: "X" for k in spec["slots"]})
            self.assertNotIn("{", clause, pid)


class R3CompilerIntegrationTests(unittest.TestCase):
    """compile_segment_h3 展開 move_preset，並把 8 秒／背景參考圖警告寫進 compile_notes。"""

    def setUp(self):
        import test_h3_compiler  # 同目錄的既有 fixture
        self.base = test_h3_compiler.H3CompilerRegressionTests("setUp")
        self.base.setUp()
        self.compiler = test_h3_compiler.compiler

    def _compile(self, preset, slots, independent=False):
        seg = self.base.segment()
        if not independent:
            seg["continuity_handshake"] = {"mode": "CHAINED"}
        seg["shots"][0]["camera_optics"]["move_preset"] = preset
        seg["shots"][0]["camera_optics"]["move_slots"] = slots
        return self.compiler.compile_segment_h3(seg, self.base.registry)

    def test_yoyo_short_shot_note(self):
        out = self._compile("yoyo_zoom", {"subject": "Mira", "place": "in the quiet room"})
        self.assertIn("zooms back in with large amplitude at fast speed", out["h3_prompt"])
        self.assertTrue(any("yoyo_zoom" in n and "8 秒" in n for n in out["compile_notes"]))

    def test_dolly_zoom_with_scene_plate_note(self):
        out = self._compile("dolly_zoom", {"subject": "Mira", "background": "the window frame and stone wall"},
                            independent=True)
        self.assertIn("pushes in while simultaneously zooming out", out["h3_prompt"])
        self.assertTrue(any("dolly_zoom" in n and "砍半" in n for n in out["compile_notes"]))


if __name__ == "__main__":
    unittest.main()
