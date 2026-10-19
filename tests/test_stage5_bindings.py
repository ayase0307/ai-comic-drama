import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))

import compile_layer2_to_h3 as compiler


class Stage5BindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.layer_path = self.root / "layer2" / "layer2-EP03-S01.json"
        self.layer_path.parent.mkdir()
        self.layer = self._layer()
        self.layer_path.write_text(json.dumps(self.layer, ensure_ascii=False), encoding="utf-8")
        self.sha = hashlib.sha256(self.layer_path.read_bytes()).hexdigest()
        self.binding = {
            "segment_id": "EP03-S01",
            "source_layer2_path": "layer2/layer2-EP03-S01.json",
            "source_sha256": self.sha,
            "scene_id": "S-HALL",
            "scene_description_en": "a narrow school back alley beside an intact wall",
            "primary_character": "C-HERO",
            "asset_refs_override": {
                "characters": [{"id": "C-HERO", "costume_id": "W-01"}],
                "creatures": [{"id": "E-SNAKE", "variant": "adult"}],
                "props": [{"id": "P-SPEAR"}],
                "bodydetails": [{"id": "D-SCAR"}],
                "no_visual_reference_ids": ["C-VOICE"],
            },
            "shot_overrides": {
                "EP03-SH001": {
                    "action_stages_en": ["The hero raises the spear."]
                }
            },
            "shots": [{
                "global_shot_id": "EP03-SH001",
                "reference_paths": {
                    "scene": "images/S-HALL.png",
                    "characters": {"C-HERO": "images/C-HERO.png"},
                    "creatures": {"E-SNAKE": "images/E-SNAKE.png"},
                    "props": {"P-SPEAR": "images/P-SPEAR.png"},
                    "bodydetails": {"D-SCAR": "images/D-SCAR.png"},
                },
                "visual_subject_ids": ["C-HERO", "E-SNAKE"],
                "no_visual_reference_ids": ["C-VOICE"],
            }, {
                "global_shot_id": "EP03-SH002", "reference_paths": {},
                "visual_subject_ids": ["C-HERO"], "no_visual_reference_ids": [],
            }, {
                "global_shot_id": "EP03-SH003", "reference_paths": {},
                "visual_subject_ids": ["C-HERO"], "no_visual_reference_ids": [],
            }],
        }
        for rel in ("images/S-HALL.png", "images/C-HERO.png", "images/E-SNAKE.png", "images/P-SPEAR.png", "images/D-SCAR.png"):
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"fixture-reference")

    @staticmethod
    def _layer():
        return {
            "segment_id": "EP03-S01", "scene_id": "S-OLD", "metadata": {
                "target_duration_sec": 9, "aspect_ratio": "16:9",
            },
            "style_lock": {"anchor": "approved style"},
            "asset_refs": {"scene_id": "S-OLD", "characters": [{"id": "C-VOICE"}]},
            "shots": [{
                "global_shot_id": "EP03-SH001", "shot_id": "SH01",
                "start_time": 0, "end_time": 3, "duration": 3,
                "character_ids": ["C-HERO", "E-SNAKE", "C-VOICE"],
                "camera_optics": {"shot_size": "MS", "movement": "static"},
                "action_and_performance": {
                    "action_stages": ["原始中文動作"], "action_stages_en": ["Original rough translation"],
                    "observable_expression": "原始表情", "observable_expression_en": "Original expression",
                },
                "dialogue_and_audio": {"has_dialogue": False},
                "spatial_blocking": {"blocking_desc": "洛年在走廊北側。", "anchor_objects": []},
            }, {
                "global_shot_id": "EP03-SH002", "shot_id": "SH02",
                "start_time": 3, "end_time": 6, "duration": 3,
                "character_ids": ["C-HERO"], "camera_optics": {"shot_size": "MS", "movement": "static"},
                "action_and_performance": {"action_stages": ["離開"], "action_stages_en": ["He leaves."], "observable_expression_en": "Calm."},
                "dialogue_and_audio": {"has_dialogue": False}, "spatial_blocking": {},
            }, {
                "global_shot_id": "EP03-SH003", "shot_id": "SH03",
                "start_time": 6, "end_time": 9, "duration": 3,
                "character_ids": ["C-HERO"], "camera_optics": {"shot_size": "MS", "movement": "static"},
                "action_and_performance": {"action_stages": ["停下"], "action_stages_en": ["He stops."], "observable_expression_en": "Still."},
                "dialogue_and_audio": {"has_dialogue": False}, "spatial_blocking": {},
            }],
        }

    def test_binding_source_hash_and_layer_path_are_verified_before_overlay(self):
        result = compiler.validate_stage5_binding(
            self.layer, self.binding, self.layer_path, self.root,
        )
        self.assertEqual(result["segment_id"], "EP03-S01")
        bad = copy.deepcopy(self.binding)
        bad["source_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA256"):
            compiler.validate_stage5_binding(self.layer, bad, self.layer_path, self.root)
        bad = copy.deepcopy(self.binding)
        bad["source_layer2_path"] = "other.json"
        with self.assertRaisesRegex(ValueError, "path|路徑"):
            compiler.validate_stage5_binding(self.layer, bad, self.layer_path, self.root)

    def test_only_supported_english_shot_translation_fields_can_be_overridden(self):
        prepared = compiler.apply_stage5_binding(self.layer, self.binding)
        shot = prepared["shots"][0]
        self.assertEqual(shot["action_and_performance"]["action_stages"], ["原始中文動作"])
        self.assertEqual(shot["action_and_performance"]["action_stages_en"], ["The hero raises the spear."])
        self.assertEqual(prepared["asset_refs"]["scene_id"], "S-HALL")
        self.assertEqual(prepared["asset_refs"]["creatures"][0]["id"], "E-SNAKE")
        bad = copy.deepcopy(self.binding)
        bad["metadata_override"] = {"target_duration_sec": 999}
        with self.assertRaisesRegex(ValueError, "metadata_override"):
            compiler.apply_stage5_binding(self.layer, bad)
        bad = copy.deepcopy(self.binding)
        bad["shot_overrides"]["EP03-SH001"]["action_stages"] = ["unauthorized story edit"]
        with self.assertRaisesRegex(ValueError, "only|僅|allowed|允許"):
            compiler.apply_stage5_binding(self.layer, bad)

    def test_compiler_includes_all_bound_creatures_and_props_and_keeps_no_visual_roles_unpictured(self):
        registry = compiler.AssetRegistry(project_root=self.root)
        registry.style = {"style_anchor": "normalized 3D animation", "style_negative": "No text"}
        registry.locations["S-HALL"] = {"id": "S-HALL", "name": "Hall", "desc_en": "school hall", "ref_img": "images/S-HALL.png"}
        registry.characters["C-HERO"] = {"id": "C-HERO", "name": "Hero", "desc_en": "a student", "short_en": "student", "ref_img": "images/C-HERO.png", "wardrobe_states": {}, "is_creature": False}
        registry.characters["E-SNAKE"] = {"id": "E-SNAKE", "name": "snake", "desc_en": "a yellow serpent", "short_en": "serpent", "ref_img": "images/E-SNAKE.png", "wardrobe_states": {}, "is_creature": True}
        registry.characters["C-VOICE"] = {"id": "C-VOICE", "name": "voice role", "desc_en": "an off-screen voice", "short_en": "off-screen voice", "ref_img": "", "wardrobe_states": {}, "is_creature": False, "no_visual_reference": True}
        registry.props["P-SPEAR"] = {"id": "P-SPEAR", "name": "spear", "desc_en": "a long silver spear", "ref_img": "images/P-SPEAR.png"}
        registry.bodydetails["D-SCAR"] = {"id": "D-SCAR", "name": "scar detail", "desc_en": "a healed scar on the left forearm", "ref_img": "images/D-SCAR.png"}
        data = compiler.apply_stage5_binding(self.layer, self.binding)
        data["style_lock"]["anchor"] = ""
        compiled = compiler.compile_segment_h3(data, registry, auto_lora=False, stage5_binding=self.binding)
        refs = compiled["reference_images"]
        self.assertEqual([ref["type"] for ref in refs], ["scene", "character", "creature", "prop", "bodydetail"])
        self.assertIn("a yellow serpent", compiled["h3_prompt"])
        self.assertIn("a long silver spear", compiled["h3_prompt"])
        self.assertNotIn("C-VOICE", [ref["id"] for ref in refs])
        self.assertIn("normalized 3D animation", compiled["h3_prompt"])
        self.assertEqual(compiled["metadata"]["style_lock"]["anchor"], "normalized 3D animation")
        self.assertEqual(compiled["metadata"]["style_lock"]["negative"], "")
        self.assertEqual(compiled["metadata"]["qa_exclusions"], "No text")
        self.assertEqual(compiled["metadata"]["style_lock"]["lighting_lock_line"], "natural ambient light")

    def test_no_visual_functional_speaker_remains_offscreen(self):
        registry = compiler.AssetRegistry(project_root=self.root)
        registry.locations["S-HALL"] = {"id": "S-HALL", "name": "Hall", "desc_en": "school hall", "ref_img": "images/S-HALL.png"}
        registry.characters["C-HERO"] = {"id": "C-HERO", "name": "hero", "desc_en": "a student", "short_en": "student", "ref_img": "images/C-HERO.png", "wardrobe_states": {}}
        registry.characters["E-SNAKE"] = {"id": "E-SNAKE", "name": "snake", "desc_en": "a yellow serpent", "short_en": "serpent", "ref_img": "images/E-SNAKE.png", "wardrobe_states": {}, "is_creature": True}
        registry.characters["C-VOICE"] = {"id": "C-VOICE", "name": "guide", "desc_en": "a guide speaking from off-screen", "short_en": "off-screen guide", "ref_img": "", "wardrobe_states": {}, "no_visual_reference": True, "voice_only": True}
        registry.props["P-SPEAR"] = {"id": "P-SPEAR", "name": "spear", "desc_en": "a long silver spear", "ref_img": "images/P-SPEAR.png"}
        registry.bodydetails["D-SCAR"] = {"id": "D-SCAR", "name": "scar", "desc_en": "a healed scar", "ref_img": "images/D-SCAR.png"}
        data = compiler.apply_stage5_binding(self.layer, self.binding)
        data["shots"][0]["dialogue_and_audio"] = {
            "has_dialogue": True, "speaker": "C-VOICE", "line_verbatim": "往前走。", "voice_4d_spec": "voiceover",
        }
        compiled = compiler.compile_segment_h3(data, registry, auto_lora=False, stage5_binding=self.binding)
        self.assertIn("do not show the speaker", compiled["h3_prompt"])
        self.assertNotIn("is the visible speaking character", compiled["h3_prompt"])
        self.assertNotIn("C-VOICE", [ref["id"] for ref in compiled["reference_images"]])

    def test_authored_camera_hold_stage_does_not_duplicate_camera_movement_clause(self):
        registry = compiler.AssetRegistry(project_root=self.root)
        registry.locations["S-HALL"] = {"id": "S-HALL", "name": "Hall", "desc_en": "school hall", "ref_img": "images/S-HALL.png"}
        registry.characters["C-HERO"] = {"id": "C-HERO", "name": "hero", "desc_en": "a student", "short_en": "student", "ref_img": "images/C-HERO.png", "wardrobe_states": {}}
        data = self._layer()
        data["shots"][0]["action_and_performance"]["action_stages_en"] = [
            "Stage 1: The camera holds on the intact north wall.",
        ]
        data["shots"][0]["character_ids"] = ["C-HERO"]
        compiled = compiler.compile_segment_h3(data, registry, auto_lora=False)
        result = compiler.lint_h3_prompt(compiled["h3_prompt"], nominal_duration=9)
        self.assertTrue(result["passed"], result["errors"])
        self.assertIn("The view remains on the intact north wall.", compiled["h3_prompt"])

    def test_creature_morphology_references_are_scoped_to_their_authored_shots(self):
        registry = compiler.AssetRegistry(project_root=self.root)
        registry.locations["S-HALL"] = {"id": "S-HALL", "name": "Hall", "desc_en": "school hall", "ref_img": "images/S-HALL.png"}
        registry.characters["C-HERO"] = {"id": "C-HERO", "name": "hero", "desc_en": "a student", "short_en": "student", "ref_img": "images/C-HERO.png", "wardrobe_states": {}}
        registry.characters["E-SNAKE"] = {"id": "E-SNAKE", "name": "serpent", "desc_en": "large serpent with eyes and mouth", "short_en": "serpent", "ref_img": "images/E-SNAKE.png", "wardrobe_states": {}, "is_creature": True}
        registry.props["P-SPEAR"] = {"id": "P-SPEAR", "name": "spear", "desc_en": "a silver spear", "ref_img": "images/P-SPEAR.png"}
        registry.bodydetails["D-SCAR"] = {"id": "D-SCAR", "name": "scar", "desc_en": "a healed scar", "ref_img": "images/D-SCAR.png"}
        for rel in ("images/E-SNAKE-early.png", "images/E-SNAKE-adult.png"):
            (self.root / rel).write_bytes(b"variant-reference")
        binding = copy.deepcopy(self.binding)
        scene = [{"id": "S-HALL", "reference_image": "images/S-HALL.png"}]
        hero = [{"id": "C-HERO", "costume_id": "W-01", "reference_image": "images/C-HERO.png"}]
        binding["shots"] = [
            {"global_shot_id": "EP03-SH001", "reference_paths": {
                "scene": scene, "characters": hero,
                "creatures": [{"id": "E-SNAKE", "variant": "early", "reference_image": "images/E-SNAKE-early.png", "desc_en": "a short yellow form with no visible eyes or mouth"}],
                "props": [], "bodydetails": [],
            }, "visual_subject_ids": ["C-HERO", "E-SNAKE"]},
            {"global_shot_id": "EP03-SH002", "reference_paths": {
                "scene": scene, "characters": hero,
                "creatures": [{"id": "E-SNAKE", "variant": "adult", "reference_image": "images/E-SNAKE-adult.png", "desc_en": "a large yellow serpent with developed eyes and mouth; no visible teeth"}],
                "props": [], "bodydetails": [],
            }, "visual_subject_ids": ["C-HERO", "E-SNAKE"]},
            {"global_shot_id": "EP03-SH003", "reference_paths": {
                "scene": scene, "characters": hero, "creatures": [], "props": [], "bodydetails": [],
            }, "visual_subject_ids": ["C-HERO"]},
        ]
        data = compiler.apply_stage5_binding(self.layer, binding)
        compiled = compiler.compile_segment_h3(data, registry, auto_lora=False, stage5_binding=binding)
        refs = compiled["reference_images"]
        self.assertEqual([r["path"] for r in refs if r.get("canonical_id") == "E-SNAKE"], ["images/E-SNAKE-adult.png"])
        self.assertTrue(any(r["type"] == "creature" and r["path"] == "images/E-SNAKE-early.png" for r in refs))
        self.assertTrue(any(r["type"] == "creature_variant" and r["path"] == "images/E-SNAKE-adult.png" for r in refs))
        prompt = compiled["h3_prompt"]
        self.assertIn("Subject 2", prompt)
        self.assertIn("a short yellow form with no visible eyes or mouth", prompt)
        self.assertIn("use <Picture 3> for the creature's early morphology in this shot only", prompt)
        shot1_body = prompt.split("[Shot 1]", 1)[1].split("[Shot 2]", 1)[0]
        self.assertNotIn("adult morphology", shot1_body)
        self.assertIn("images/E-SNAKE-adult.png", [r["path"] for r in refs])

    def test_cli_uses_bindings_without_mutating_approved_layer2_and_rejects_stale_hash(self):
        bible = {
            "style": {"anchor": "normalized style", "negative": "No text", "lighting_lock_line": "soft daylight"},
            "characters": [
                {"id": "C-HERO", "name": "hero", "visual_prompt_en": "a student", "reference_image": "images/C-HERO.png"},
                {"id": "E-SNAKE", "name": "snake", "visual_prompt_en": "a yellow serpent", "reference_image": "images/E-SNAKE.png", "is_creature": True},
                {"id": "C-VOICE", "name": "guide", "no_visual_reference": True, "voice_only": True},
            ],
            "locations": [{"id": "S-HALL", "name": "hall", "visual_prompt_en": "school hall", "reference_image": "images/S-HALL.png"}],
            "props": [{"id": "P-SPEAR", "name": "spear", "desc_en": "a long silver spear", "reference_image": "images/P-SPEAR.png"}],
            "bodydetails": [{"id": "D-SCAR", "name": "scar detail", "desc_en": "a healed scar on the left forearm", "reference_image": "images/D-SCAR.png"}],
        }
        bible_path = self.root / "video-bible.json"
        bible_path.write_text(json.dumps(bible, ensure_ascii=False), encoding="utf-8")
        bindings_path = self.root / "video-bindings.json"
        cli_binding = copy.deepcopy(self.binding)
        cli_binding["metadata_override"] = {
            "soundscape_en": "A distant bell rings once.",
            "music_en": "No music.",
            "lighting_lock_line": "soft daylight from frame left.",
        }
        bindings_path.write_text(json.dumps({"segments": [cli_binding]}, ensure_ascii=False), encoding="utf-8")
        layer_before = self.layer_path.read_bytes()
        argv = [
            "compile_layer2_to_h3.py", "--layer2", str(self.layer_path), "--bindings", str(bindings_path),
            "--bible", str(bible_path), "--project-root", str(self.root), "--skip-stage-gate",
            "--output-segments", str(self.root / "segments.json"), "--no-auto-lora",
        ]
        output = StringIO()
        with patch.object(sys, "argv", argv), redirect_stdout(output), redirect_stderr(output):
            status = compiler.main()
        self.assertEqual(status, 0, output.getvalue())
        self.assertEqual(self.layer_path.read_bytes(), layer_before)
        result = json.loads((self.root / "segments.json").read_text(encoding="utf-8"))["segments"][0]
        self.assertIn("The hero raises the spear.", result["h3_prompt"])
        self.assertIn("a narrow school back alley beside an intact wall", result["h3_prompt"])
        self.assertIn("style anchor: normalized style", result["h3_prompt"])
        self.assertIn("A distant bell rings once.", result["h3_prompt"])
        self.assertIn("No music.", result["h3_prompt"])
        self.assertEqual([ref["type"] for ref in result["reference_images"]], ["scene", "character", "creature", "prop", "bodydetail"])

        stale = copy.deepcopy(self.binding)
        stale["source_sha256"] = "f" * 64
        bindings_path.write_text(json.dumps({"segments": [stale]}, ensure_ascii=False), encoding="utf-8")
        output = StringIO()
        with patch.object(sys, "argv", argv), redirect_stdout(output), redirect_stderr(output):
            status = compiler.main()
        self.assertEqual(status, 1)
        self.assertIn("SHA256", output.getvalue())


if __name__ == "__main__":
    unittest.main()
