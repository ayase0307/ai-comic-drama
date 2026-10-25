import copy
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts.storyboard import verify_video_shot as qa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))

import compile_layer2_to_h3 as compiler


class H3CompilerRegressionTests(unittest.TestCase):
    def setUp(self):
        self.registry = compiler.AssetRegistry()
        self.registry.locations["S-ROOM"] = {
            "id": "S-ROOM",
            "name": "Room",
            "desc_en": "a quiet room with a west-facing window",
            "desc_zh": "安靜房間",
            "ref_img": "assets/scenes/room.png",
            "lighting": "blue moonlight",
        }
        self.registry.characters["C-MIRA"] = {
            "id": "C-MIRA",
            "name": "Mira",
            "desc_en": "Mira, short black hair, gray coat",
            "desc_zh": "Mira，短黑髮，灰色外套",
            "ref_img": "assets/characters/mira.png",
            "wardrobe_states": {},
            "is_creature": False,
        }

    def segment(self):
        return {
            "project_id": "TEST",
            "scene_id": "S-ROOM",
            "segment_id": "EP01-S01-seg01",
            "metadata": {
                "aspect_ratio": "16:9",
                "target_duration_sec": 9.0,
                "pacing_profile": "Standard_Narrative",
                "lighting_lock_line": "Blue moonlight through the west window.",
            },
            "style_lock": {
                "anchor": "2D ink-wash anime, cobalt shadows, hand-drawn linework",
                "negative": "No photorealism, no live-action skin texture",
                "lighting_lock_line": "Blue moonlight through the west window.",
                "continuity_anchors": {
                    "lighting": "moonlight from camera left",
                    "axis": "Mira remains east of the table",
                    "blocking": "the table stays between Mira and the door",
                    "texture": "rough ink wash on the stone wall",
                },
                "tail_freeze_hold": True,
            },
            "asset_refs": {
                "scene_id": "S-ROOM",
                "characters": [{"id": "C-MIRA"}],
            },
            "continuity_handshake": {"mode": "INDEPENDENT_REF2VA"},
            "overall_soundscape": "Rain ticks against the west window; Mira exhales once.",
            "non_diegetic_music": "No music; leave the scene quiet.",
            "segment_end_state": {
                "planned_final_state": {
                    "Mira": "holds the sealed letter in her left hand",
                    "door": "remains closed",
                },
                "observed_final_state": None,
            },
            "shots": [
                self.shot("S1", 0.0, 3.0, "Mira folds the map and sets it on the table."),
                self.shot("S2", 3.0, 6.0, "Mira notices the sealed letter."),
                self.shot("S3", 6.0, 9.0, "Mira holds still and listens."),
            ],
        }

    FIVE_PART = [
        {
            "camera": "50mm from two metres at her standing eye height, locked off for 3.0 s with Mira on the right third line.",
            "motion": "First her fingers crease the map along its old fold, then she presses the fold flat with the heel of her hand, as the paper slides a finger's width across the wood, finally she sets it square against the table edge.",
            "performance": "Her lips press together while she smooths the crease, and her eyes flick once toward the door before returning to the map.",
            "light": "Blue moonlight from the west window rakes across the paper, catching the raised fold and the ink lines on its back.",
            "sound": "Paper crackles at about 0.6 s and the map taps the wood at about 2.4 s; rain keeps ticking on the glass.",
        },
        {
            "camera": "50mm from two metres, same eye height, locked off for 3.0 s; the sealed letter sits in the lower left third.",
            "motion": "First her gaze drops to the corner of the table, then her right hand stops halfway to the lamp, as she leans her weight onto her left palm, finally her fingertips slide the sealed letter out from under the map.",
            "performance": "Her brows lift a fraction and her breath catches once; the corner of her mouth tightens as she recognises the red wax seal.",
            "light": "The moonlight lands on the red wax seal so it glints darker than the paper; her knuckles stay in cool shadow.",
            "sound": "A short intake of breath at about 0.9 s; the envelope rasps against the map at about 2.1 s under the rain.",
        },
        {
            "camera": "50mm from two metres at her eye height, locked off for 3.0 s with her head turned toward frame left.",
            "motion": "First her chin turns toward the door, then her left hand closes around the letter and draws it against her ribs, as her weight shifts back onto her heels, finally she holds her breath with the letter pressed flat.",
            "performance": "Her eyes widen and stay on the door; her shoulders rise and do not drop while she listens for a step outside.",
            "light": "Moonlight outlines the side of her face and the edge of the letter; the door behind the table falls into deep cobalt shadow.",
            "sound": "The rain thins at about 1.0 s, a floorboard creaks somewhere beyond the door at about 2.2 s, and she does not answer.",
        },
    ]

    def five_part_segment(self):
        data = self.segment()
        for shot, five in zip(data["shots"], self.FIVE_PART):
            shot["action_and_performance"]["five_part_en"] = dict(five)
        return data

    @staticmethod
    def shot(shot_id, start, end, action, movement="static", line=None, foley=""):
        return {
            "shot_id": shot_id,
            "start_time": start,
            "end_time": end,
            "duration": end - start,
            "camera_optics": {
                "shot_size": "MS",
                "focal_length": "50mm",
                "physical_distance": "2m",
                "pov_routing": "objective",
                "movement": movement,
            },
            "spatial_blocking": {
                "anchor_objects": ["table", "west window"],
                "blocking_desc": "Mira stands east of the table.",
            },
            "action_and_performance": {
                "action_stages": [action],
                "observable_expression": "Mira's eyes narrow, then relax.",
                "background_idle_life": "",
                "micro_physics_tail": "",
            },
            "dialogue_and_audio": {
                "has_dialogue": line is not None,
                "speaker": "C-MIRA" if line is not None else "",
                "line_verbatim": line,
                "lips_closed_lock": line is None,
                "foley_and_ambience": foley,
            },
        }

    def compile(self, data=None, **kwargs):
        return compiler.compile_segment_h3(
            copy.deepcopy(data or self.segment()),
            registry=self.registry,
            auto_lora=False,
            **kwargs,
        )

    def test_legacy_characters_field_is_normalized_before_compile(self):
        data = self.segment()
        legacy = data["shots"][0].pop("character_ids", ["C-MIRA"])
        data["shots"][0]["characters"] = legacy
        compiled = self.compile(data)
        notes = " ".join(compiled.get("compile_notes") or [])
        self.assertIn("[normalize]", notes)

    def test_missing_timeline_is_rejected_with_clear_error(self):
        data = self.segment()
        for key in ("start_time", "end_time", "duration"):
            data["shots"][0].pop(key, None)
        with self.assertRaises(ValueError) as ctx:
            self.compile(data)
        self.assertIn("正規化失敗", str(ctx.exception))

    def test_cut_marker_tokens_are_opt_in(self):
        plain = self.compile()
        self.assertNotIn("<cutoff>", plain["h3_prompt"])
        self.assertFalse(plain["metadata"]["cut_marker_tokens"]["embedded"])

        data = self.segment()
        for shot in data["shots"]:
            shot["scene_id"] = "SC01"
        data["shots"][-1]["scene_id"] = "SC02"
        marked = compiler.compile_segment_h3(copy.deepcopy(data), registry=self.registry,
                                             auto_lora=False, embed_cut_markers=True)
        self.assertIn("<cutoff>", marked["h3_prompt"])
        self.assertIn("<scenetrans>", marked["h3_prompt"])
        self.assertTrue(marked["metadata"]["cut_marker_tokens"]["embedded"])

    def test_cut_markers_are_structured_metadata(self):
        compiled = self.compile()
        metadata = compiled["metadata"]
        shots = compiled["shots"]
        markers = metadata["cut_markers"]
        self.assertEqual(len(markers), len(shots) - 1)
        self.assertEqual(markers[0]["shot_id"], shots[1]["shot_id"])
        self.assertAlmostEqual(markers[0]["at_seconds"], float(shots[1]["start_time"]), places=3)
        # 切點標記只放 metadata，不進提示詞（避免官方 lint 把它當非法 token）
        self.assertNotIn("[cut]", compiled["h3_prompt"])

    def test_compiled_metadata_carries_frame_quantum(self):
        """編譯器必須寫出可被送件端讀回的 17n+5 影格數（2026-10-19 時長漂移防線）。"""
        compiled = self.compile()
        metadata = compiled["metadata"]
        self.assertIn("frames", metadata)
        frames = metadata["frames"]
        self.assertIsInstance(frames, int)
        self.assertEqual((frames - 5) % 17, 0, f"{frames} 不是 17n+5")
        self.assertAlmostEqual(metadata["effective_duration_sec"],
                               round(frames / 24.0, 3), places=3)
        self.assertIn("17n+5", metadata["frame_spec"])

    def test_dialogue_segments_use_ceil_frames(self):
        data = self.segment()
        data["shots"] = [self.shot("D1", 0, 9, "Mira raises one hand.", line="先別退，聽我說！")]
        metadata = self.compile(data)["metadata"]
        self.assertEqual(metadata["rounding_mode"], "ceil")
        self.assertEqual(metadata["frames"], 226)  # 9.0s 含台詞 → 13 steps × 17 + 5
        self.assertEqual((metadata["frames"] - 5) % 17, 0)

    def test_anime_and_ink_style_and_continuity_are_preserved(self):
        for anchor in (
            "2D anime, cobalt shadows, hand-drawn linework",
            "ink-wash illustration with dry-brush stone texture",
        ):
            with self.subTest(anchor=anchor):
                data = self.segment()
                data["style_lock"]["anchor"] = anchor
                compiled = self.compile(data)
                prompt = compiled["h3_prompt"]
                for authored_value in (
                    anchor,
                    "moonlight from camera left",
                    "Mira remains east of the table",
                    "the table stays between Mira and the door",
                    "rough ink wash on the stone wall",
                ):
                    self.assertIn(authored_value, prompt)
                self.assertEqual(compiled["metadata"]["qa_exclusions"], data["style_lock"]["negative"])
                self.assertNotIn(data["style_lock"]["negative"], prompt)
                self.assertNotIn("The target video is live-action cinematic", prompt)
                self.assertNotIn("The target video is live-action", prompt)

    def test_ref2va_scene_reference_is_not_declared_as_a_locked_first_frame(self):
        prompt = self.compile()["h3_prompt"]
        self.assertIn("[reference generation]", prompt)
        self.assertIn("scene/style reference", prompt.lower())
        self.assertNotIn("first frame", prompt.lower())
        self.assertNotIn("begins from <Picture 1>", prompt)

    def test_three_by_three_fixture_remains_accepted_by_official_lint(self):
        compiled = self.compile()
        result = compiler.lint_h3_prompt(
            compiled["h3_prompt"],
            nominal_duration=compiler.effective_duration(9.0),
        )
        self.assertTrue(result["passed"], result["errors"])

    def test_cli_check_passes_for_compliant_three_by_three_ref2va_segment(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            layer = root / "layer2.json"
            layer.write_text(json.dumps(self.five_part_segment(), ensure_ascii=False), encoding="utf-8")
            argv = [
                "compile_layer2_to_h3.py", "--layer2", str(layer), "--skip-stage-gate",
                "--project-root", str(root), "--output-md", str(root / "prompts.md"),
                "--output-segments", str(root / "segments.json"), "--check", "--no-auto-lora",
            ]
            output = StringIO()
            with patch.object(sys, "argv", argv), redirect_stdout(output), redirect_stderr(output):
                status = compiler.main()
            self.assertEqual(status, 0, output.getvalue())

    def test_noncombat_scene_gets_no_invented_defensive_or_fight_action(self):
        prompt = self.compile()["h3_prompt"]
        self.assertIn("Mira folds the map and sets it on the table.", prompt)
        self.assertIn("Mira's eyes narrow, then relax.", prompt)
        self.assertNotIn("defensive posture", prompt)
        self.assertNotIn("physical kinetic energy propagates", prompt)
        self.assertNotIn("choreographed actions", prompt)

    def test_missing_performance_authorship_does_not_add_generic_or_fight_action(self):
        data = self.segment()
        data["shots"][0]["action_and_performance"]["action_stages"] = []
        data["shots"][0]["action_and_performance"]["observable_expression"] = ""
        try:
            prompt = self.compile(data)["h3_prompt"]
        except ValueError as exc:
            self.assertRegex(str(exc), "action|performance|表演|動作")
        else:
            self.assertNotIn("deliberate physical blocking", prompt)
            self.assertNotIn("defensive posture", prompt)

    def test_missing_sound_authoring_does_not_insert_generic_foley_or_music(self):
        data = self.segment()
        data.pop("overall_soundscape")
        data.pop("non_diegetic_music")
        for shot in data["shots"]:
            shot["dialogue_and_audio"]["foley_and_ambience"] = ""
        try:
            prompt = self.compile(data)["h3_prompt"]
        except ValueError as exc:
            self.assertRegex(str(exc), "sound|music|audio|聲音|配樂")
        else:
            self.assertNotIn("Atmospheric ambient environmental room tone", prompt)
            self.assertNotIn("Low atmospheric cinematic score", prompt)

    def test_fight_action_and_segment_end_state_are_preserved_without_added_beats(self):
        data = self.segment()
        action = "Mira drives the spear into the stone floor, then braces against the recoil."
        data["shots"][0] = self.shot("F1", 0, 3, action)
        compiled = self.compile(data)
        self.assertIn(action, compiled["h3_prompt"])
        self.assertEqual(compiled.get("segment_end_state"), data["segment_end_state"])
        self.assertNotIn("maintains a steady defensive posture", compiled["h3_prompt"])
        self.assertIn("holds the sealed letter in her left hand", compiled["h3_prompt"])

    def test_authored_palette_and_spatial_blocking_are_carried_forward(self):
        data = self.segment()
        data["metadata"]["palette_preset"] = "indigo and muted ochre"
        prompt = self.compile(data)["h3_prompt"]
        self.assertIn("indigo and muted ochre", prompt)
        self.assertIn("Mira stands east of the table.", prompt)
        self.assertIn("anchor objects: table, west window", prompt)

    def test_missing_lighting_does_not_invent_sunlight_and_metadata_reaches_qa(self):
        data = self.segment()
        data["metadata"].pop("lighting_lock_line")
        data["style_lock"].pop("lighting_lock_line")
        data["style_lock"]["anchor"] = "black-and-white ink illustration"
        data["metadata"]["palette_preset"] = "monochrome"
        data["metadata"]["audio_required"] = False
        data["metadata"]["requires_audio"] = False
        compiled = self.compile(data)
        self.assertNotIn("sunlight", compiled["h3_prompt"].lower())
        expected_style = dict(data["style_lock"], negative="")
        self.assertEqual(compiled["metadata"]["style_lock"], expected_style)
        self.assertEqual(compiled["metadata"]["qa_exclusions"], data["style_lock"]["negative"])
        self.assertEqual(compiled["metadata"]["palette_preset"], "monochrome")
        self.assertIs(compiled["metadata"]["audio_required"], False)
        self.assertIs(compiled["metadata"]["requires_audio"], False)

        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            video = Path(directory) / "shot.mp4"
            video.write_bytes(b"test video placeholder")
            specs = {
                "duration": 3.0, "width": 640, "height": 360, "fps": 24.0,
                "aspect_ratio_val": 16 / 9, "video_codec": "h264", "has_audio": False,
                "audio_codec": None, "file_size": video.stat().st_size,
            }
            with patch.object(qa, "probe_video_specs", return_value=specs), \
                 patch.object(qa, "extract_frame_rgb", return_value=bytes([0, 0, 0]) * 360 * 202), \
                 patch.object(qa, "compute_frame_chroma", return_value=0.0), \
                 patch.object(qa, "check_grid_split_screen", return_value=(False, [])), \
                 patch.object(qa, "extract_palette", return_value=[]), \
                 patch.object(qa, "to_lab", return_value=(0, 0, 0)), \
                 patch.object(qa, "generate_contact_sheet", return_value=False):
                result = qa.verify_single_shot(compiled["shots"][0], video, compiled["metadata"])
        self.assertNotIn("STYLE_BLEED_GRAYSCALE", " ".join(result["issues"]))
        self.assertFalse(result["audio_check"]["required"])
        self.assertTrue(result["audio_check"]["ok"])

    def test_authored_soundscape_and_music_are_not_replaced_by_defaults(self):
        data = self.segment()
        data["overall_soundscape"] = "A kettle clicks off; no other room tone."
        data["non_diegetic_music"] = "Single low piano note, then silence."
        prompt = self.compile(data)["h3_prompt"]
        self.assertIn(data["overall_soundscape"], prompt)
        self.assertIn(data["non_diegetic_music"], prompt)
        self.assertNotIn("Atmospheric ambient environmental room tone", prompt)
        self.assertNotIn("matching the tension of the scene", prompt)

    def test_mute_scene_keeps_explicit_silence_and_has_no_dialogue(self):
        data = self.segment()
        data["overall_soundscape"] = "Silence: no dialogue, ambience, foley, or effects."
        data["non_diegetic_music"] = "No music."
        data["shots"][0] = self.shot("M1", 0, 3, "Mira waits without moving.")
        prompt = self.compile(data)["h3_prompt"]
        self.assertIn("Silence: no dialogue, ambience, foley, or effects.", prompt)
        self.assertIn("No music.", prompt)
        self.assertNotIn("<d>", prompt)
        self.assertNotIn("subtle clothing rustle and footsteps", prompt)

    def test_dialogue_is_preserved_verbatim(self):
        data = self.segment()
        line = "先別退，聽我說！"
        data["shots"][0] = self.shot("D1", 0, 3, "Mira raises one hand.", line=line)
        self.assertIn(f"<d>[Chinese] {line}</d>", self.compile(data)["h3_prompt"])

    def test_dialogue_keeps_speaker_identity_and_exact_segment_window(self):
        data = self.segment()
        shot = self.shot("D1", 0, 9, "Mira raises one hand.", line="先別退，聽我說！")
        shot["character_ids"] = ["C-MIRA"]
        shot["dialogue_and_audio"]["speech_window"] = {
            "start": 1.25,
            "end": 2.5,
            "unit": "segment_seconds",
        }
        data["shots"] = [shot]

        prompt = self.compile(data)["h3_prompt"]

        # 官方 base §4.4：說話人要用穩定 (Sx) 代號綁定；對應得到 Subject 時寫 <Subject N> (Sx)
        self.assertIn("<Subject 1> (S1)", prompt)
        self.assertIn("segment_seconds 1.250–2.500", prompt)
        self.assertIn("<d>[Chinese] 先別退，聽我說！</d>", prompt)

    def test_listener_offscreen_does_not_hide_visible_speaker(self):
        # "looking at {C-x} off-screen" places the LISTENER outside the frame; the speaker's mouth is visible.
        data = self.segment()
        action = "First she says the line while looking toward frame right at {C-wang-ju} off-screen"
        shot = self.shot("L1", 0, 9, action, line="小橘，丹翠交給妳。")
        shot["character_ids"] = ["C-MIRA"]
        shot["dialogue_and_audio"].update({"speaker": "C-MIRA", "lips_closed_lock": False})
        shot["action_and_performance"]["action_stages_en"] = [action]
        shot["action_and_performance"]["observable_expression_en"] = "Her mouth is clearly visible while she speaks."
        data["shots"] = [shot]
        compiled = self.compile(data)
        self.assertIn("is the visible speaking character", compiled["h3_prompt"])
        self.assertNotIn("off-screen: <d>", compiled["h3_prompt"])
        self.assertEqual(compiled["external_narration"], [])

    def test_offscreen_and_inner_voice_dialogue_never_becomes_visible_speech(self):
        cases = [
            ("C-guide", ["C-MIRA", "C-guide"], "The offscreen guide asks from beyond frame; only a hand is visible.", "C-guide"),
            ("C-doctor", ["C-MIRA"], "The doctor remains offscreen and never appears; no speaking mouth is visible.", "the doctor"),
            ("E-unknown-voice", ["C-MIRA"], "An unseen inner voice speaks; no source or mouth is visible.", "the unseen inner voice"),
        ]
        for speaker, character_ids, action, identity in cases:
            with self.subTest(speaker=speaker):
                data = self.segment()
                shot = self.shot("V1", 0, 9, action, line="你聽得見嗎？")
                shot["character_ids"] = character_ids
                shot["dialogue_and_audio"].update({
                    "speaker": speaker,
                    "lips_closed_lock": True,
                    "voice_4d_spec": "近距腦內聲，無可見聲源嘴部。" if speaker == "E-unknown-voice" else "",
                    "speech_window": {"start": 0.5, "end": 2.0, "unit": "segment_seconds"},
                })
                shot["action_and_performance"]["action_stages_en"] = [action]
                shot["action_and_performance"]["observable_expression_en"] = "Mira keeps her lips closed."
                data["shots"] = [shot]

                # 預設 short-offscreen-h3：短畫外句留 H3，用官方畫外句式＋逐字 <d>（#104 #114）
                compiled = self.compile(data)
                prompt = compiled["h3_prompt"]
                # 官方 base §4.4：發聲者一定要有穩定 (Sx) 代號
                # #66：Subject 1（Mira）佔 S1，畫外發聲者接在後面
                self.assertRegex(prompt, r"\(S[12]\)")
                self.assertIn(identity, prompt)
                self.assertIn("segment_seconds 0.500–2.000", prompt)
                self.assertNotIn(f"{speaker} speaks", prompt)
                self.assertNotIn("<Subject 1> speaks", prompt)
                self.assertNotIn("is the visible speaking character", prompt)
                self.assertIn("<d>[Chinese] 你聽得見嗎？</d>", prompt)
                self.assertRegex(prompt, r"(heard from .* off-screen|says in an off-screen voiceover)")
                self.assertIn("lips remain completely closed", prompt)
                self.assertEqual(compiled["external_narration"], [])

                # external：整句外部 TTS；提示詞不得寫「有人說話卻不給字」（#122）
                compiled = self.compile(data, narration_policy="external")
                prompt = compiled["h3_prompt"]
                self.assertIn("segment_seconds 0.500–2.000", prompt)
                self.assertNotIn("<d>[Chinese] 你聽得見嗎？</d>", prompt)
                # 編譯器自己不得產生說話句（分鏡原文的動作句另由 audit E26 抓）
                self.assertNotRegex(prompt, r"\(S\d+\) (speaks|narrates|says)")
                self.assertNotIn("off-screen over this shot", prompt)
                self.assertEqual(len(compiled["external_narration"]), 1)
                self.assertEqual(compiled["external_narration"][0]["line"], "你聽得見嗎？")
                self.assertIn("lips completely closed", prompt)

    def test_visible_back_only_speaker_respects_lip_closed_lock(self):
        data = self.segment()
        shot = self.shot("B1", 0, 9, "The driver stays turned away; the line is heard.", line="先送你回去。")
        shot["character_ids"] = ["C-MIRA", "C-DRIVER"]
        shot["dialogue_and_audio"].update({
            "speaker": "C-DRIVER",
            "lips_closed_lock": True,
            "speech_window": {"start": 0.5, "end": 2.0, "unit": "segment_seconds"},
        })
        shot["composition_start"] = "The driver is visible only from behind; the mouth is out of view."
        shot["action_and_performance"]["action_stages_en"] = ["The driver stays in a back view while speaking from offscreen."]
        data["shots"] = [shot]

        compiled = self.compile(data, narration_policy="external")
        prompt = compiled["h3_prompt"]

        # 背影說話沒有可見的嘴 → external 政策整句改由外部 TTS，H3 不生成人聲，也不提有人說話
        self.assertNotRegex(prompt, r"\b(speaks|narrates|says)\b")
        self.assertIn("lips completely closed", prompt)
        self.assertIn("segment_seconds 0.500–2.000", prompt)
        self.assertNotIn("<d>[Chinese] 先送你回去。</d>", prompt)
        self.assertEqual(len(compiled["external_narration"]), 1)
        self.assertEqual(compiled["external_narration"][0]["line"], "先送你回去。")

    def test_null_speaker_is_valid_for_a_nondialogue_shot(self):
        data = self.segment()
        data["shots"][0]["dialogue_and_audio"]["speaker"] = None
        self.assertIn("Mira folds the map", self.compile(data)["h3_prompt"])

    def test_source_cut_points_are_kept_and_only_final_shot_is_quantized(self):
        data = self.segment()
        data["metadata"]["target_duration_sec"] = 15.0
        data["shots"] = [
            self.shot("S1", 0, 5, "Mira opens the letter."),
            self.shot("S2", 5, 10, "Mira reads the first line."),
            self.shot("S3", 10, 15, "Mira lowers the letter."),
        ]
        compiled = self.compile(data)
        self.assertEqual([s["start_time"] for s in compiled["shots"]], [0, 5, 10])
        self.assertEqual([s["end_time"] for s in compiled["shots"]], [5, 10, 14.375])
        self.assertEqual([s["duration"] for s in compiled["shots"]], [5, 5, 4.375])
        self.assertIn("At 00:05.000", compiled["h3_prompt"])
        self.assertIn("At 00:10.000", compiled["h3_prompt"])
        self.assertIn("14.375s effective from 15.000s target", compiled["h3_prompt"])
        self.assertEqual(compiled["metadata"]["effective_duration_sec"], 14.375)

    def test_floor_quantization_ceil_protects_speech_window_that_reaches_target(self):
        data = self.segment()
        data["metadata"]["target_duration_sec"] = 10.0
        shot = self.shot("D1", 0.0, 10.0, "Mira raises one hand.", line="Stay right here.")
        shot["dialogue_and_audio"]["speech_window"] = {
            "start": 7.5,
            "end": 10.0,
            "unit": "segment_seconds",
        }
        data["shots"] = [shot]

        compiled = self.compile(data)

        self.assertAlmostEqual(compiler.effective_duration(10.0, "floor"), 9.417, places=3)
        self.assertEqual(compiled["metadata"]["rounding_mode"], "ceil")
        self.assertEqual(compiled["metadata"]["rounding_reason"], "dialogue-preserving")
        self.assertEqual(compiled["metadata"]["effective_duration_sec"], 10.125)
        self.assertEqual(compiled["shots"][0]["duration"], 10.125)
        lint = compiler.lint_h3_prompt(
            compiled["h3_prompt"],
            nominal_duration=10.0,
            rounding_mode=compiled["metadata"]["rounding_mode"],
            authored_shots=compiled["shots"],
        )
        self.assertTrue(lint["passed"], lint["errors"])
        self.assertNotIn("The final second holds still before the cut.", compiled["h3_prompt"])

    def test_any_dialogue_segment_uses_ceil_to_preserve_authored_pauses(self):
        data = self.segment()
        data["metadata"]["target_duration_sec"] = 10.0
        shot = self.shot("D1", 0.0, 10.0, "Mira raises one hand.", line="Stay right here.")
        shot["dialogue_and_audio"]["speech_window"] = {
            "start": 5.0,
            "end": 9.0,
            "unit": "segment_seconds",
        }
        data["shots"] = [shot]

        compiled = self.compile(data)

        self.assertEqual(compiled["metadata"]["rounding_mode"], "ceil")
        self.assertEqual(compiled["metadata"]["rounding_reason"], "dialogue-preserving")
        self.assertEqual(compiled["metadata"]["effective_duration_sec"], 10.125)

    def test_no_dialogue_overrun_keeps_floor_quantization(self):
        data = self.segment()
        data["metadata"]["target_duration_sec"] = 10.0
        data["shots"] = [self.shot("S1", 0.0, 10.0, "Mira waits by the table.")]

        compiled = self.compile(data)

        self.assertEqual(compiled["metadata"]["rounding_mode"], "floor")
        self.assertAlmostEqual(compiled["metadata"]["effective_duration_sec"], 9.417, places=3)
        self.assertAlmostEqual(compiled["shots"][0]["duration"], 9.417, places=3)

    def test_overlapping_and_gapped_source_timelines_are_rejected(self):
        for label, second_start in (("overlap", 2.5), ("gap", 3.5)):
            with self.subTest(label=label):
                data = self.segment()
                data["shots"][1]["start_time"] = second_start
                data["shots"][1]["duration"] = data["shots"][1]["end_time"] - second_start
                with self.assertRaisesRegex(ValueError, "timeline|時間|shot"):
                    self.compile(data)

    def test_unknown_camera_motion_is_explicitly_static_or_rejected(self):
        data = self.segment()
        data["shots"][0] = self.shot("U1", 0, 3, "Mira waits.", movement="mystery-crane-spiral")
        try:
            prompt = self.compile(data)["h3_prompt"]
        except ValueError as exc:
            self.assertRegex(str(exc), "movement|camera|運鏡")
        else:
            self.assertIn("static", prompt.lower())
            self.assertNotIn("trucking left", prompt.lower())
            self.assertNotIn("dollies in", prompt.lower())

    def test_repeated_static_multishot_does_not_add_camera_filler(self):
        prompt = self.compile()["h3_prompt"]
        self.assertNotIn("with steady optical focus", prompt)

    def test_short_multishot_that_cannot_fit_h3_cut_bounds_is_rejected(self):
        data = self.segment()
        data["metadata"]["target_duration_sec"] = 3.0
        data["shots"] = [
            self.shot("Q1", 0, 1.5, "Mira turns."),
            self.shot("Q2", 1.5, 3.0, "Mira stops."),
        ]
        with self.assertRaisesRegex(ValueError, "duration|切點|timeline|時間"):
            self.compile(data)

    def test_source_shot_total_must_match_declared_segment_before_quantization(self):
        data = self.segment()
        data["shots"][2]["end_time"] = 8.0
        data["shots"][2]["duration"] = 2.0
        with self.assertRaisesRegex(ValueError, "duration|target|segment|時間"):
            self.compile(data)


if __name__ == "__main__":
    unittest.main()


class ExtrasAssetRegistryTest(unittest.TestCase):
    def test_extras_card_is_a_group_not_a_face(self):
        import compile_layer2_to_h3 as c
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "assets.md"
            p.write_text("## 角色\n\n### EXTRAS-crowd　弟子群（群演）\n"
                         "- **固定描述片段**：`seated disciples`\n- **設定圖**：`images/extras-crowd.png`\n",
                         encoding="utf-8")
            reg = c.AssetRegistry(assets_path=p, project_root=d)
            rec = reg.get_character("EXTRAS-crowd")
            self.assertTrue(rec["is_group"])
            self.assertEqual(rec["ref_img"], "images/extras-crowd.png")
