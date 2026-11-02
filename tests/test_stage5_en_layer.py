"""階段 5 英文層（噩盡島 #49–53）：

#49 Layer 2 只有 shot_id 也能套 stage5 綁定（記憶體補 global_shot_id，不改檔）
#50 中文運鏡對到官方動詞；movement_en／en_overlay 優先
#51 中文欄位不再原樣進英文提示詞；E15 對編譯器的開頭也會觸發
#52 閉唇句只加在「看得到臉且不說話」的鏡
#53 只出聲的角色不寫外觀；段落專用描述取代角色聖經外觀
"""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "scripts", ROOT / "scripts" / "storyboard", ROOT / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import compile_layer2_to_h3 as compiler  # noqa: E402
from audit_refs_and_segments import lint_h3_prompt  # noqa: E402
import test_h3_compiler  # noqa: E402  （只借 fixture；不 import 類別名，避免被 discover 重跑）


def _fixture():
    """借用既有編譯器測試的 registry 與 segment 骨架。"""
    f = test_h3_compiler.H3CompilerRegressionTests("test_cut_marker_tokens_are_opt_in")
    f.setUp()
    return f


def _detailed(prompt: str) -> str:
    """只回 [Shot N] 行，一行一鏡。"""
    block = prompt.split("detailed_description:\n", 1)[1].split("\n\noverall_soundscape:", 1)[0]
    return "\n".join(line for line in block.split("\n") if line.startswith("[Shot"))


class CameraMotionTests(unittest.TestCase):
    def test_chinese_movements_map_to_official_verbs(self):
        cases = {
            "穩定短推，保持單一主體": "dollies in",
            "鏡頭緩慢拉遠露出全景": "dollies out",
            "由下往上仰搖到天空": "tilts up",
            "撞擊瞬間手持晃動": "handheld",
            "跟拍洛年奔跑": "tracks",
            "固定機位": "static",
        }
        for raw, verb in cases.items():
            with self.subTest(raw=raw):
                self.assertIn(verb, compiler.map_camera_motion(raw))

    def test_unknown_chinese_movement_points_to_movement_en(self):
        with self.assertRaises(ValueError) as ctx:
            compiler.map_camera_motion("詩意地呼吸")
        self.assertIn("movement_en", str(ctx.exception))

    def test_movement_en_wins_over_chinese_movement(self):
        f = _fixture()
        data = f.segment()
        data["shots"][0]["camera_optics"]["movement"] = "詩意地呼吸"
        data["shots"][0]["camera_optics"]["movement_en"] = "dolly in"
        compiled = f.compile(data)
        self.assertIn("dollies in", _detailed(compiled["h3_prompt"]).split("\n")[0])


class ChineseFieldTests(unittest.TestCase):
    def test_chinese_blocking_anchor_continuity_and_end_state_stay_out(self):
        f = _fixture()
        data = f.segment()
        data["style_lock"]["continuity_anchors"]["axis"] = "洛年始終在桌子東側"
        data["segment_end_state"]["planned_final_state"] = {"米拉": "左手握著信"}
        for shot in data["shots"]:
            shot["spatial_blocking"]["blocking_desc"] = "米拉站在桌子東側"
            shot["spatial_blocking"]["anchor_objects"] = ["桌子", "west window"]
        compiled = f.compile(data)
        prompt = compiled["h3_prompt"]
        self.assertNotRegex(prompt.replace("<d>", "").split("<d>")[0], r"[\u4e00-\u9fff]")
        self.assertIn("anchor objects: west window", prompt)
        notes = " ".join(compiled.get("compile_notes") or [])
        self.assertIn("blocking_desc 是中文", notes)
        self.assertIn("segment_end_state 是中文", notes)

    def test_e15_triggers_on_compiler_opening(self):
        f = _fixture()
        prompt = f.compile()["h3_prompt"]
        leaked = prompt.replace("Mira folds the map", "米拉把地圖摺好放在桌上然後轉身")
        result = lint_h3_prompt(leaked, nominal_duration=9.0)
        self.assertTrue(any("E15" in e for e in result["errors"]), result["errors"])


