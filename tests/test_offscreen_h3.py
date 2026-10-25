"""PR-10c：畫外音／旁白由 H3 直接生成（findings #104 #114 #122 #123）。

句式來自噩盡島實測（EP01-S02-b「氣已極淡……等久了？」、S02-d「如你所願。」、
S03-e「人生用這種方式結束，也算得上別緻。」拼音相似度 1.00）：
- O.S.：the line is heard from X (Sn) off-screen, <聲線>: <d>…</d> while <Subject k>'s lips remain completely closed.
- V.O.：X (Sn) says in an off-screen voiceover, <聲線>: <d>…</d> while no face is on screen, so all lips remain completely closed.
"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))

import compile_layer2_to_h3 as compiler  # noqa: E402
import audit_refs_and_segments as audit  # noqa: E402
import project_state as ps  # noqa: E402
import voice_lint  # noqa: E402

BIRD_VOICE = "a deep, ancient, resonant voice of indeterminate age, slow and calm"


def _registry():
    reg = compiler.AssetRegistry()
    reg.locations["S-ROCK"] = {"id": "S-ROCK", "name": "Rock", "desc_en": "a black volcanic boulder under noon sun",
                               "ref_img": "assets/scenes/rock.png"}
    reg.characters["C-HERO"] = {"id": "C-HERO", "name": "Luonian", "desc_en": "a teenage boy in a white shirt",
                                "ref_img": "assets/characters/hero.png", "wardrobe_states": {}, "is_creature": False}
    reg.characters["C-BIRD"] = {"id": "C-BIRD", "name": "the crimson bird", "desc_en": "an unseen crimson bird",
                                "ref_img": "", "wardrobe_states": {}, "no_visual_reference": True, "voice_only": True}
    return reg


def _segment(shot_overrides):
    shot = {
        "shot_id": "S1", "start_time": 0.0, "end_time": 4.0, "duration": 4.0,
        "character_ids": ["C-HERO"],
        "camera_optics": {"shot_size": "CU", "focal_length": "85mm", "physical_distance": "1.2m", "movement": "static"},
        "spatial_blocking": {"blocking_desc": "Luonian's face close-up, sky soft behind."},
        "action_and_performance": {
            "action_stages": ["His shoulders lock and his head jerks to frame left"],
            "observable_expression": "pupils tightening, lips pressed tightly shut",
        },
        "dialogue_and_audio": {"has_dialogue": True, "speaker": "C-BIRD", "line_verbatim": "看不到？",
                               "audio_type": "offscreen", "voice_4d_spec_en": BIRD_VOICE},
    }
    for key, value in shot_overrides.items():
        if isinstance(value, dict) and isinstance(shot.get(key), dict):
            shot[key].update(value)
        else:
            shot[key] = value
    return {
        "project_id": "T", "scene_id": "S-ROCK", "segment_id": "EP01-S02-b",
        "metadata": {"aspect_ratio": "16:9", "target_duration_sec": 4.0},
        "style_lock": {"anchor": "3D donghua", "negative": "", "tail_freeze_hold": False},
        "asset_refs": {"scene_id": "S-ROCK", "characters": [{"id": "C-HERO"}], "no_visual_reference_ids": ["C-BIRD"]},
        "continuity_handshake": {"mode": "INDEPENDENT_REF2VA"},
        "overall_soundscape": "Wind over the ridge.",
        "shots": [shot],
    }


def _compile(data, **kw):
    return compiler.compile_segment_h3(copy.deepcopy(data), registry=_registry(), auto_lora=False, **kw)


class OffscreenH3CompilerTests(unittest.TestCase):
    def test_default_policy_is_short_offscreen_h3(self):
        self.assertEqual(compiler.DEFAULT_NARRATION_POLICY, "short-offscreen-h3")
        compiled = _compile(_segment({}))
        self.assertEqual(compiled["metadata"]["narration_policy"], "short-offscreen-h3")

    def test_short_os_line_goes_to_h3_with_voice_outside_d_and_face_lips_closed(self):
        prompt = _compile(_segment({}))["h3_prompt"]
        self.assertIn(f"the line is heard from the crimson bird (S2) off-screen, {BIRD_VOICE}: <d>[Chinese] 看不到？</d>"
                      f" while <Subject 1>'s lips remain completely closed", prompt)
        # 聲線描述在 <d> 外，<d> 內只有逐字台詞
        self.assertIn("<d>[Chinese] 看不到？</d>", prompt)
        self.assertNotIn("voiceover", prompt)

    def test_short_os_line_with_no_face_writes_no_lips_sentence(self):
        data = _segment({"character_ids": [], "dialogue_and_audio": {"lips_closed_lock": False}})
        prompt = _compile(data)["h3_prompt"]
        self.assertIn("<d>[Chinese] 看不到？</d>", prompt)
        self.assertNotIn("lips remain completely closed", prompt)

    def test_vo_with_no_face_writes_no_face_is_on_screen(self):
        data = _segment({
            "character_ids": [],
            "dialogue_and_audio": {"speaker": "C-HERO", "audio_type": "voiceover", "lips_closed_lock": False,
                                   "line_verbatim": "人生用這種方式結束，也算得上別緻。",
                                   "voice_4d_spec_en": "a calm, flat teenage male voice, quiet and wry"},
        })
        compiled = _compile(data)
        prompt = compiled["h3_prompt"]
        self.assertIn("says in an off-screen voiceover, a calm, flat teenage male voice, quiet and wry: "
                      "<d>[Chinese] 人生用這種方式結束，也算得上別緻。</d> while no face is on screen, "
                      "so all lips remain completely closed", prompt)
        self.assertEqual(compiled["external_narration"], [])
        # E23 仍滿足
        self.assertEqual([e for e in audit.audit_refs_and_subjects(compiled)["errors"] if "E23" in e], [])

    def test_long_line_goes_external_without_a_speaking_sentence(self):
        long_line = "這是一句很長很長的旁白，超過十五個字，不適合讓模型直接念出來。"
        data = _segment({"dialogue_and_audio": {"line_verbatim": long_line}})
        compiled = _compile(data)
        prompt = compiled["h3_prompt"]
        self.assertNotIn(long_line, prompt)
        self.assertEqual([e["line"] for e in compiled["external_narration"]], [long_line])
        self.assertNotIn("heard from", prompt)
        self.assertNotRegex(prompt, r"\(S\d+\) (speaks|narrates|says)")
        self.assertIn("lips completely closed", prompt)
        self.assertEqual([i["code"] for i in voice_lint.voice_issues(prompt)], [])

    def test_voice_route_override_wins_over_policy(self):
        forced_ext = _compile(_segment({"dialogue_and_audio": {"voice_route": "external"}}))
        self.assertEqual(len(forced_ext["external_narration"]), 1)
        long_line = "這是一句很長很長的旁白，超過十五個字，但這一段需要模型直接念。"
        forced_h3 = _compile(_segment({"dialogue_and_audio": {"voice_route": "h3", "line_verbatim": long_line}}),
                             narration_policy="external")
        self.assertIn(f"<d>[Chinese] {long_line}</d>", forced_h3["h3_prompt"])
        self.assertTrue(any("超過實測範圍" in n for n in forced_h3["compile_notes"]))

    def test_h3_native_keeps_long_lines_and_external_drops_short_ones(self):
        long_line = "這是一句很長很長的旁白，超過十五個字，不適合讓模型直接念出來。"
        native = _compile(_segment({"dialogue_and_audio": {"line_verbatim": long_line}}), narration_policy="h3-native")
        self.assertIn(f"<d>[Chinese] {long_line}</d>", native["h3_prompt"])
        external = _compile(_segment({}), narration_policy="external")
        self.assertNotIn("<d>", external["h3_prompt"])
        self.assertEqual(len(external["external_narration"]), 1)

    def test_unknown_policy_is_rejected(self):
        with self.assertRaises(ValueError):
            _compile(_segment({}), narration_policy="tts")

    def test_mouth_open_expression_on_os_shot_adds_a_compile_note(self):
        data = _segment({"action_and_performance": {"observable_expression": "eyes wide, mouth hanging open, gasping"}})
        compiled = _compile(data)
        self.assertTrue(any("#123" in n for n in compiled["compile_notes"]))
        codes = [i["code"] for i in voice_lint.voice_issues(compiled["h3_prompt"])]
        self.assertIn("E44", codes)

    def test_en_overlay_h3_voice_sets_route_voice_and_where(self):
        shot = {"dialogue_and_audio": {}}
        compiler._apply_en_shot(shot, {"h3_voice": {"form": "offscreen", "voice": BIRD_VOICE, "where": "from above the ridge"}})
        dlg = shot["dialogue_and_audio"]
        self.assertEqual(dlg["voice_route"], "h3")
        self.assertEqual(dlg["offscreen_voice_en"], BIRD_VOICE)
        self.assertEqual(dlg["offscreen_where_en"], "from above the ridge")
        data = _segment({"dialogue_and_audio": dict(dlg, line_verbatim="這是一句很長很長的旁白，超過十五個字，仍然留給模型。")})
        prompt = _compile(data, narration_policy="external")["h3_prompt"]
        self.assertIn("off-screen from above the ridge, " + BIRD_VOICE + ": <d>", prompt)

    def test_cli_default_is_short_offscreen_h3(self):
        src = (ROOT / "scripts" / "storyboard" / "compile_layer2_to_h3.py").read_text(encoding="utf-8")
        self.assertIn("default=DEFAULT_NARRATION_POLICY, choices=list(NARRATION_POLICIES)", src)


class VoiceLintTests(unittest.TestCase):
    HEAD = "subject_definitions:\n<Subject 1> is a boy.\n\ndetailed_description:\n"

    def _prompt(self, body):
        return self.HEAD + body + "\n\noverall_soundscape:\nWind.\n"

    def test_e41_speaking_verb_without_d(self):
        for body in (
            "[Shot 1] A CU of <Subject 1>. The guide (S1) speaks off-screen over this shot, and the shot carries only the location ambience.",
            "[Shot 1] A MS of <Subject 1>. First his head turns slightly as he speaks, then he looks down.",
            "[Shot 1] A MS of <Subject 1>. Then, as the line is heard, his shoulders rise.",
        ):
            with self.subTest(body=body[:40]):
                self.assertEqual([i["code"] for i in voice_lint.voice_issues(self._prompt(body))], ["E43"])

    def test_e41_ignores_rhetoric_negation_and_lines_with_d(self):
        for body in (
            "[Shot 1] A MS of <Subject 1>. The stance says everything; the notice speaks in a calm official hand.",
            "[Shot 1] A MS of <Subject 1>. He listens without speaking, and he says nothing more.",
            "[Shot 1] A CU of <Subject 1>. <Subject 1> (S1) is the visible speaking character, and says: <d>[Chinese] 走。</d>",
            "[Shot 1] A CU of <Subject 1>. The visible characters keep their lips completely closed and continue their actions, "
            "and the shot carries only the location ambience.",
        ):
            with self.subTest(body=body[:40]):
                self.assertEqual(voice_lint.voice_issues(self._prompt(body)), [])

    def test_e42_mouth_open_on_offscreen_shot(self):
        bad = ("[Shot 1] A CU of <Subject 1>. Expression: eyes wide, gasping. ; the line is heard from the bird (S2) off-screen, "
               "a deep voice: <d>[Chinese] 如你所願。</d> while <Subject 1>'s lips remain completely closed.")
        good = bad.replace("gasping", "lips pressed tightly shut")
        self.assertEqual([i["code"] for i in voice_lint.voice_issues(self._prompt(bad))], ["E44"])
        self.assertEqual(voice_lint.voice_issues(self._prompt(good)), [])

    def test_audit_warns_by_default_and_errors_in_strict(self):
        seg = {"segment_id": "X", "reference_images": [],
               "h3_prompt": self._prompt("[Shot 1] A MS. First his head turns as he speaks, then he looks down.")}
        loose = audit.audit_refs_and_subjects(seg)
        strict = audit.audit_refs_and_subjects(seg, strict=True)
        self.assertFalse(any("E43" in e for e in loose["errors"]))
        self.assertTrue(any("E43" in w for w in loose["warnings"]))
        self.assertTrue(any("E43" in e for e in strict["errors"]))

    def test_project_state_only_gates_stage5_in_strict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "images").mkdir()
            (root / "images" / "scene.png").write_bytes(b"x")
            seg = {"segment_id": "EP01-S01", "reference_images": [{"path": "images/scene.png", "type": "scene"}],
                   "h3_prompt": self._prompt("[Shot 1] A MS. First his head turns as he speaks, then he looks down.")}
            (root / "segments-ep01.json").write_text(json.dumps({"segments": [seg]}), encoding="utf-8")
            self.assertEqual(ps.stage_validation_errors(root, 5), [])
            errors = ps.stage_validation_errors(root, 5, strict=True)
            self.assertEqual(len(errors), 1)
            self.assertIn("E43", errors[0])


if __name__ == "__main__":
    unittest.main()
