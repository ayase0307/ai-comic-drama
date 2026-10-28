"""牆面分配層工具（scripts/storyboard/wall_map.py，可選、不接編譯）。老易空間實驗 2026-10。"""
import contextlib
import copy
import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))

import wall_map  # noqa: E402

EXAMPLE = ROOT / "references" / "storyboard" / "templates" / "wall-map.example.json"


def _load():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


class FrameSideTests(unittest.TestCase):
    def test_facing_north(self):
        self.assertEqual(wall_map.frame_side("north", "west"), "frame left")
        self.assertEqual(wall_map.frame_side("north", "east"), "frame right")

    def test_reverse_shot_flips_sides(self):
        self.assertEqual(wall_map.frame_side("south", "west"), "frame right")
        self.assertEqual(wall_map.frame_side("south", "east"), "frame left")

    def test_side_shots(self):
        self.assertEqual(wall_map.frame_side("west", "north"), "frame right")
        self.assertEqual(wall_map.frame_side("east", "north"), "frame left")

    def test_bad_facing(self):
        with self.assertRaises(ValueError):
            wall_map.frame_side("northeast", "west")


class RenderTests(unittest.TestCase):
    def test_example_renders_clean(self):
        results = wall_map.render_all(_load())
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["errors"], [], r)
            self.assertTrue(r["text"].startswith("Wall map: "))
            # 每鏡都重寫全部場景常量
            for needle in ("only on the west wall", "only on the north wall", "only on the east wall", "only on the south wall"):
                self.assertIn(needle, r["text"])
            # 主光鎖世界位置並換算成本機位畫面方向
            self.assertIn("comes only from the east, frame right in this shot.", r["text"])

    def test_pair_sentence_only_when_given(self):
        r1, r2 = wall_map.render_all(_load())
        self.assertNotIn("matching view", r1["text"])
        self.assertIn("matching view", r2["text"])

    def test_auto_place_from_camera_facing(self):
        wm = _load()
        del wm["shots"]["S01-c#1"]["place"]["counter"]
        r = wall_map.render_shot(wm, "S01-c#1")
        self.assertIn("the counter is only on the west wall, frame left here", r["text"])

    def test_same_as_above_is_error(self):
        wm = _load()
        wm["shots"]["S01-c#2"]["directions"] = "Same as above."
        r = wall_map.render_shot(wm, "S01-c#2")
        self.assertTrue(any("同上" in e for e in r["errors"]))

    def test_missing_negation_is_error(self):
        wm = _load()
        wm["shots"]["S01-c#1"]["no_new_openings"] = ""
        self.assertTrue(wall_map.render_shot(wm, "S01-c#1")["errors"])

    def test_two_negation_sentences_is_error(self):
        wm = _load()
        wm["shots"]["S01-c#1"]["no_new_openings"] = "No window. No door."
        self.assertTrue(wall_map.render_shot(wm, "S01-c#1")["errors"])

    def test_duplicate_negation_across_shots_is_error(self):
        wm = _load()
        wm["shots"]["S01-c#2"]["no_new_openings"] = wm["shots"]["S01-c#1"]["no_new_openings"]
        results = wall_map.render_all(wm)
        self.assertTrue(any("相同" in e for e in results[1]["errors"]))

    def test_unknown_place_key_is_error(self):
        wm = _load()
        wm["shots"]["S01-c#1"]["place"]["window"] = "frame left"
        self.assertTrue(wall_map.render_shot(wm, "S01-c#1")["errors"])

    def test_char_budget_warning(self):
        wm = copy.deepcopy(_load())
        wm["char_budget"] = 100
        r = wall_map.render_shot(wm, "S01-c#1")
        self.assertEqual(r["errors"], [])
        self.assertTrue(r["warnings"])

    def test_cli_exit_codes(self):
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            self.assertEqual(wall_map.main(["--map", str(EXAMPLE), "--json"]), 0)
        self.assertEqual(len(json.loads(buf.getvalue())), 2)


if __name__ == "__main__":
    unittest.main()
