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

import audit_refs_and_segments as audit
import compile_layer2_to_h3 as compiler


class CloneDefenseTests(unittest.TestCase):
    """複製人防線：未錨定人物、單視角裁切、官方 (Sx) 綁定與旁白外部化。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.layer_path = self.root / "layer2" / "layer2-EP01-S01.json"
        self.layer_path.parent.mkdir()
        self.layer = self._layer()
        self.layer_path.write_text(json.dumps(self.layer, ensure_ascii=False), encoding="utf-8")
        self.sha = hashlib.sha256(self.layer_path.read_bytes()).hexdigest()
        for rel in ("images/L-ALLEY.png", "images/C-HERO.png", "images/C-FRIEND.png",
                    "images/C-FRIEND-back.png", "images/board-2560x1440.png"):
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"fixture-reference")
        self.binding = self._binding()

    # ---------- fixtures ----------

    def _binding(self, *, friend_reference="images/C-FRIEND.png", anchor=False):
        shot = {
            "global_shot_id": "EP01-SH001",
            "reference_paths": {
                "scene": [{"id": "L-ALLEY", "reference_image": "images/L-ALLEY.png"}],
                "characters": [
                    {"id": "C-HERO", "reference_image": "images/C-HERO.png"},
                    {"id": "C-FRIEND", "reference_image": friend_reference},
                ],
            },
            "visual_subject_ids": ["C-HERO", "C-FRIEND"],
            "face_subject_ids": ["C-HERO"],
            "crop_note_en": "The friend is framed as a near shoulder and back, with his head turned away.",
        }
        if anchor:
            shot["identity_anchor_ids"] = ["C-FRIEND"]
        return {
            "segment_id": "EP01-S01",
            "source_layer2_path": "layer2/layer2-EP01-S01.json",
            "source_sha256": self.sha,
            "scene_id": "L-ALLEY",
            "scene_description_en": "a narrow school back alley",
            "primary_character": "C-HERO",
            "asset_refs_override": {
                "scene_id": "L-ALLEY",
                "characters": [{"id": "C-HERO", "costume_id": "W-01"}, {"id": "C-FRIEND"}],
                "creatures": [], "props": [],
            },
            "shots": [shot],
        }

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
                "start_time": 0, "end_time": 6, "duration": 6,
                "character_ids": ["C-HERO", "C-FRIEND"],
                "camera_optics": {"shot_size": "MS", "movement": "static"},
                "action_and_performance": {
                    "action_stages": ["A"], "action_stages_en": ["The hero steps forward."],
                    "observable_expression": "B", "observable_expression_en": "Calm.",
                },
                "dialogue_and_audio": {"has_dialogue": False},
                "spatial_blocking": {"blocking_desc": "hero left", "anchor_objects": []},
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

    # ---------- 定律二：重要角色必掛自己的參考圖 ----------

    def test_identity_anchor_character_keeps_its_own_reference(self):
        binding = self._binding(anchor=True)
        compiled = self._compile(binding)
        character_refs = [r for r in compiled["reference_images"] if r["type"] == "character"]
        self.assertEqual({r["id"] for r in character_refs}, {"C-HERO", "C-FRIEND"})
        anchor_ref = next(r for r in character_refs if r["id"] == "C-FRIEND")
        self.assertEqual(anchor_ref["reference_view"], "non_face")
        self.assertIn("partially_preserved", compiled["h3_prompt"])
        self.assertIn("the reference face is not imported", compiled["h3_prompt"])
        self.assertEqual(compiled["unanchored_in_frame_characters"], [])

    def test_identity_anchor_without_reference_path_is_rejected(self):
        binding = self._binding(anchor=True)
        binding["shots"][0]["reference_paths"]["characters"] = [
            {"id": "C-HERO", "reference_image": "images/C-HERO.png"},
        ]
        with self.assertRaisesRegex(ValueError, "identity_anchor_ids"):
            self._compile(binding)

    def test_a_character_cannot_be_both_a_readable_face_and_an_identity_anchor(self):
        binding = self._binding(anchor=True)
        binding["shots"][0]["face_subject_ids"] = ["C-HERO", "C-FRIEND"]
        with self.assertRaisesRegex(ValueError, "both a readable face"):
            self._compile(binding)

    def test_visible_character_without_bound_reference_is_not_silently_backfilled(self):
        """在場角色若沒有綁定參考圖，不得沿用角色聖經的整張設定板。"""
        binding = self._binding()
        binding["shots"][0].pop("face_subject_ids", None)
        binding["shots"][0].pop("crop_note_en", None)
        binding["shots"][0]["reference_paths"]["characters"] = [
            {"id": "C-HERO", "reference_image": "images/C-HERO.png"},
        ]
        with self.assertRaisesRegex(ValueError, "no approved reference image"):
            self._compile(binding)

    def test_unanchored_in_frame_character_is_reported(self):
        binding = self._binding()
        binding["shots"][0]["reference_paths"]["characters"] = [
            {"id": "C-HERO", "reference_image": "images/C-HERO.png"},
        ]
        compiled = self._compile(binding)
        self.assertIn("C-FRIEND", compiled["unanchored_in_frame_characters"])
        self.assertTrue(any("未錨定在場人物" in n for n in compiled["compile_notes"]))

    # ---------- 門禁 ----------

    def test_e19_blocks_unanchored_in_frame_characters(self):
        result = audit.audit_refs_and_subjects({
            "segment_id": "EP01-S01",
            "reference_images": [{"id": "L-ALLEY", "type": "scene", "path": "images/L-ALLEY.png"}],
            "h3_prompt": "subject_definitions:\n<Picture 1> is a scene reference.\n",
            "unanchored_in_frame_characters": ["C-FRIEND"],
        })
        self.assertFalse(result["passed"])
        self.assertTrue(any("E19" in e for e in result["errors"]))

    def test_e20_blocks_a_multi_panel_reference_sheet(self):
        from PIL import Image
        board = self.root / "images/board-2560x1440.png"
        Image.new("RGB", (2560, 1440), (10, 10, 10)).save(board)
        result = audit.audit_refs_and_subjects({
            "segment_id": "EP01-S01",
            "reference_images": [
                {"id": "L-ALLEY", "type": "scene", "path": "images/L-ALLEY.png"},
                {"id": "C-HERO", "type": "character", "path": "images/board-2560x1440.png"},
            ],
            "h3_prompt": "subject_definitions:\n<Picture 1> is a scene reference.\n",
        }, project_root=self.root)
        self.assertFalse(result["passed"])
        self.assertTrue(any("E20" in e for e in result["errors"]))

    def test_e21_blocks_unanchored_crowd_descriptions(self):
        prompt = (
            "subject_definitions:\n<Picture 1> is a scene reference.\n\n"
            "detailed_description:\n[Shot 1] A medium shot frames the empty street. "
            "Tourists leave along the path on frame-right, their varied everyday clothes clearly visible.\n\n"
            "overall_soundscape:\nWind.\n\nnon_diegetic_music:\nN/A\n"
        )
        result = audit.audit_refs_and_subjects({
            "segment_id": "EP01-S01",
            "reference_images": [{"id": "L-ALLEY", "type": "scene", "path": "images/L-ALLEY.png"}],
            "h3_prompt": prompt,
        })
        self.assertFalse(result["passed"])
        self.assertTrue(any("E21" in e for e in result["errors"]))

    def test_e21_accepts_a_crowd_anchored_by_an_extras_reference(self):
        prompt = (
            "subject_definitions:\n<Picture 1> is a scene reference.\n"
            "<Subject 1> is the group of background extras in <Picture 2>.\n\n"
            "detailed_description:\n[Shot 1] A crowd of seated disciples in pale yellow robes fills the frame.\n\n"
            "overall_soundscape:\nWind.\n\nnon_diegetic_music:\nN/A\n"
        )
        refs = [{"id": "S-HALL", "type": "scene", "path": "images/S-HALL.png"},
                {"id": "EXTRAS-x", "type": "extras", "path": "images/extras-x.png"}]
        result = audit.audit_refs_and_subjects({"segment_id": "EP01-S02", "reference_images": refs, "h3_prompt": prompt})
        self.assertFalse(any("E21" in e for e in result["errors"]), result["errors"])
        refs[1]["path"] = ""
        result = audit.audit_refs_and_subjects({"segment_id": "EP01-S02", "reference_images": refs, "h3_prompt": prompt})
        self.assertTrue(any("E21" in e for e in result["errors"]))

    def test_e21_accepts_an_unidentifiable_out_of_focus_crowd(self):
        prompt = (
            "subject_definitions:\n<Picture 1> is a scene reference.\n\n"
            "detailed_description:\n[Shot 1] A medium shot frames the empty street. "
            "Tourists recede along the path on frame-right, out of focus and without facial detail.\n\n"
            "overall_soundscape:\nWind.\n\nnon_diegetic_music:\nN/A\n"
        )
        result = audit.audit_refs_and_subjects({
            "segment_id": "EP01-S01",
            "reference_images": [{"id": "L-ALLEY", "type": "scene", "path": "images/L-ALLEY.png"}],
            "h3_prompt": prompt,
        })
        self.assertFalse(any("E21" in e for e in result["errors"]), result["errors"])

    def test_e22_requires_a_speaker_id_when_a_dialogue_block_exists(self):
        prompt = (
            "subject_definitions:\n<Picture 1> is a scene reference.\n\n"
            "detailed_description:\n[Shot 1] A medium shot frames the alley. "
            "The guide asks from offscreen. <d>[Chinese] 你聽得見嗎？</d>\n\n"
            "overall_soundscape:\nWind.\n\nnon_diegetic_music:\nN/A\n"
        )
        result = audit.audit_refs_and_subjects({
            "segment_id": "EP01-S01",
            "reference_images": [{"id": "L-ALLEY", "type": "scene", "path": "images/L-ALLEY.png"}],
            "h3_prompt": prompt,
        })
        self.assertFalse(result["passed"])
        self.assertTrue(any("E22" in e for e in result["errors"]))

    def test_e25_blocks_dialogue_repeated_in_the_soundscape(self):
        prompt = (
            "subject_definitions:\n<Picture 1> is a scene reference.\n\n"
            "detailed_description:\n[Shot 1] A medium shot frames the alley. "
            "The guide (S1) says: <d>[Chinese] 你聽得見嗎？</d>\n\n"
            "overall_soundscape:\nWind. The guide's question 你聽得見嗎？ stays clear in the foreground.\n\n"
            "non_diegetic_music:\nN/A\n"
        )
        result = audit.audit_refs_and_subjects({
            "segment_id": "EP01-S01",
            "reference_images": [{"id": "L-ALLEY", "type": "scene", "path": "images/L-ALLEY.png"}],
            "h3_prompt": prompt,
        })
        self.assertFalse(result["passed"])
        self.assertTrue(any("E25" in e for e in result["errors"]))

    def test_e24_blocks_a_voiceover_line_under_the_external_narration_policy(self):
        prompt = (
            "subject_definitions:\n<Picture 1> is a scene reference.\n\n"
            "detailed_description:\n[Shot 1] A medium shot frames the alley. "
            "The guide (S1) says in an off-screen voiceover: <d>[Chinese] 你聽得見嗎？</d> "
            "while the visible characters' lips remain completely closed.\n\n"
            "overall_soundscape:\nWind.\n\nnon_diegetic_music:\nN/A\n"
        )
        result = audit.audit_refs_and_subjects({
            "segment_id": "EP01-S01",
            "metadata": {"narration_policy": "external"},
            "reference_images": [{"id": "L-ALLEY", "type": "scene", "path": "images/L-ALLEY.png"}],
            "h3_prompt": prompt,
            "external_narration": [{"line": "你聽得見嗎？", "language": "Chinese"}],
        })
        self.assertFalse(result["passed"])
        self.assertTrue(any("E24" in e for e in result["errors"]))

    # ---------- 官方 (Sx) 綁定 ----------

    def test_speaker_ids_are_assigned_in_first_vocal_order(self):
        data = self._layer()
        base = data["shots"][0]
        data["shots"] = [
            dict(base, global_shot_id="EP01-SH001", shot_id="SH01",
                 start_time=0, end_time=2, duration=2, character_ids=["C-HERO"],
                 dialogue_and_audio={"has_dialogue": True, "speaker": "C-HERO", "line_verbatim": "甲。"}),
            dict(base, global_shot_id="EP01-SH002", shot_id="SH02",
                 start_time=2, end_time=4, duration=2, character_ids=["C-HERO", "C-FRIEND"],
                 dialogue_and_audio={"has_dialogue": True, "speaker": "C-FRIEND", "line_verbatim": "乙。"}),
            dict(base, global_shot_id="EP01-SH003", shot_id="SH03",
                 start_time=4, end_time=6, duration=2, character_ids=["C-HERO"],
                 dialogue_and_audio={"has_dialogue": True, "speaker": "C-HERO", "line_verbatim": "丙。"}),
        ]
        data["style_lock"]["anchor"] = ""
        compiled = compiler.compile_segment_h3(data, self._registry(), auto_lora=False)
        self.assertEqual(compiled["speaker_ids"], {"C-HERO": "S1", "C-FRIEND": "S2"})
        prompt = compiled["h3_prompt"]
        self.assertIn("(S1)", prompt)
        self.assertIn("(S2)", prompt)

    def test_external_narration_is_not_written_into_the_h3_prompt(self):
        data = self._layer()
        shot = dict(data["shots"][0])
        shot["dialogue_and_audio"] = {
            "has_dialogue": True, "speaker": "C-HERO", "line_verbatim": "這是一句旁白。",
            "voice_4d_spec": "voiceover", "lips_closed_lock": True,
        }
        data["shots"] = [shot]
        data["style_lock"]["anchor"] = ""
        compiled = compiler.compile_segment_h3(data, self._registry(), auto_lora=False)
        self.assertNotIn("<d>[Chinese] 這是一句旁白。</d>", compiled["h3_prompt"])
        self.assertEqual(len(compiled["external_narration"]), 1)
        self.assertEqual(compiled["external_narration"][0]["line"], "這是一句旁白。")
        self.assertTrue(compiled["external_narration"][0]["is_voiceover"])

    def test_visible_mouth_dialogue_keeps_its_d_block(self):
        data = self._layer()
        shot = dict(data["shots"][0])
        shot["character_ids"] = ["C-HERO"]
        shot["dialogue_and_audio"] = {
            "has_dialogue": True, "speaker": "C-HERO", "line_verbatim": "看著我。",
        }
        data["shots"] = [shot]
        data["style_lock"]["anchor"] = ""
        compiled = compiler.compile_segment_h3(data, self._registry(), auto_lora=False)
        self.assertIn("<d>[Chinese] 看著我。</d>", compiled["h3_prompt"])
        self.assertEqual(compiled["external_narration"], [])


class PanelLookupTests(unittest.TestCase):
    """整板查表：四視圖板可以整張用，但必須宣告用哪一格。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.layer_path = self.root / "layer2" / "layer2-EP01-S01.json"
        self.layer_path.parent.mkdir()
        self.layer = {
            "segment_id": "EP01-S01", "scene_id": "L-OLD", "metadata": {
                "target_duration_sec": 6, "aspect_ratio": "16:9",
            },
            "style_lock": {"anchor": "approved style"},
            "asset_refs": {"scene_id": "L-OLD", "characters": [{"id": "C-HERO"}, {"id": "C-FRIEND"}]},
            "shots": [{
                "global_shot_id": "EP01-SH001", "shot_id": "SH01",
                "start_time": 0, "end_time": 6, "duration": 6,
                "character_ids": ["C-HERO", "C-FRIEND"],
                "camera_optics": {"shot_size": "MS", "movement": "static"},
                "action_and_performance": {
                    "action_stages": ["A"], "action_stages_en": ["The hero steps forward."],
                    "observable_expression": "B", "observable_expression_en": "Calm.",
                },
                "dialogue_and_audio": {"has_dialogue": False},
                "spatial_blocking": {"blocking_desc": "hero left", "anchor_objects": []},
            }],
        }
        self.layer_path.write_text(json.dumps(self.layer, ensure_ascii=False), encoding="utf-8")
        self.sha = hashlib.sha256(self.layer_path.read_bytes()).hexdigest()
        for rel in ("images/L-ALLEY.png", "images/C-HERO.png", "images/board.png"):
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"fixture-reference")

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

    def _binding(self, *, panel_label="the fourth figure from the left, a full-body back view"):
        friend_entry = {"id": "C-FRIEND", "reference_image": "images/board.png"}
        if panel_label is not None:
            friend_entry["reference_view"] = "panel"
            friend_entry["panel_label_en"] = panel_label
        return {
            "segment_id": "EP01-S01",
            "source_layer2_path": "layer2/layer2-EP01-S01.json",
            "source_sha256": self.sha,
            "scene_id": "L-ALLEY",
            "scene_description_en": "a narrow school back alley",
            "primary_character": "C-HERO",
            "asset_refs_override": {
                "scene_id": "L-ALLEY",
                "characters": [{"id": "C-HERO", "costume_id": "W-01"}, {"id": "C-FRIEND"}],
                "creatures": [], "props": [],
            },
            "shots": [{
                "global_shot_id": "EP01-SH001",
                "reference_paths": {
                    "scene": [{"id": "L-ALLEY", "reference_image": "images/L-ALLEY.png"}],
                    "characters": [
                        {"id": "C-HERO", "reference_image": "images/C-HERO.png"},
                        friend_entry,
                    ],
                },
                "visual_subject_ids": ["C-HERO", "C-FRIEND"],
                "face_subject_ids": ["C-HERO"],
                "identity_anchor_ids": ["C-FRIEND"],
            }],
        }

    def _compile(self, binding):
        data = compiler.apply_stage5_binding(self.layer, binding)
        data["style_lock"]["anchor"] = ""
        return compiler.compile_segment_h3(
            data, self._registry(), auto_lora=False, stage5_binding=binding,
        )

    def test_panel_lookup_names_the_panel_and_excludes_the_rest_of_the_sheet(self):
        compiled = self._compile(self._binding())
        prompt = compiled["h3_prompt"]
        self.assertIn("the fourth figure from the left, a full-body back view", prompt)
        self.assertIn("that panel is the only part of the sheet used", prompt)
        self.assertIn("partially_preserved", prompt)
        self.assertIn("the other panels of that sheet", prompt)
        ref = next(r for r in compiled["reference_images"] if r["id"] == "C-FRIEND")
        self.assertEqual(ref["reference_view"], "panel")
        self.assertIn("panel_label_en", ref)
        self.assertEqual(compiled["unanchored_in_frame_characters"], [])

    def test_panel_lookup_without_a_label_is_rejected(self):
        binding = self._binding(panel_label="")
        binding["shots"][0]["reference_paths"]["characters"][1].pop("panel_label_en", None)
        with self.assertRaisesRegex(ValueError, "panel_label_en"):
            self._compile(binding)

    def test_panel_lookup_cannot_be_a_readable_face(self):
        binding = self._binding()
        binding["shots"][0]["face_subject_ids"] = ["C-HERO", "C-FRIEND"]
        binding["shots"][0].pop("identity_anchor_ids", None)
        with self.assertRaisesRegex(ValueError, "整板查表"):
            self._compile(binding)

    def test_panel_role_profile_keeps_the_side_profile_and_drops_the_frontal_face(self):
        binding = self._binding()
        binding["shots"][0]["reference_paths"]["characters"][1]["panel_role"] = "profile"
        binding["shots"][0]["reference_paths"]["characters"][1]["panel_label_en"] = (
            "the full-body three-quarter side view, the middle of the three standing full-body figures"
        )
        compiled = self._compile(binding)
        prompt = compiled["h3_prompt"]
        self.assertIn("only the three-quarter profile from it may appear in the target video", prompt)
        self.assertIn("the frontal face from that sheet is not imported", prompt)
        self.assertNotIn("no face appears in the target video", prompt)
        ref = next(r for r in compiled["reference_images"] if r["id"] == "C-FRIEND")
        self.assertEqual(ref["reference_view"], "panel")
        self.assertEqual(ref["panel_role"], "profile")

    def test_e20_allows_a_declared_panel_lookup(self):
        from PIL import Image
        board = self.root / "images/board.png"
        Image.new("RGB", (2560, 1440), (10, 10, 10)).save(board)
        result = audit.audit_refs_and_subjects({
            "segment_id": "EP01-S01",
            "reference_images": [
                {"id": "L-ALLEY", "type": "scene", "path": "images/L-ALLEY.png"},
                {"id": "C-FRIEND", "type": "character", "path": "images/board.png",
                 "reference_view": "panel",
                 "panel_label_en": "the fourth figure from the left, a full-body back view"},
            ],
            "h3_prompt": "subject_definitions:\n<Picture 1> is a scene reference.\n",
        }, project_root=self.root)
        self.assertFalse(any("E20" in e for e in result["errors"]), result["errors"])

    def test_e27_flags_a_panel_lookup_without_a_label(self):
        result = audit.audit_refs_and_subjects({
            "segment_id": "EP01-S01",
            "reference_images": [
                {"id": "L-ALLEY", "type": "scene", "path": "images/L-ALLEY.png"},
                {"id": "C-FRIEND", "type": "character", "path": "images/board.png",
                 "reference_view": "panel"},
            ],
            "h3_prompt": "subject_definitions:\n<Picture 1> is a scene reference.\n",
        })
        self.assertFalse(result["passed"])
        self.assertTrue(any("E27" in e for e in result["errors"]))


