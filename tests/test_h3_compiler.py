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

    def compile(self, data=None):
        return compiler.compile_segment_h3(
            copy.deepcopy(data or self.segment()),
            registry=self.registry,
            auto_lora=False,
        )

    def test_anime_and_ink_style_and_continuity_are_preserved(self):
        for anchor in (
            "2D anime, cobalt shadows, hand-drawn linework",
            "ink-wash illustration with dry-brush stone texture",
        ):
            with self.subTest(anchor=anchor):
                data = self.segment()
                data["style_lock"]["anchor"] = anchor
                prompt = self.compile(data)["h3_prompt"]
                for authored_value in (
                    anchor,
                    data["style_lock"]["negative"],
                    "moonlight from camera left",
                    "Mira remains east of the table",
                    "the table stays between Mira and the door",
                    "rough ink wash on the stone wall",
                ):
                    self.assertIn(authored_value, prompt)
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
            layer.write_text(json.dumps(self.segment(), ensure_ascii=False), encoding="utf-8")
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
        self.assertEqual(compiled["metadata"]["style_lock"], data["style_lock"])
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