class LipsTests(unittest.TestCase):
    def test_lips_clause_only_when_a_visible_face_is_silent(self):
        f = _fixture()
        data = f.segment()
        data["shots"][0]["character_ids"] = ["C-MIRA"]
        data["shots"][1]["character_ids"] = []          # 空景
        data["shots"][2]["character_ids"] = ["C-MIRA"]
        data["shots"][2]["dialogue_and_audio"]["lips_closed_lock"] = False  # 張嘴嘶吼
        data["shots"][1]["dialogue_and_audio"].pop("lips_closed_lock", None)
        lines = _detailed(f.compile(data)["h3_prompt"]).split("\n")
        self.assertIn("lips stay closed", lines[0])
        self.assertNotIn("lips stay closed", lines[1])
        self.assertNotIn("lips stay closed", lines[2])

    def test_overlay_lips_omit_wins(self):
        data = {"shots": [{"global_shot_id": "A", "dialogue_and_audio": {"lips_closed_lock": True}}]}
        compiler._apply_en_shot(data["shots"][0], {"lips": "omit"})
        self.assertFalse(compiler._lips_closed_wanted(data["shots"][0], compiler.AssetRegistry(), set()))


class VoiceOnlyTests(unittest.TestCase):
    def test_voice_only_secondary_is_not_described(self):
        f = _fixture()
        f.registry.characters["C-BIRD"] = {
            "id": "C-BIRD", "name": "Bird", "desc_en": "a colossal crimson bird with burning wings",
            "short_en": "a colossal crimson bird", "desc_zh": "", "ref_img": "", "wardrobe_states": {},
            "is_creature": True, "no_visual_reference": True,
        }
        data = f.segment()
        data["asset_refs"]["characters"].append({"id": "C-BIRD"})
        data["asset_refs"]["no_visual_reference_ids"] = ["C-BIRD"]
        data["shots"][1]["character_ids"] = ["C-MIRA", "C-BIRD"]
        prompt = f.compile(data)["h3_prompt"]
        self.assertNotIn("burning wings", prompt)

    def test_segment_specific_description_replaces_bible_look(self):
        f = _fixture()
        f.registry.characters["C-BIRD"] = {
            "id": "C-BIRD", "name": "Bird", "desc_en": "a colossal crimson bird with burning wings",
            "short_en": "a colossal crimson bird", "desc_zh": "", "ref_img": "", "wardrobe_states": {},
            "is_creature": True,
        }
        data = f.segment()
        data["asset_refs"]["characters"].append({"id": "C-BIRD"})
        data["shots"][1]["character_ids"] = ["C-MIRA", "C-BIRD"]
        data["_secondary_desc_en"] = {"C-BIRD": "a vast pulse of red light with no readable shape"}
        prompt = f.compile(data)["h3_prompt"]
        self.assertNotIn("burning wings", prompt)
        self.assertIn("a vast pulse of red light", prompt)


class GlobalShotIdTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "layer2").mkdir()
        f = _fixture()
        self.layer = f.segment()
        self.layer["segment_id"] = "EP01-S01"
        for shot in self.layer["shots"]:
            shot.pop("global_shot_id", None)
        self.path = self.root / "layer2" / "layer2-EP01-S01.json"
        self.path.write_text(json.dumps(self.layer, ensure_ascii=False), encoding="utf-8")
        sha = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.binding = {
            "segment_id": "EP01-S01", "source_layer2_path": "layer2/layer2-EP01-S01.json", "source_sha256": sha,
            "shots": [{"global_shot_id": s["shot_id"], "reference_paths": {}} for s in self.layer["shots"]],
            "en_overlay": {
                "shots": {"S1": {"movement_en": "dolly in", "blocking_en": "Mira stands east of the table.", "lips": "omit"}},
                "continuity_anchors_en": {"axis": "Mira stays east of the table"},
                "end_state_en": {"Mira": "holds the letter"},
            },
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_binding_validates_and_applies_without_global_shot_id_in_file(self):
        data = json.loads(self.path.read_text(encoding="utf-8"))
        compiler.validate_stage5_binding(data, self.binding, self.path, self.root)
        applied = compiler.apply_stage5_binding(json.loads(self.path.read_text(encoding="utf-8")), self.binding)
        shot = applied["shots"][0]
        self.assertEqual(shot["global_shot_id"], "S1")
        self.assertEqual(shot["camera_optics"]["movement_en"], "dolly in")
        self.assertEqual(shot["dialogue_and_audio"]["lips_mode"], "omit")
        self.assertEqual(applied["style_lock"]["continuity_anchors_en"]["axis"], "Mira stays east of the table")
        self.assertEqual(applied["segment_end_state"]["planned_final_state_en"], {"Mira": "holds the letter"})
        # 檔案沒被動到
        self.assertNotIn("global_shot_id", self.path.read_text(encoding="utf-8"))

    def test_legacy_x_en_overlay_name_is_accepted(self):
        binding = copy.deepcopy(self.binding)
        binding["x_en_overlay"] = binding.pop("en_overlay")
        applied = compiler.apply_stage5_binding(json.loads(self.path.read_text(encoding="utf-8")), binding)
        self.assertEqual(applied["shots"][0]["camera_optics"]["movement_en"], "dolly in")

    def test_overlay_rejects_bad_lips_value(self):
        binding = copy.deepcopy(self.binding)
        binding["en_overlay"]["shots"]["S1"]["lips"] = "maybe"
        data = json.loads(self.path.read_text(encoding="utf-8"))
        with self.assertRaises(ValueError):
            compiler.validate_stage5_binding(data, binding, self.path, self.root)


class EnOverlayOverrideTests(unittest.TestCase):
    """階段 5 binding 的 en_overlay 覆寫：五小節逐節、可見度豁免、段落風格錨。

    規格：docs/research/briefs/2026-11-02-wip-landing-plan.opus.md §2 PR③。
    """

    FIVE = {"camera": "35mm from two metres at her eye height, static.",
            "motion": "She lifts the cup, then sets it down.",
            "performance": "Her jaw tightens once.",
            "light": "Cold window light from camera left.",
            "sound": "Cup clicks on wood at about 1.1 s."}

    def test_overlay_replaces_only_the_named_part(self):
        shot = {"shot_id": "S1", "action_and_performance": {"five_part_en": dict(self.FIVE)}}
        compiler._apply_en_shot(shot, {"five_part_en": {"motion": "He steps back, then turns away."}})
        after = shot["action_and_performance"]["five_part_en"]
        self.assertEqual(after["motion"], "He steps back, then turns away.")
        for key in ("camera", "performance", "light", "sound"):
            self.assertEqual(after[key], self.FIVE[key])

    def test_single_container_when_shot_already_has_five_part(self):
        shot = {"shot_id": "S1", "five_part_en": dict(self.FIVE)}
        compiler._apply_en_shot(shot, {"five_part_en": {"light": "Amber lamp from the right."}})
        self.assertEqual(shot["five_part_en"]["light"], "Amber lamp from the right.")
        self.assertNotIn("action_and_performance", shot)

    def test_overlay_rejects_unknown_part_and_bad_values(self):
        shot = {"shot_id": "S1", "action_and_performance": {"five_part_en": dict(self.FIVE)}}
        with self.assertRaises(ValueError):
            compiler._apply_en_shot(shot, {"five_part_en": {"music": "none"}})
        with self.assertRaises(ValueError):
            compiler._apply_en_shot(shot, {"five_part_en": {"motion": "   "}})
        with self.assertRaises(ValueError):
            compiler._apply_en_shot(shot, {"five_part_en": "Motion: x"})
        with self.assertRaises(ValueError):
            compiler._apply_en_shot(shot, {"offscreen_subject_ids": "C-MIRA"})

    def test_visibility_override_lists_are_string_arrays(self):
        shot = {"shot_id": "S1"}
        compiler._apply_en_shot(shot, {"offscreen_subject_ids": [" C-BEN "],
                                      "accepted_unbound_subject_ids": ["C-ANA"]})
        self.assertEqual(shot["offscreen_subject_ids"], ["C-BEN"])
        self.assertEqual(shot["accepted_unbound_subject_ids"], ["C-ANA"])

    def test_offscreen_override_exempts_subject_coverage_e40(self):
        from prompt_authoring import audit_subject_coverage
        f = _fixture()
        f.registry.characters["C-BIRD"] = {
            "id": "C-BIRD", "name": "Bird", "desc_en": "a vast crimson bird", "short_en": "a crimson bird",
            "desc_zh": "", "ref_img": "", "wardrobe_states": {}, "is_creature": True,
        }
        data = f.segment()
        data["shots"][1]["character_ids"] = ["C-MIRA", "C-BIRD"]   # 沒掛參考圖 → E40
        compiled = f.compile(data)
        self.assertTrue(any("E40" in e for e in audit_subject_coverage(compiled)), audit_subject_coverage(compiled))
        compiler._apply_en_shot(compiled["shots"][1], {"offscreen_subject_ids": ["C-BIRD"]})
        self.assertEqual([e for e in audit_subject_coverage(compiled) if "E40" in e], [])

    def test_cast_lock_drops_offscreen_actor(self):
        f = _fixture()
        for cid, name in (("C-ANA", "Ana"), ("C-BEN", "Ben")):
            f.registry.characters[cid] = {
                "id": cid, "name": name, "desc_en": f"{name}, grey coat", "short_en": name,
                "desc_zh": "", "ref_img": f"assets/characters/{cid}.png",
                "wardrobe_states": {}, "is_creature": False,
            }
        data = f.segment()
        data["metadata"]["cast_lock"] = True
        data["asset_refs"]["characters"] = [{"id": "C-MIRA"}, {"id": "C-ANA"}, {"id": "C-BEN"}]
        for shot in data["shots"]:
            shot["character_ids"] = ["C-MIRA", "C-ANA", "C-BEN"]
        self.assertIn("three people", f.compile(copy.deepcopy(data))["h3_prompt"])
        for shot in data["shots"]:
            shot["offscreen_subject_ids"] = ["C-BEN"]
        prompt = f.compile(copy.deepcopy(data))["h3_prompt"]
        self.assertIn("two people", prompt)
        self.assertNotIn("Ben", prompt.split("Cast rule:")[1].split(";")[0])

    def test_binding_offscreen_end_to_end(self):
        """從 `stage5_binding.en_overlay.shots` 一路寫到 shot，E40 的豁免真的吃到（不是直接改 Layer 2）。

        註：這裡不跑 `compile_segment_h3`——fixture 的 binding 沒有 `reference_paths`，帶 binding 編譯會（正確地）
        擋「has no approved reference image」。E40／人數鎖的完整編譯效果由另外兩支測試覆蓋。
        """
        from prompt_authoring import shot_entities
        f = _fixture()
        for cid, name in (("C-ANA", "Ana"), ("C-BEN", "Ben")):
            f.registry.characters[cid] = {
                "id": cid, "name": name, "desc_en": f"{name}, grey coat", "short_en": name,
                "desc_zh": "", "ref_img": f"assets/characters/{cid}.png",
                "wardrobe_states": {}, "is_creature": False,
            }
        data = f.segment()
        data["metadata"]["cast_lock"] = True
        data["asset_refs"]["characters"] = [{"id": "C-MIRA"}, {"id": "C-ANA"}]   # C-BEN 沒掛參考圖
        for shot in data["shots"]:
            shot["character_ids"] = ["C-MIRA", "C-ANA", "C-BEN"]

        binding = {"segment_id": data["segment_id"], "shots": [], "en_overlay": {"shots": {}}}
        for shot in data["shots"]:
            key = shot.get("global_shot_id") or shot.get("shot_id")
            binding["en_overlay"]["shots"][key] = {"offscreen_subject_ids": ["C-BEN"]}
        applied = compiler.apply_stage5_binding(copy.deepcopy(data), binding)
        self.assertEqual(applied["shots"][0]["offscreen_subject_ids"], ["C-BEN"])   # binding 真的寫進 shot
        self.assertNotIn("C-BEN", shot_entities(applied["shots"][0]))               # E40 的豁免吃得到
        self.assertIn("C-BEN", applied["shots"][0]["character_ids"])                # 沒改 Layer 2 的選角

    def test_style_anchor_en_overrides_segment_anchor(self):
        data = _fixture().segment()
        compiler._apply_en_segment(data, {"style_anchor_en": "bold oil painting, amber rim light"})
        self.assertEqual(data["style_lock"]["anchor"], "bold oil painting, amber rim light")


if __name__ == "__main__":
    unittest.main()
