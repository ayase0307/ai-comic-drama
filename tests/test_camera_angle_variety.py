"""Eian 文章對照（2026-11-05）：W:R3 正面平視配額。

validate_storyboard.camera_angle_variety_warnings：同段 ≥3 鏡 pov_routing=objective
（正面平視客觀機位）→ W:R3，提醒換俯拍／仰拍／背後／過肩／遮擋機位。
文章原規則是短片「全片平視正面最多兩次」；長篇按段套用。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT / "scripts"), str(ROOT / "scripts" / "storyboard")):
    if p not in sys.path:
        sys.path.insert(0, p)

from scripts.storyboard import validate_storyboard as vs  # noqa: E402


def _shot(shot_id, pov):
    return {"shot_id": shot_id, "camera_optics": {"pov_routing": pov}}


class CameraAngleVarietyTests(unittest.TestCase):
    def test_three_objective_shots_warn(self):
        shots = [_shot("A", "objective"), _shot("B", "objective"), _shot("C", "objective")]
        out = vs.camera_angle_variety_warnings(shots)
        self.assertTrue(any("W:R3" in w and "A、B、C" in w for w in out), out)

    def test_two_objective_shots_silent(self):
        shots = [_shot("A", "objective"), _shot("B", "objective")]
        self.assertEqual(vs.camera_angle_variety_warnings(shots), [])

    def test_varied_pov_is_silent(self):
        shots = [_shot("A", "objective"), _shot("B", "defensive_reaction_ots"),
                 _shot("C", "dirty_frame_20_35"), _shot("D", "objective")]
        self.assertEqual(vs.camera_angle_variety_warnings(shots), [])

    def test_missing_pov_is_ignored(self):
        shots = [{"shot_id": "A", "camera_optics": {}},
                 {"shot_id": "B", "camera_optics": {}},
                 {"shot_id": "C", "camera_optics": {}}]
        self.assertEqual(vs.camera_angle_variety_warnings(shots), [])

    def test_integrated_into_validate_warnings(self):
        # 走 validate_storyboard_data 的警告彙總路徑，確認 W:R3 有被接進去
        data = {
            "project_id": "T", "scene_id": "EP01-S01", "segment_id": "EP01-S01",
            "metadata": {"aspect_ratio": "16:9", "target_duration_sec": 9.0},
            "shots": [_shot(f"S{i}", "objective") for i in range(3)],
        }
        for i, s in enumerate(data["shots"]):
            s.update({"duration": 3.0, "dramatic_beat_type": "Dramatic_Core",
                      "camera_optics": {"pov_routing": "objective", "shot_size": "MS",
                                        "focal_length": "35mm", "physical_distance": "2m",
                                        "movement": "static"},
                      "shot_intent": {"audience": "觀眾看懂他正在猶豫要不要開口",
                                      "story_beat": "他第三次走向門又停下",
                                      "pov": "觀眾站在他背後那一側",
                                      "emotional_shift": "從決然到遲疑"},
                      "choice_why": {"shot_size": "中景保留手勢與環境", "lens_distance": "35mm 2m 對話距離",
                                     "movement": "固定鏡讓遲疑自己演出來", "blocking": "他偏畫面右側留左側空間",
                                     "background": "露走廊盡頭的窗格"},
                      "spatial_blocking": {"anchor_objects": ["走廊窗格"], "blocking_desc": "他站畫面右側"},
                      "action_and_performance": {"action_stages": ["①抬手", "②停住"], "observable_expression": "眉頭鬆開"},
                      "dialogue_and_audio": {"has_dialogue": False}})
        res = vs.validate_storyboard_data(data)
        self.assertTrue(any("W:R3" in w for w in res["warnings"]), res["warnings"])


if __name__ == "__main__":
    unittest.main()
