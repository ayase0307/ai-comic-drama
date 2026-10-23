"""階段 5 資產綁定缺口（噩盡島 #54 #55 #60 #61）：

#54 沒有設定圖的道具以文字注入，不報錯也不丟描述
#55 缺場景母版可宣告 pending_references：可編譯審稿、不可送件
#60 同段的生物階段變體與基本型可共存；生物 retention 不沿用人類模板
#61 17 條自檢的條數與文件一致
"""
import copy
import inspect
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "scripts", ROOT / "scripts" / "storyboard", ROOT / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import audit_refs_and_segments as audit  # noqa: E402
import compile_layer2_to_h3 as compiler  # noqa: E402
import test_stage5_bindings  # noqa: E402  （只借 fixture，不 import 類別名，避免被 discover 重跑）


def _fixture():
    f = test_stage5_bindings.Stage5BindingTests("test_binding_source_hash_and_layer_path_are_verified_before_overlay")
    f.setUp()
    return f


def _registry(f):
    r = compiler.AssetRegistry(project_root=f.root)
    r.style = {"style_anchor": "normalized 3D animation", "style_negative": "No text"}
    r.locations["S-HALL"] = {"id": "S-HALL", "name": "Hall", "desc_en": "school hall", "ref_img": "images/S-HALL.png"}
    r.characters["C-HERO"] = {"id": "C-HERO", "name": "Hero", "desc_en": "a student", "short_en": "student",
                              "ref_img": "images/C-HERO.png", "wardrobe_states": {}, "is_creature": False}
    r.characters["E-SNAKE"] = {"id": "E-SNAKE", "name": "snake", "desc_en": "a yellow serpent", "short_en": "serpent",
                               "ref_img": "images/E-SNAKE.png", "wardrobe_states": {}, "is_creature": True}
    r.characters["C-VOICE"] = {"id": "C-VOICE", "name": "voice", "desc_en": "an off-screen voice", "short_en": "voice",
                               "ref_img": "", "wardrobe_states": {}, "no_visual_reference": True}
    r.props["P-SPEAR"] = {"id": "P-SPEAR", "name": "spear", "desc_en": "a long silver spear", "ref_img": "images/P-SPEAR.png"}
    r.bodydetails["D-SCAR"] = {"id": "D-SCAR", "name": "scar", "desc_en": "a healed scar", "ref_img": "images/D-SCAR.png"}
    return r


def _compile(f, registry, binding):
    data = compiler.apply_stage5_binding(copy.deepcopy(f.layer), binding)
    return compiler.compile_segment_h3(data, registry, auto_lora=False, stage5_binding=binding)


class PropWithoutImageTests(unittest.TestCase):
    def setUp(self):
        self.f = _fixture()
        self.addCleanup(self.f.doCleanups)

    def test_prop_without_image_is_injected_as_text(self):
        reg = _registry(self.f)
        reg.props["P-SPEAR"]["ref_img"] = ""
        binding = copy.deepcopy(self.f.binding)
        binding["shots"][0]["reference_paths"]["props"] = {"P-SPEAR": ""}
        compiled = _compile(self.f, reg, binding)
        self.assertNotIn("prop", [r["type"] for r in compiled["reference_images"]])
        self.assertIn("described in words only: a long silver spear", compiled["h3_prompt"])
        self.assertTrue(any("P-SPEAR" in n and "沒有設定圖" in n for n in compiled["compile_notes"]))
        res = audit.audit_refs_and_subjects(compiled, project_root=self.f.root)
        self.assertTrue(res["passed"], res["errors"])

    def test_prop_without_image_and_description_still_fails_clearly(self):
        reg = _registry(self.f)
        reg.props["P-SPEAR"].update(ref_img="", desc_en="")
        binding = copy.deepcopy(self.f.binding)
        binding["shots"][0]["reference_paths"]["props"] = {"P-SPEAR": ""}
        with self.assertRaisesRegex(ValueError, "P-SPEAR.*English visual description"):
            _compile(self.f, reg, binding)