class VoiceReferenceTests(unittest.TestCase):
    """音色參考 <Audio N>：官方 ref-en §2.4 / §4.1 的綁定與保留標記。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.layer_path = self.root / "layer2" / "layer2-EP01-S01.json"
        self.layer_path.parent.mkdir()
        self.layer = {
            "segment_id": "EP01-S01", "scene_id": "L-OLD", "metadata": {
                "target_duration_sec": 6, "aspect_ratio": "16:9",
            },
            "style_lock": {"anchor": "approved style"},
            "asset_refs": {"scene_id": "L-OLD", "characters": [{"id": "C-HERO"}]},
            "shots": [{
                "global_shot_id": "EP01-SH001", "shot_id": "SH01",
                "start_time": 0, "end_time": 6, "duration": 6,
                "character_ids": ["C-HERO"],
                "camera_optics": {"shot_size": "MS", "movement": "static"},
                "action_and_performance": {
                    "action_stages": ["A"], "action_stages_en": ["The hero steps forward."],
                    "observable_expression": "B", "observable_expression_en": "Calm.",
                },
                "dialogue_and_audio": {
                    "has_dialogue": True, "speaker": "C-HERO", "line_verbatim": "看著我。",
                    "voice_4d_spec_en": "a teenage boy with a quiet, breathy voice",
                },
                "spatial_blocking": {"blocking_desc": "hero left", "anchor_objects": []},
            }],
        }
        self.layer_path.write_text(json.dumps(self.layer, ensure_ascii=False), encoding="utf-8")
        self.sha = hashlib.sha256(self.layer_path.read_bytes()).hexdigest()
        for rel in ("images/L-ALLEY.png", "images/C-HERO.png", "audio/V-HERO-master.wav"):
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"fixture-reference")

    def _registry(self):
        registry = compiler.AssetRegistry(project_root=self.root)
        registry.style = {"style_anchor": "normalized 3D animation", "style_negative": "No text"}
        registry.locations["L-ALLEY"] = {
            "id": "L-ALLEY", "name": "Alley", "desc_en": "a narrow school back alley",
            "ref_img": "images/L-ALLEY.png",
        }
        registry.characters["C-HERO"] = {
            "id": "C-HERO", "name": "Hero", "desc_en": "a teenage boy in a light shirt",
            "short_en": "hero", "ref_img": "images/C-HERO.png", "wardrobe_states": {}, "is_creature": False,
        }
        return registry

    def _binding(self, character_id="C-HERO"):
        return {
            "segment_id": "EP01-S01",
            "source_layer2_path": "layer2/layer2-EP01-S01.json",
            "source_sha256": self.sha,
            "scene_id": "L-ALLEY",
            "scene_description_en": "a narrow school back alley",
            "primary_character": "C-HERO",
            "asset_refs_override": {
                "scene_id": "L-ALLEY", "characters": [{"id": "C-HERO"}], "creatures": [], "props": [],
            },
            "audio_references": [{
                "id": "V-HERO", "path": "audio/V-HERO-master.wav", "character_id": character_id,
                "role": "voice-timbre",
                "description_en": "a single teenage boy's Mandarin line recorded dry with no music",
            }],
            "shots": [{
                "global_shot_id": "EP01-SH001",
                "reference_paths": {
                    "scene": [{"id": "L-ALLEY", "reference_image": "images/L-ALLEY.png"}],
                    "characters": [{"id": "C-HERO", "reference_image": "images/C-HERO.png"}],
                },
                "visual_subject_ids": ["C-HERO"],
                "face_subject_ids": ["C-HERO"],
            }],
        }

    def _compile(self, binding):
        data = compiler.apply_stage5_binding(self.layer, binding)
        data["style_lock"]["anchor"] = ""
        return compiler.compile_segment_h3(
            data, self._registry(), auto_lora=False, stage5_binding=binding,
        )

    def test_audio_reference_uses_the_official_label_and_retention_marker(self):
        compiled = self._compile(self._binding())
        prompt = compiled["h3_prompt"]
        self.assertIn("<Audio 1> is the voice-timbre reference for <Subject 1> (S1)", prompt)
        self.assertIn("<Audio 1>: reference -", prompt)
        self.assertIn("without copying the original signal", prompt)
        self.assertIn("[reference generation + audio reference]", prompt)
        self.assertIn("matching the voice timbre referenced from <Audio 1>", prompt)
        audio_refs = [r for r in compiled["reference_images"] if r.get("type") == "audio"]
        self.assertEqual(len(audio_refs), 1)
        self.assertEqual(audio_refs[0]["audio_tag"], "<Audio 1>")
        self.assertEqual(audio_refs[0]["speaker_id"], "S1")

    def test_voice_descriptor_is_written_into_the_prompt(self):
        compiled = self._compile(self._binding())
        self.assertIn("a teenage boy with a quiet, breathy voice", compiled["h3_prompt"])

    def test_chinese_voice_spec_is_not_pasted_into_the_english_prompt(self):
        data = self.layer
        dlg = data["shots"][0]["dialogue_and_audio"]
        dlg.pop("voice_4d_spec_en", None)
        dlg["voice_4d_spec"] = "低沉的少年嗓音，語速偏慢"
        self.layer_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.sha = hashlib.sha256(self.layer_path.read_bytes()).hexdigest()
        binding = self._binding()
        binding["source_sha256"] = self.sha
        compiled = self._compile(binding)
        self.assertNotIn("低沉的少年嗓音", compiled["h3_prompt"])
        # 文件宣稱「只在 compile_notes 回報提醒」，程式必須真的回報
        self.assertTrue(
            any("voice_4d_spec_en" in n for n in compiled["compile_notes"]),
            compiled["compile_notes"],
        )

    def test_audio_reference_is_skipped_when_the_speaker_has_no_visible_mouth(self):
        data = self.layer
        data["shots"][0]["dialogue_and_audio"]["voice_4d_spec"] = "voiceover"
        data["shots"][0]["dialogue_and_audio"]["lips_closed_lock"] = True
        self.layer_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.sha = hashlib.sha256(self.layer_path.read_bytes()).hexdigest()
        binding = self._binding()
        binding["source_sha256"] = self.sha
        compiled = self._compile(binding)
        self.assertNotIn("<Audio 1>", compiled["h3_prompt"])
        self.assertEqual([r for r in compiled["reference_images"] if r.get("type") == "audio"], [])
        self.assertTrue(any("音色參考" in n for n in compiled["compile_notes"]))


if __name__ == "__main__":
    unittest.main()
