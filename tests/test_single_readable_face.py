import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))

import compile_layer2_to_h3 as compiler


class SingleReadableFaceTests(unittest.TestCase):
    """Stage 5 may name the characters whose faces are actually readable.

    H3 averages several character reference images into one face, so a segment
    carries one scene master plus at most one character identity reference.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.layer_path = self.root / "layer2" / "layer2-EP01-S01.json"
        self.layer_path.parent.mkdir()
        self.layer = self._layer()
        self.layer_path.write_text(json.dumps(self.layer, ensure_ascii=False), encoding="utf-8")
        self.sha = hashlib.sha256(self.layer_path.read_bytes()).hexdigest()
        self.binding = {
            "segment_id": "EP01-S01",
            "source_layer2_path": "layer2/layer2-EP01-S01.json",
            "source_sha256": self.sha,
            "scene_id": "L-ALLEY",
            "scene_description_en": "a narrow school back alley",
            "primary_character": "C-HERO",
            "asset_refs_override": {
                "scene_id": "L-ALLEY",
                "characters": [{"id": "C-HERO", "costume_id": "W-01"}, {"id": "C-FRIEND"}],
                "creatures": [],
                "props": [],
            },
            "shots": [{
                "global_shot_id": "EP01-SH001",
                "reference_paths": {
                    "scene": "images/L-ALLEY.png",
                    "characters": {"C-HERO": "images/C-HERO.png", "C-FRIEND": "images/C-FRIEND.png"},
                },
                "visual_subject_ids": ["C-HERO", "C-FRIEND"],
                "face_subject_ids": ["C-HERO"],
                "crop_note_en": "The friend is framed as a near shoulder and back, with his head turned away.",
            }, {
                "global_shot_id": "EP01-SH002",
                "reference_paths": {},
                "visual_subject_ids": ["C-HERO", "C-FRIEND"],
                "face_subject_ids": ["C-HERO"],
            }],
        }
        for rel in ("images/L-ALLEY.png", "images/C-HERO.png", "images/C-FRIEND.png"):
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"fixture-reference")

    @staticmethod
    def _layer():
        return {
            "segment_id": "EP01-S01", "scene_id": "L-OLD", "metadata": {
                "target_duration_sec": 6, "aspect_ratio": "16:9",
            },
            "style_lock": {"anchor": "approved style"},
            "asset_refs": {"scene_id": "L-OLD", "characters": [{"id": "C-HERO"}, {"id": "C-FRIEND"}]},
            "shots": [{
                "global_shot_id": "EP01-SH001", "shot_id": "SH01",
                "start_time": 0, "end_time": 3, "duration": 3,
                "character_ids": ["C-HERO", "C-FRIEND"],
                "camera_optics": {"shot_size": "MS", "movement": "static"},
                "action_and_performance": {
                    "action_stages": ["A"], "action_stages_en": ["The hero steps forward."],
                    "observable_expression": "B", "observable_expression_en": "Calm.",
                },
                "dialogue_and_audio": {"has_dialogue": False},
                "spatial_blocking": {"blocking_desc": "hero left", "anchor_objects": []},
            }, {
                "global_shot_id": "EP01-SH002", "shot_id": "SH02",
                "start_time": 3, "end_time": 6, "duration": 3,
                "character_ids": ["C-HERO", "C-FRIEND"],
                "camera_optics": {"shot_size": "MS", "movement": "static"},
                "action_and_performance": {
                    "action_stages": ["A"], "action_stages_en": ["The hero stops."],
                    "observable_expression": "B", "observable_expression_en": "Still.",
                },
                "dialogue_and_audio": {"has_dialogue": False},
                "spatial_blocking": {},
            }],
        }

    def _registry(self):
        registry = compiler.AssetRegistry(project_root=self.root)
        registry.style = {"style_anchor": "normalized 3D animation", "style_negative": "No text"}
        registry.locations["L-ALLEY"] = {
            "id": "L-ALLEY", "name": "Alley", "desc_en": "a narrow school back alley",
            "ref_img": "images/L-ALLEY.png",
        }
        for cid, name, desc in (
            ("C-HERO", "Hero", "a teenage boy in a light shirt"),
            ("C-FRIEND", "Friend", "a stocky student in a white school shirt"),
        ):
            registry.characters[cid] = {
                "id": cid, "name": name, "desc_en": desc, "short_en": name.lower(),
                "ref_img": f"images/{cid}.png", "wardrobe_states": {}, "is_creature": False,
            }
        return registry

    def _compile(self, binding):
        data = compiler.apply_stage5_binding(self.layer, binding)
        data["style_lock"]["anchor"] = ""
        return compiler.compile_segment_h3(
            data, self._registry(), auto_lora=False, stage5_binding=binding,
        )

    def test_face_subject_ids_limit_character_references_to_the_readable_face(self):
        compiled = self._compile(self.binding)
        refs = compiled["reference_images"]
        character_refs = [ref for ref in refs if ref["type"] == "character"]
        self.assertEqual(len(character_refs), 1, "only the readable face may carry a character reference")
        self.assertEqual(character_refs[0]["id"], "C-HERO")
        self.assertNotIn("C-FRIEND", [ref["id"] for ref in refs])
        prompt = compiled["h3_prompt"]
        self.assertIn("readable face", prompt)
        self.assertIn("near shoulder and back", prompt)
        self.assertIn("pure text description without reference image", prompt)

    def test_without_face_subject_ids_every_visible_character_keeps_its_reference(self):
        legacy = copy.deepcopy(self.binding)
        for shot in legacy["shots"]:
            shot.pop("face_subject_ids", None)
            shot.pop("crop_note_en", None)
        compiled = self._compile(legacy)
        character_refs = [ref for ref in compiled["reference_images"] if ref["type"] == "character"]
        self.assertEqual({ref["id"] for ref in character_refs}, {"C-HERO", "C-FRIEND"})

    def test_two_readable_faces_are_reported_as_a_mix_face_risk(self):
        risky = copy.deepcopy(self.binding)
        for shot in risky["shots"]:
            shot["face_subject_ids"] = ["C-HERO", "C-FRIEND"]
        compiled = self._compile(risky)
        notes = " ".join(compiled.get("compile_notes", []))
        self.assertIn("face_subject_ids", notes)
        self.assertIn("C-FRIEND", [ref["id"] for ref in compiled["reference_images"] if ref["type"] == "character"])

    def test_binding_validation_rejects_malformed_face_fields(self):
        bad = copy.deepcopy(self.binding)
        bad["shots"][0]["face_subject_ids"] = "C-HERO"
        with self.assertRaisesRegex(ValueError, "face_subject_ids"):
            compiler.validate_stage5_binding(self.layer, bad, self.layer_path, self.root)
        bad = copy.deepcopy(self.binding)
        bad["shots"][0]["crop_note_en"] = "   "
        with self.assertRaisesRegex(ValueError, "crop_note_en"):
            compiler.validate_stage5_binding(self.layer, bad, self.layer_path, self.root)

    def test_a_face_subject_marked_as_having_no_visual_reference_is_rejected(self):
        broken = copy.deepcopy(self.binding)
        broken["shots"][0]["no_visual_reference_ids"] = ["C-HERO"]
        with self.assertRaisesRegex(ValueError, "readable face"):
            self._compile(broken)


if __name__ == "__main__":
    unittest.main()
