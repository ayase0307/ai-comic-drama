"""鏡頭意圖（shot_intent／choice_why）強制檢查：references/storyboard/shot-intent.md。

反例取自 2026-10-24《噩盡島 II》EP01：agent 為了消警告而改分鏡，沒有先想每一鏡要表達什麼。
"""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))

import handoff_to_skeleton as hs  # noqa: E402
import shot_intent as si  # noqa: E402
import validate_storyboard as vs  # noqa: E402


def shot(sid, aud, dialogue=False, why=None):
    s = {
        "shot_id": sid, "start_time": 0.0, "end_time": 3.0, "duration": 3.0,
        "character_ids": ["C-a"],
        "shot_intent": {"audience": aud, "story_beat": "她被點名，慌忙起身回答",
                        "pov": "旁觀的同門，看她出糗", "emotional_shift": "走神轉成慌張"},
        "choice_why": why or {
            "shot_size": f"{sid} 中景要同時看到她跳起的全身與兩側同門",
            "lens_distance": f"{sid} 35mm 2.5 公尺保留她與同門的距離感",
            "movement": f"{sid} 跟著她起身上搖，站定後停住",
            "blocking": f"{sid} 她在畫面中央，視線朝畫左講台",
            "background": f"{sid} 兩側坐著穿淡黃袍的弟子，交代這是講堂",
        },
        "camera_optics": {"shot_size": "MS", "focal_length": "35mm", "physical_distance": "2.5m",
                          "pov_routing": "objective", "movement": "tilt up"},
        "spatial_blocking": {"anchor_objects": [], "blocking_desc": "中央起身"},
        "action_and_performance": {"action_stages": ["起身"], "observable_expression": "瞪眼"},
        "dialogue_and_audio": {"has_dialogue": dialogue, "speaker": "C-a" if dialogue else None,
                               "line_verbatim": "到！" if dialogue else None},
    }
    if dialogue and why is None:
        s["choice_why"]["line_timing"] = f"{sid} 站定後才開口，口型落在靜止畫面上"
    return s


class ShotIntentTests(unittest.TestCase):
    def codes(self, s):
        return " ".join(si.shot_intent_errors(s, s["shot_id"]))

    def test_complete_shot_passes(self):
        self.assertEqual(si.shot_intent_errors(shot("SH01", "她在全班面前被抓到走神"), "SH01"), [])

    def test_missing_intent_and_why(self):
        s = shot("SH01", "x")
        del s["shot_intent"], s["choice_why"]
        c = self.codes(s)
        self.assertIn("I01", c)
        self.assertIn("I02", c)

    def test_placeholder_and_too_short(self):
        s = shot("SH01", "同上")
        s["choice_why"]["background"] = "TODO"
        s["choice_why"]["movement"] = "固定"
        c = self.codes(s)
        self.assertIn("I03 意圖是空話", c)
        self.assertIn("choice_why.background", c)
        self.assertIn("choice_why.movement", c)

    def test_dialogue_requires_line_timing(self):
        s = shot("SH01", "她在全班面前被抓到走神", dialogue=True)
        del s["choice_why"]["line_timing"]
        self.assertIn("line_timing", self.codes(s))

    def test_reason_that_only_repeats_value(self):
        s = shot("SH01", "她在全班面前被抓到走神")
        s["camera_optics"]["movement"] = "slow dolly in please"
        s["choice_why"]["movement"] = "slow dolly in please"
        self.assertIn("I05", self.codes(s))

    def test_duplicate_intent_in_segment(self):
        errs = " ".join(si.segment_intent_errors([shot("SH01", "她被抓到走神"), shot("SH02", "她被抓到走神")]))
        self.assertIn("I04", errs)

    def test_same_reason_on_three_shots(self):
        same = {"shot_size": "中景交代人物關係與空間", "lens_distance": "35mm 接近人眼視角",
                "movement": "固定鏡頭讓表演說話", "blocking": "人物置中，視線看向對手", "background": "照場景圖露出講堂樑柱"}
        shots = [shot(f"SH0{i}", f"第{i}鏡要讓觀眾看懂的事", why=dict(same)) for i in range(1, 4)]
        self.assertIn("I05 理由套句", " ".join(si.segment_intent_errors(shots)))

    def test_cross_segment_copy(self):
        datas = []
        for n in range(5):
            s = shot("SH01", f"第{n}段的獨特意圖內容")
            s["choice_why"]["background"] = "身後露出講堂的木柱與窗格"
            datas.append({"segment_id": f"S{n}", "shots": [s]})
        self.assertIn("I06", " ".join(si.cross_segment_intent_errors(datas)))

    def test_validator_wires_intent_checks(self):
        data = {"metadata": {"target_duration_sec": 6.0, "lighting_lock_line": "窗光由畫右進，暖白"},
                "continuity_handshake": {}, "shots": [shot("SH01", "她被抓到走神"), shot("SH02", "她被抓到走神")]}
        data["shots"][1]["start_time"], data["shots"][1]["end_time"] = 3.0, 6.0
        bad = copy.deepcopy(data)
        del bad["shots"][0]["shot_intent"]
        errs = " ".join(vs.validate_storyboard_data(bad)["errors"])
        self.assertIn("I01", errs)
        self.assertIn("I04", " ".join(vs.validate_storyboard_data(data)["errors"]))
        data["shots"][1]["shot_intent"]["audience"] = "同門的笑聲讓她更窘"
        self.assertFalse(any(" I0" in e for e in vs.validate_storyboard_data(data)["errors"]))

    def test_format_error_on_wrong_type(self):
        s = shot("SH01", "她被抓到走神")
        s["shot_intent"] = "她被抓到走神"
        self.assertTrue(any("shot_intent" in e for e in vs.layer2_format_errors(
            {"metadata": {}, "continuity_handshake": {}, "shots": [s]})))

    def test_demo_valid_case_still_passes(self):
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            vs.run_demo_suite()
        self.assertIn("審查結果: PASS", buf.getvalue())

    def test_skeleton_emits_todo_intent(self):
        item = {"kind": "dialogue", "speaker": "甲", "text": "到！", "duration": 3.0,
                "audio_type": "onscreen", "note": ""}
        scene = {"characters": ["甲"], "props": []}
        s = hs.make_shot(item, "EP01-S01-SH01", 0.0, 3.0, scene, {"甲": "C-a"})
        self.assertIn("TODO", s["shot_intent"]["audience"])
        self.assertIn("line_timing", s["choice_why"])
        self.assertTrue(any("TODO" in e for e in hs.find_todo(s)))


if __name__ == "__main__":
    unittest.main()
