"""P1-5／P1-10（11-03 噩盡島 #5／#29／#31）：景別節奏與持續動作警告。

- validate_storyboard.shot_size_rhythm_warnings：同主體連續 ≥3 鏡同景別級（W:R1）、
  ≥6 鏡完全沒有 ELS/LS（W:R2）。
- prompt_authoring audit_segment：≥2.5s 的【動作】鏡 Motion 沒有持續動詞（W51）、
  有 <d> 且 ≥2.5s 的鏡 Motion 沒有持續動作（W52）。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT / "scripts"), str(ROOT / "scripts" / "storyboard")):
    if p not in sys.path:
        sys.path.insert(0, p)

import prompt_authoring as pa  # noqa: E402
from scripts.storyboard import validate_storyboard as vs  # noqa: E402


def _shot(shot_id, size, chars=None, dur=3.0):
    return {"shot_id": shot_id, "duration": dur,
            "camera_optics": {"shot_size": size},
            "character_ids": chars or []}


class ShotSizeRhythmTests(unittest.TestCase):
    def test_r1_same_tier_run_of_three_warns(self):
        shots = [_shot("A", "CU", ["C-A"]), _shot("B", "ECU", ["C-A"]), _shot("C", "CU", ["C-A"])]
        out = vs.shot_size_rhythm_warnings(shots)
        self.assertTrue(any("W:R1" in w and "A、B、C" in w for w in out), out)

    def test_r1_needs_shared_character(self):
        shots = [_shot("A", "CU", ["C-A"]), _shot("B", "ECU", ["C-B"]), _shot("C", "CU", ["C-B"])]
        out = vs.shot_size_rhythm_warnings(shots)
        # 沒有全程共同主體 → 仍報節奏，但不帶「同一主體」
        self.assertTrue(any("W:R1" in w and "同一主體" not in w for w in out), out)

    def test_r1_two_shots_do_not_warn(self):
        shots = [_shot("A", "CU", ["C-A"]), _shot("B", "ECU", ["C-A"])]
        self.assertEqual(vs.shot_size_rhythm_warnings(shots), [])

    def test_r1_breaks_on_different_tier(self):
        shots = [_shot("A", "CU", ["C-A"]), _shot("B", "MS", ["C-A"]), _shot("C", "CU", ["C-A"])]
        self.assertEqual([w for w in vs.shot_size_rhythm_warnings(shots) if "W:R1" in w], [])

    def test_r2_no_wide_in_long_segment_warns(self):
        shots = [_shot(f"S{i}", "MS") for i in range(6)]
        out = vs.shot_size_rhythm_warnings(shots)
        self.assertTrue(any("W:R2" in w for w in out), out)

    def test_r2_with_one_wide_is_silent(self):
        # 交錯景別避免 R1；最後一鏡 LS 讓 R2 沉默
        shots = [_shot("A", "MS"), _shot("B", "CU"), _shot("C", "MS"),
                 _shot("D", "CU"), _shot("E", "MS"), _shot("W", "LS")]
        self.assertEqual(vs.shot_size_rhythm_warnings(shots), [])

    def test_unknown_size_is_ignored(self):
        shots = [_shot("A", "CU", ["C-A"]), _shot("B", "ECU", ["C-A"]),
                 {"shot_id": "C", "camera_optics": {}}]
        self.assertEqual(vs.shot_size_rhythm_warnings(shots), [])


class BackgroundAnchorTests(unittest.TestCase):
    def _close(self, shot_id="A", anchors=None):
        return {"shot_id": shot_id, "camera_optics": {"shot_size": "CU"},
                "spatial_blocking": {"anchor_objects": anchors or []}}

    def test_close_shot_without_anchors_warns(self):
        out = vs.background_anchor_warnings([self._close()])
        self.assertTrue(any("W:B1" in w for w in out), out)

    def test_close_shot_with_anchors_is_silent(self):
        out = vs.background_anchor_warnings([self._close(anchors=["cracked wall", "window grille"])])
        self.assertEqual(out, [])

    def test_wide_shot_is_not_checked(self):
        out = vs.background_anchor_warnings([{"shot_id": "W", "camera_optics": {"shot_size": "LS"},
                                              "spatial_blocking": {"anchor_objects": []}}])
        self.assertEqual(out, [])

    def test_mixed_segment_reports_only_close_shots(self):
        shots = [self._close("A"), {"shot_id": "W", "camera_optics": {"shot_size": "MS"},
                                    "spatial_blocking": {"anchor_objects": []}}]
        out = vs.background_anchor_warnings(shots)
        self.assertEqual(len(out), 1)
        self.assertIn("A", out[0])


# --- W51／W52：audit_segment 的持續動作警告 -----------------------------------

BASE_PROMPT = (
    "integrated_multimodal_description: anchor. "
    "[Shot 1] The shot opens on a medium shot. "
    "Camera: static medium shot at chest height. "
    "Motion: first he raises the lantern, then he lowers it as the light settles. "
    "Performance: he watches the doorway with narrowed eyes. "
    "Light: a warm lamp light falls from the left. "
    "Sound: wind pushes against the shutters through the whole shot.\n"
    "\noverall_soundscape: quiet night wind.\n"
    "\nnon_diegetic_music: None."
)


DIALOGUE_PROMPT = (
    "integrated_multimodal_description: anchor. "
    "[Shot 1] The shot opens on a medium shot. "
    "Camera: static medium shot at chest height. "
    "Motion: first he raises the lantern, then he lowers it as the light settles. "
    "Performance: he watches the doorway with narrowed eyes. "
    "Light: a warm lamp light falls from the left. "
    "Sound: wind pushes against the shutters while he says (S1): <d>[Chinese] 誰？</d>\n"
    "\noverall_soundscape: quiet night wind.\n"
    "\nnon_diegetic_music: None."
)


def _audit(authored, prompt=None):
    return pa.audit_segment(prompt or BASE_PROMPT, authored, "EP01-S01-a")


class SustainWarningTests(unittest.TestCase):
    def action_shot(self, dur=3.0):
        return {"shot_id": "SH01", "duration": dur, "source_action": True,
                "action_mark": {"text": "【動作】", "seconds": dur},
                "dialogue_and_audio": {"has_dialogue": False}}

    def dialogue_shot(self, dur=3.0):
        return {"shot_id": "SH01", "duration": dur,
                "camera_optics": {"movement": "static"},
                "dialogue_and_audio": {"has_dialogue": True, "line_verbatim": "誰？"}}

    def test_w51_action_shot_without_sustain_warns(self):
        res = _audit([self.action_shot()])
        self.assertTrue(any("W51" in w for w in res["warnings"]), res["warnings"])

    def test_w51_silenced_by_sustain_word(self):
        prompt = BASE_PROMPT.replace("as the light settles",
                                     "all the while the light settles")
        res = pa.audit_segment(prompt, [self.action_shot()], "EP01-S01-a")
        self.assertFalse(any("W51" in w for w in res["warnings"]), res["warnings"])

    def test_w51_short_action_shot_is_silent(self):
        res = _audit([self.action_shot(dur=2.0)])
        self.assertFalse(any("W51" in w for w in res["warnings"]), res["warnings"])

    def test_w52_dialogue_shot_without_sustain_warns(self):
        res = _audit([self.dialogue_shot()], DIALOGUE_PROMPT)
        self.assertTrue(any("W52" in w for w in res["warnings"]), res["warnings"])

    def test_w52_short_dialogue_shot_is_silent(self):
        res = _audit([self.dialogue_shot(dur=2.0)], DIALOGUE_PROMPT)
        self.assertFalse(any("W52" in w for w in res["warnings"]), res["warnings"])

    def test_w52_silenced_by_sustain_word(self):
        prompt = DIALOGUE_PROMPT.replace("as the light settles",
                                         "all the while the light settles")
        res = _audit([self.dialogue_shot()], prompt)
        self.assertFalse(any("W52" in w for w in res["warnings"]), res["warnings"])

    def test_w52_accepts_progressive_action(self):
        # _remix_fixture 的寫法（starts pushing himself up）是持續過程，不該報 W52
        prompt = DIALOGUE_PROMPT.replace("then he lowers it as the light settles",
                                         "then he lowers it as he starts backing toward the door")
        res = _audit([self.dialogue_shot()], prompt)
        self.assertFalse(any("W52" in w for w in res["warnings"]), res["warnings"])

    def test_action_and_dialogue_do_not_double_report(self):
        # is_action_shot 要求無台詞；有 <d> 的鏡不會同時觸發 W51
        res = _audit([self.dialogue_shot()])
        self.assertFalse(any("W51" in w for w in res["warnings"]), res["warnings"])


class LipsConflictTests(unittest.TestCase):
    """W53（11-03 #4）：同鏡又張嘴又閉嘴——列出兩句讓人判斷，不同人各說各話合法。"""

    def test_open_and_closed_in_same_shot_warns(self):
        prompt = (
            "integrated_multimodal_description: anchor. "
            "[Shot 1] The shot opens on a medium shot. "
            "Camera: static medium shot. "
            "Motion: first Friend's lips part in a smirk, then his lips remain closed as the line lands. "
            "Performance: Friend smirks while Hero speaks. "
            "Light: warm lamp from the left. "
            "Sound: footsteps while Hero says (S1): <d>[Chinese] 走吧。</d>\n"
            "\noverall_soundscape: quiet alley.\n"
            "\nnon_diegetic_music: None."
        )
        res = pa.audit_segment(prompt, [], "EP01-S01-a")
        self.assertTrue(any("W53" in w for w in res["warnings"]), res["warnings"])

    def test_closed_only_is_silent(self):
        prompt = (
            "integrated_multimodal_description: anchor. "
            "[Shot 1] The shot opens on a medium shot. "
            "Camera: static medium shot. "
            "Motion: first Hero glances back, then he nods as the camera holds. "
            "Performance: Hero keeps his eyes forward. "
            "Light: warm lamp from the left. "
            "Sound: footsteps while Hero says (S1): <d>[Chinese] 走吧。</d> "
            "while Friend's lips remain completely closed.\n"
            "\noverall_soundscape: quiet alley.\n"
            "\nnon_diegetic_music: None."
        )
        res = pa.audit_segment(prompt, [], "EP01-S01-a")
        self.assertFalse(any("W53" in w for w in res["warnings"]), res["warnings"])


if __name__ == "__main__":
    unittest.main()