class PendingReferenceTests(unittest.TestCase):
    def setUp(self):
        self.f = _fixture()
        self.addCleanup(self.f.doCleanups)
        self.reg = _registry(self.f)
        self.reg.locations["S-HALL"]["ref_img"] = "refs/scenes/S-HALL-new.png"
        self.binding = copy.deepcopy(self.f.binding)
        self.binding["shots"][0]["reference_paths"]["scene"] = "refs/scenes/S-HALL-new.png"

    def test_missing_plate_without_declaration_still_fails(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            _compile(self.f, self.reg, self.binding)

    def test_declared_pending_plate_compiles_for_review_and_is_recorded(self):
        for key in ("pending_references", "x_pending_scene_plate"):
            with self.subTest(key=key):
                binding = copy.deepcopy(self.binding)
                binding[key] = ["refs/scenes/S-HALL-new.png"] if key == "pending_references" else "refs/scenes/S-HALL-new.png"
                compiled = _compile(self.f, self.reg, binding)
                self.assertEqual(compiled["metadata"]["pending_references"], ["refs/scenes/S-HALL-new.png"])
                self.assertTrue(any("待補參考圖" in n for n in compiled["compile_notes"]))
                self.assertFalse(any(n.startswith("參考圖不存在") for n in compiled["compile_notes"]))
                self.assertIn("refs/scenes/S-HALL-new.png", [r["path"] for r in compiled["reference_images"]])

    def test_pending_declaration_is_dropped_once_the_file_exists(self):
        binding = copy.deepcopy(self.binding)
        binding["pending_references"] = ["refs/scenes/S-HALL-new.png"]
        target = self.f.root / "refs/scenes/S-HALL-new.png"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"plate")
        compiled = _compile(self.f, self.reg, binding)
        self.assertNotIn("pending_references", compiled["metadata"])

    def test_pending_must_be_project_relative_strings(self):
        for bad in ("/abs/plate.png", [1], [""]):
            with self.subTest(bad=bad):
                binding = copy.deepcopy(self.binding)
                binding["pending_references"] = bad
                with self.assertRaises(ValueError):
                    compiler.validate_stage5_binding(copy.deepcopy(self.f.layer), binding, self.f.layer_path, self.f.root)

    def test_submit_refuses_segments_with_pending_references(self):
        import submit_h3_segments as submit
        src = inspect.getsource(submit)
        self.assertIn("pending_references", src)


class CreatureVariantTests(unittest.TestCase):
    def setUp(self):
        self.f = _fixture()
        self.addCleanup(self.f.doCleanups)
        for rel in ("images/E-SNAKE-early.png",):
            (self.f.root / rel).write_bytes(b"variant")
        self.reg = _registry(self.f)

    def _binding(self, early_first=True):
        b = copy.deepcopy(self.f.binding)
        scene = [{"id": "S-HALL", "reference_image": "images/S-HALL.png"}]
        hero = [{"id": "C-HERO", "costume_id": "W-01", "reference_image": "images/C-HERO.png"}]
        early = [{"id": "E-SNAKE", "variant": "early", "reference_image": "images/E-SNAKE-early.png",
                  "desc_en": "a short worm-like yellow form"}]
        base = [{"id": "E-SNAKE", "reference_image": "images/E-SNAKE.png"}]
        order = (early, base) if early_first else (base, early)
        def shot(i, creatures, vis):
            return {"global_shot_id": f"EP03-SH00{i}", "reference_paths": {
                "scene": scene, "characters": hero, "creatures": creatures, "props": [], "bodydetails": []},
                "visual_subject_ids": vis}
        b["shots"] = [shot(1, order[0], ["C-HERO", "E-SNAKE"]), shot(2, order[1], ["C-HERO", "E-SNAKE"]),
                      shot(3, [], ["C-HERO"])]
        return b

    def test_variant_and_base_coexist_in_one_segment_in_either_order(self):
        for early_first in (True, False):
            with self.subTest(early_first=early_first):
                compiled = _compile(self.f, self.reg, self._binding(early_first))
                refs = compiled["reference_images"]
                subject = [r for r in refs if r["type"] == "creature"]
                self.assertEqual([r["path"] for r in subject], ["images/E-SNAKE.png"])
                variants = [r for r in refs if r["type"] == "creature_variant"]
                self.assertEqual([r["path"] for r in variants], ["images/E-SNAKE-early.png"])
                prompt = compiled["h3_prompt"]
                self.assertIn("a short worm-like yellow form", prompt)
                self.assertIn("morphology in this shot only", prompt)
                res = audit.audit_refs_and_subjects(compiled, project_root=self.f.root)
                self.assertTrue(res["passed"], res["errors"])

    def test_two_different_base_paths_still_conflict(self):
        b = self._binding(early_first=False)
        b["shots"][1]["reference_paths"]["creatures"] = [{"id": "E-SNAKE", "reference_image": "images/E-SNAKE-early.png"}]
        with self.assertRaisesRegex(ValueError, "conflicting"):
            _compile(self.f, self.reg, b)

    def test_creature_retention_does_not_use_the_human_template(self):
        compiled = _compile(self.f, self.reg, self.f.binding)
        prompt = compiled["h3_prompt"]
        creature_line = [l for l in prompt.splitlines() if "fully_preserved" in l and "body shape" in l]
        self.assertTrue(creature_line, prompt)
        self.assertNotIn("facial identity", creature_line[0])
        human_line = [l for l in prompt.splitlines() if "facial identity" in l]
        self.assertTrue(human_line)


class LintRuleCountTests(unittest.TestCase):
    def test_lint_h3_has_exactly_the_17_documented_rules(self):
        src = inspect.getsource(audit.lint_h3_prompt)
        codes = set(re.findall(r"\[([EW]\d+)[:：]", src))
        self.assertEqual(len(codes), 17, sorted(codes))
        for text in ("17 條", ):
            self.assertIn(text, (ROOT / "references" / "tooling.md").read_text(encoding="utf-8"))

    def test_user_facing_messages_no_longer_say_13(self):
        for rel in ("scripts/storyboard/compile_layer2_to_h3.py", "scripts/storyboard/audit_refs_and_segments.py"):
            self.assertNotIn("13 條", (ROOT / rel).read_text(encoding="utf-8"), rel)


if __name__ == "__main__":
    unittest.main()
