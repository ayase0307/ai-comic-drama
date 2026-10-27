"""逐鏡撰寫審查（防偷懶）回歸測試：references/prompt-authoring.md。

反例取自實戰：《噩盡島》EP01 由 agent 用腳本把五小節套成同一組句子
（Hold the authored support…／no added step…），全部 139 鏡都過了原本的 17 條自檢。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))

import prompt_authoring as pa  # noqa: E402

HEAD1 = "[Shot 1] The scene opens with <Picture 1> as a scene/style reference for spatial guidance: MCU (50mm, 1.5m) of <Subject 1>, as the camera dollies in."
HEAD2 = "[Shot 2] At 00:04.000, the shot cuts to a CU (85mm, 1m) of <Subject 1>, as the camera holds a static shot."

GOOD1 = (
    "Camera: 50mm from one and a half metres at his eye height, moving closer by about a tenth over 4 s, ending on a tight medium close-up. "
    "Motion: First his palm slides along the warm stone, then his fingers catch on a ridge, as his weight tips onto his left foot, finally he pulls the hand back to his chest. "
    "Performance: His brows draw together and his lips part without a sound; he swallows once and keeps staring at the stone. "
    "Light: The noon sun from frame right flattens the grey rock and throws a hard shadow of his hand across its grain. "
    "Sound: His sleeve rasps on the rock at about 1.2 s under steady island wind."
)
GOOD2 = (
    "Camera: 85mm from one metre at his eye height, locked off for 4 s with his face on the left third. "
    "Motion: First his head snaps toward frame right, then his eyes search past the lens, as his shoulders rise toward his ears, finally he touches his right ear with two fingers. "
    "Performance: His eyes widen and dart twice; the breath stops in his throat and his mouth hangs half open. "
    "Light: Sun glare blooms on his cheek and a thin red glow starts to edge the rim of his ear. "
    "Sound: The wind drops out at about 0.5 s and a low whisper rises near his right ear."
)

TEMPLATE = (
    "Camera: static for 4s at the visible subject's eye line; hold the authored MCU crop from first frame to last. "
    "Motion: He indicates the stone with an open hand. Hold the authored support and end pose; only an expressly named breath, eyeline, or small gesture may shift, with no added step or prop contact. "
    "Performance: Keep the eyes on the specified partner or object; a small breath and one restrained brow change carry the beat without adding a new gesture. No new gesture crosses the crop. "
    "Light: clear midday sun with consistent physical direction on skin and stone; its direction and softness stay fixed to the approved plate; no loose particles appear unless the action names them. "
    "Sound: Keep the continuous bed through the shot; add no isolated one-off Foley beyond the soundscape already listed."
)


def prompt(*shots):
    return "subject_definitions:\nx\n\ndetailed_description:\nStyle line.\n" + "\n".join(shots) + "\n\noverall_soundscape:\nwind\n"


def seg(sid, text, shots=None, fingerprint=None):
    s = {"segment_id": sid, "h3_prompt": text, "metadata": {}}
    if shots is not None:
        s["shots"] = shots
    if fingerprint is not None:
        s["metadata"]["compiled_prompt_sha256"] = fingerprint
    return s


class PromptAuthoringTests(unittest.TestCase):
    def test_hand_written_five_part_passes(self):
        p = prompt(f"{HEAD1} {GOOD1}", f"{HEAD2} {GOOD2}")
        res = pa.audit_segments([seg("A", p, fingerprint=pa.prompt_fingerprint(p))])
        self.assertTrue(res["passed"], res["errors"])

    def test_scripted_template_is_rejected(self):
        p = prompt(f"{HEAD1} {TEMPLATE}", f"{HEAD2} {TEMPLATE}")
        codes = " ".join(pa.audit_segment(p)["errors"])
        for code in ("E33", "E34", "E35"):
            self.assertIn(code, codes)

    def test_missing_and_thin_parts(self):
        p = prompt(f"{HEAD1} Camera: 50mm from two metres at his eye height over four seconds. Motion: He turns. Performance: Sad.")
        codes = " ".join(pa.audit_segment(p)["errors"])
        self.assertIn("E30", codes)
        self.assertIn("E31", codes)

    def test_motion_must_be_a_process(self):
        motion = "Motion: He stands beside the stone and keeps the same pose for the whole take, his hands at his sides and the group in a loose line behind him."
        body = GOOD1.split("Motion:")[0] + motion + " Performance:" + GOOD1.split("Performance:")[1]
        codes = " ".join(pa.audit_segment(prompt(f"{HEAD1} {body}"))["errors"])
        self.assertIn("E32", codes)

    def test_expressive_negation_is_not_defensive(self):
        body = GOOD2.replace("Performance: His eyes widen and dart twice; the breath stops in his throat and his mouth hangs half open.",
                             "Performance: No tremble in the voice; his gaze does not drop; a wet glint without tears; he never blinks.")
        self.assertNotIn("E35", " ".join(pa.audit_segment(prompt(f"{HEAD2} {body}"))["errors"]))

    def test_storyboard_movement_and_dialogue_route(self):
        shots = [
            {"camera_optics": {"movement": "緩推近到臉"}, "character_ids": ["C-a"],
             "dialogue_and_audio": {"speech_events": [{"audio_route": "visible_mouth_dialogue"}]}},
        ]
        head = HEAD1.replace("dollies in", "holds a static shot")
        body = GOOD1 + " The visible characters keep their lips completely closed and continue their actions, and the shot carries only the location ambience."
        codes = " ".join(pa.audit_segment(prompt(f"{head} {body}"), shots)["errors"])
        self.assertIn("E36", codes)
        self.assertIn("E37", codes)

    def test_post_compile_rewrite_is_detected(self):
        p = prompt(f"{HEAD1} {GOOD1}", f"{HEAD2} {GOOD2}")
        fp = pa.prompt_fingerprint(p)
        rewritten = p.replace("warm stone", "cold stone")
        res = pa.audit_segments([seg("A", rewritten, fingerprint=fp)])
        self.assertIn("E38", " ".join(res["errors"]))
        # subject_definitions 的自動修正不算改寫
        fixed = p.replace("subject_definitions:\nx", "subject_definitions:\ny")
        self.assertTrue(pa.audit_segments([seg("A", fixed, fingerprint=fp)])["passed"])

    def test_cross_segment_template(self):
        line = "Hold the breath and let the chest rise slowly while the shoulders stay square to the stone face."
        segs = []
        for i in range(3):
            g1 = GOOD1.replace("Sound:", f"{line} Sound:").replace("1.2 s", f"1.{i} s")
            segs.append(seg(f"S{i}", prompt(f"{HEAD1} {g1}")))
        g2 = GOOD2.replace("Sound:", f"{line} Sound:")
        segs.append(seg("S9", prompt(f"{HEAD1} {g2}", f"{HEAD2} {GOOD2.replace('Sound:', line + ' Sound:')}")))
        self.assertIn("跨段套句", " ".join(pa.audit_segments(segs)["errors"]))

    def test_unfingerprinted_segments_only_warn(self):
        p = prompt(f"{HEAD1} {GOOD1}")
        res = pa.audit_segments([seg("A", p)])
        self.assertTrue(res["passed"])
        self.assertIn("W30", " ".join(res["warnings"]))



class BackgroundAndMoodTests(unittest.TestCase):
    """2026-10-24《噩盡島 II》EP01：為了壓背景警告，提示詞被寫成 the background is empty。"""

    def test_empty_background_is_rejected(self):
        bad = GOOD2.replace("Light: Sun glare", "Light: The background is empty. Sun glare")
        codes = " ".join(pa.audit_segment(prompt(f"{HEAD2} {bad}"))["errors"])
        self.assertIn("E40", codes)

    def test_concrete_background_passes(self):
        good = GOOD2.replace("Light: Sun glare", "Light: Behind him the vine-wrapped pillars of the hall, no one else behind him. Sun glare")
        res = pa.audit_segment(prompt(f"{HEAD2} {good}"))
        self.assertFalse(any("E40" in e for e in res["errors"]), res["errors"])

    def test_mood_word_without_visual_cue_warns(self):
        bad = GOOD2.replace("Sound: The wind", "Light: x. Sound: The wind").replace(
            "Performance: His eyes", "Performance: A cinematic and dramatic moment. His eyes")
        warns = " ".join(pa.audit_segment(prompt(f"{HEAD2} {bad}"))["warnings"])
        self.assertIn("W40", warns)


class FoyegeWarningTests(unittest.TestCase):
    """PR-F2：Foyege 導演法的 W41–W45（來源 Foyege、H3 0 實測，全部只警告不擋）。"""

    DIALOGUE = " <Subject 1> (S1) says: <d>[Chinese] 你昨晚去哪了？</d>."

    def _warns(self, text):
        res = pa.audit_segment(text)
        return res, " ".join(res["warnings"])

    def test_w41_gaze_with_screen_direction_passes(self):
        body = GOOD1.replace("Performance: His brows", "Performance: He looks at her off-screen left; his brows") + self.DIALOGUE
        res, warns = self._warns(prompt(f"{HEAD1} {body}"))
        self.assertTrue(res["passed"], res["errors"])
        self.assertNotIn("W41", warns)

    def test_w41_gaze_without_direction_warns_only(self):
        body = GOOD1.replace("Performance: His brows", "Performance: He looks at her; his brows") + self.DIALOGUE
        res, warns = self._warns(prompt(f"{HEAD1} {body}"))
        self.assertIn("W41", warns)
        self.assertFalse(any("W41" in e for e in res["errors"]))

    def test_w41_no_gaze_is_left_to_d07(self):
        # 完全沒有視線句：那是 h3d staging D07 的範圍，W41 不重複報
        body = GOOD1 + self.DIALOGUE
        _, warns = self._warns(prompt(f"{HEAD1} {body}"))
        self.assertNotIn("W41", warns)

    def test_w41_light_side_does_not_count_as_gaze_direction(self):
        # GOOD1 的 Light 有 frame right（陽光方向），不能拿來當視線方向
        body = GOOD1.replace("Performance: His brows", "Performance: He looks at her; his brows") + self.DIALOGUE
        self.assertIn("frame right", body)
        _, warns = self._warns(prompt(f"{HEAD1} {body}"))
        self.assertIn("W41", warns)

    def test_d07_and_w41_share_gaze_detection(self):
        import staging_lint
        self.assertIsNotNone(staging_lint.find_gaze("He looks at her across the table."))
        self.assertIsNone(staging_lint.find_gaze("He looks at the camera."))

    def test_w42_clean_mapping_passes(self):
        text = prompt(f"{HEAD1} {GOOD1}").replace(
            "subject_definitions:\nx", "subject_definitions:\n<Subject 1> is the character in <Picture 2> (Lin; reference image 2), a lean young guide.")
        self.assertNotIn("W42", self._warns(text)[1])

    def test_w42_position_or_pose_in_mapping_warns(self):
        for extra in ("standing at frame left by the door", "seated at the table", "in the foreground"):
            text = prompt(f"{HEAD1} {GOOD1}").replace(
                "subject_definitions:\nx", f"subject_definitions:\n<Subject 1> is the character in <Picture 2> (Lin), {extra}.")
            res, warns = self._warns(text)
            self.assertIn("W42", warns, extra)
            self.assertTrue(res["passed"], res["errors"])

    def test_w42_compiler_extras_line_is_exempt(self):
        text = prompt(f"{HEAD1} {GOOD1}").replace(
            "subject_definitions:\nx", "subject_definitions:\n<Subject 2> is the group of background extras in <Picture 3> "
            "(villagers; a crowd group reference), farmers; they stay in the background as a group.")
        self.assertNotIn("W42", self._warns(text)[1])

    WIDE = "[Shot 1] The scene opens with <Picture 1> as a scene/style reference for spatial guidance: WS (24mm, 8m) of <Subject 1>, as the camera trucks left."

    def test_w43_pores_in_wide_realistic_shot_warns(self):
        body = GOOD1.replace("Performance: His brows", "Performance: Visible pores on his cheeks; his brows")
        res, warns = self._warns(prompt(f"Photorealistic live-action film. {self.WIDE} {body}"))
        self.assertIn("W43", warns)
        self.assertTrue(res["passed"], res["errors"])

    def test_w43_close_up_and_locked_skin_block_pass(self):
        body = GOOD1.replace("Performance: His brows", "Performance: Visible pores on his cheeks; his brows")
        # 近景寫毛孔：不報
        self.assertNotIn("W43", self._warns(prompt(f"Photorealistic live-action film. {HEAD1} {body}"))[1])
        # 遠景但只有守富定版皮膚段：不報
        locked = ("photorealistic skin with visible pores and natural micro-texture; fine peach-fuzz vellus hairs along the cheek edge. "
                  "Shot on 35mm Kodak Portra 400 film, fine silver-halide grain.")
        self.assertNotIn("W43", self._warns(prompt(f"{self.WIDE} {GOOD1.replace('Sound:', locked + ' Sound:')}"))[1])
        # 非寫實畫風：不報
        self.assertNotIn("W43", self._warns(prompt(f"{self.WIDE} {body}"))[1])

    def test_w44_emotion_only_and_au_codes_warn(self):
        emo = GOOD2.replace("Performance: His eyes widen and dart twice; the breath stops in his throat and his mouth hangs half open.",
                            "Performance: He is shocked, scared and deeply upset, overwhelmed and sad.")
        res, warns = self._warns(prompt(f"{HEAD2} {emo}"))
        self.assertIn("W44", warns)
        self.assertFalse(any("W44" in e for e in res["errors"]))
        au = GOOD2.replace("Performance: His eyes widen", "Performance: AU1+2 then AU25; his eyes widen")
        self.assertIn("W44", self._warns(prompt(f"{HEAD2} {au}"))[1])

    def test_w44_visible_cues_pass(self):
        ok = GOOD2.replace("Performance: His eyes widen", "Performance: Shocked, his eyes widen")
        self.assertNotIn("W44", self._warns(prompt(f"{HEAD2} {ok}"))[1])

    def test_w45_mid_shot_relisting_world_positions_warns(self):
        relist = GOOD2.replace("Light: Sun glare",
                               "Light: <Subject 1> stays by the door, <Subject 2> sits at the head of the table and "
                               "<Subject 3> waits beside the window. Sun glare")
        res, warns = self._warns(prompt(f"{HEAD1} {GOOD1}", f"{HEAD2} {relist}"))
        self.assertIn("W45", warns)
        self.assertTrue(res["passed"], res["errors"])

    def test_w45_first_shot_and_left_to_right_pass(self):
        relist = GOOD1.replace("Light: The noon", "Light: <Subject 1> stays by the door, <Subject 2> sits at the head of the table and "
                               "<Subject 3> waits beside the window. The noon")
        self.assertNotIn("W45", self._warns(prompt(f"{HEAD1} {relist}"))[1])
        # D08 要的 left to right 名單不是世界站位，不報
        ltr = GOOD2.replace("Light: Sun glare", "Light: Left to right: <Subject 1>, <Subject 2>, <Subject 3>. Sun glare")
        self.assertNotIn("W45", self._warns(prompt(f"{HEAD1} {GOOD1}", f"{HEAD2} {ltr}"))[1])


if __name__ == "__main__":
    unittest.main()
