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
        body = GOOD1 + " <Subject 1> (S1) speaks off-screen over this shot; the visible characters keep their lips completely closed and continue their actions."
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


if __name__ == "__main__":
    unittest.main()
