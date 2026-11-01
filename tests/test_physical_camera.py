"""物理機位（R2）、施力因果鏈＋Forbidden（R3）、可選人數／環境鎖（R4）與送件端字元上限（2026-11-02）。

來源：X @LoveUolanda H3 寫法，噩盡島 EP01 A/B 盲評 2 seed（甩 1/2→2/2、插入鏡跑位錯 1.0→0、運鏡 +0.5～1.0；
R4 中性、R1 未驗、R5 弱正向只進文件）。守富更正：實際送件是家機本地，沒有 hosted 7000 字元上限。
"""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))
sys.path.insert(0, str(ROOT / "tests"))

import _remix_fixture as fx  # noqa: E402
import audit_refs_and_segments as audit  # noqa: E402
import decisions  # noqa: E402
import physical_camera as pc  # noqa: E402
import prompt_authoring  # noqa: E402
from test_remix_compile import RemixProject  # noqa: E402


MARK = {"text": "【動作2.3】巨獸咬住他的左前臂。", "seconds": 2.3}  # 劇本【動作】鏡＝source_action＋action_mark（PR #124）


def _shot(**kw):
    base = {"shot_id": "SH01", "camera_optics": {"shot_size": "MS"},
            "action_and_performance": {}, "dialogue_and_audio": {"has_dialogue": False}}
    for k, v in kw.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k] = {**base[k], **v}
        else:
            base[k] = v
    return base


class RigTests(unittest.TestCase):
    def test_angle_keywords_map_to_height_and_axis(self):
        cases = {
            ("Low-angle side close-up at ground level", "約 1.5m 低角度"): "a real camera 1.5 m away, lens just above the ground, optical axis tilted up",
            ("Top-down medium shot from directly above the head", "約 3m 正俯"): "a real camera 3 m away, lens directly overhead, optical axis straight down",
            ("Low-angle shot looking straight up from beside his head", "約 1m 仰拍"): "a real camera 1 m away, lens at ground level, optical axis straight up",
            ("Medium close-up of him at eye level", "約 2m"): "a real camera 2 m away, lens at eye height, optical axis level",
            ("Close-up of his face from slightly above", "約 1m 微俯"): "a real camera 1 m away, lens above eye line, optical axis tilted down",
            ("Medium two-shot from the entrance", "2.5m"): "a real camera 2.5 m away",
        }
        for (cam, dist), want in cases.items():
            self.assertEqual(pc.derive_rig(cam, dist), want, cam)
        self.assertEqual(pc.derive_rig("Medium shot", ""), "")

    def test_rig_replaces_duplicated_lens_distance_clause(self):
        cam = "Low-angle side close-up at ground level, 50mm from one and a half metres, locked off; he lies at frame left."
        out = pc.camera_with_rig(cam, {"physical_distance": "約 1.5m 低角度"}, "1.5m")
        self.assertNotIn("50mm from", out)
        self.assertIn("a real camera 1.5 m away, lens just above the ground, optical axis tilted up, locked off;", out)
        self.assertTrue(out.endswith("he lies at frame left."))

    def test_authored_rig_wins(self):
        cam = "Insert, 35mm from four metres, locked off; the ledge sits upper centre."
        out = pc.camera_with_rig(cam, {"rig_en": "the camera stands 4 m in front of the boulder, lens 1 m high."}, "4m")
        self.assertIn("Insert, the camera stands 4 m in front of the boulder, lens 1 m high, locked off;", out)
        obj = {"rig": {"position_en": "4 m in front of them", "height_en": "lens 1.6 m high", "axis_en": "optical axis level"}}
        self.assertEqual(pc.authored_rig(obj), "4 m in front of them, lens 1.6 m high, optical axis level")
        self.assertEqual(pc.authored_rig({"rig_en": "相機在前方四米"}), "")  # 中文不進英文提示詞

    def test_authored_rig_with_path_drops_contradicting_locked_off(self):
        cam = "Side-on medium shot at ground level, 35mm from five metres, locked off; the beast at frame right."
        rig = "lens 50 cm high, locked off while the beast grips, then it tilts up on the release"
        out = pc.camera_with_rig(cam, {"rig_en": rig}, "5m")
        self.assertEqual(out, "Side-on medium shot at ground level, " + rig + "; the beast at frame right.")

    def test_rig_inserted_after_first_clause_when_no_lens_clause(self):
        self.assertEqual(pc.apply_rig("Wide shot of the hall; she enters.", "a real camera 6 m away"),
                         "Wide shot of the hall, a real camera 6 m away; she enters.")


class ActionTests(unittest.TestCase):
    def test_action_mark_gets_default_forbidden_without_semicolons(self):
        s = _shot(source_action=True, action_mark=MARK)
        items = pc.forbidden_items(s, "", "the beast jerks its head up")
        self.assertEqual(items, pc.DEFAULT_ACTION_FORBIDDEN)
        line = pc.forbidden_sentence(items)
        self.assertTrue(line.startswith("Forbidden: ") and ";" not in line and line.endswith("."))

    def test_authored_forbidden_replaces_defaults_dedup_and_capped(self):
        s = _shot(source_action=True, action_mark=MARK, action_and_performance={
            "forbidden_en": ["he does not rise by himself; no second beast", "no second beast",
                             "no bite on his head", "the fangs do not pass through the arm", "he does not climb out", "the beast jerks only once"]})
        items = pc.forbidden_items(s, "", "")
        self.assertEqual(items[:2], ["he does not rise by himself", "no second beast"])
        self.assertEqual(len(items), pc.MAX_FORBIDDEN_ITEMS)
        self.assertFalse(any("self-levitating" in i for i in items))  # 作者寫了就不補語意重疊的預設

    def test_explicit_empty_forbidden_disables_defaults(self):
        s = _shot(source_action=True, action_mark=MARK, action_and_performance={"forbidden_en": []})
        self.assertEqual(pc.forbidden_items(s, "", "jerks"), [])

    def test_hand_insert_gets_framing_and_insert_forbidden(self):
        s = _shot(dialogue_and_audio={"has_dialogue": True, "line_verbatim": "前面"})
        five = {"camera": "The same low insert framing as the boulder before, locked off",
                "motion": "First his index finger touches the ledge, then it slides to the tip."}
        out = pc.apply_action_rules(five, s)
        self.assertIn("only the hand and forearm enter frame", out["camera"])
        self.assertIn("Forbidden: no full-body entry when only the hand is framed", out["motion"])
        self.assertNotIn("self-levitating", out["motion"])  # 有台詞的插入鏡不是動作鏡

    def test_dialogue_or_gaze_only_shots_get_nothing(self):
        talk = _shot(dialogue_and_audio={"has_dialogue": True, "line_verbatim": "不像。"})
        self.assertEqual(pc.forbidden_items(talk, "", "she grabs his sleeve"), [])
        glance = _shot()
        self.assertEqual(pc.forbidden_items(glance, "", "first she flicks her eyes down, then her eyebrows lift"), [])
        silent_hit = _shot()
        self.assertTrue(pc.forbidden_items(silent_hit, "", "the paw slams down onto his chest"))

    def test_source_action_without_mark_is_not_action_shot(self):
        # PR #124 實測：v118 #9 的【建立】【停頓】鏡只標 source_action；和 validate D5 同一判定，不當【動作】鏡
        est = _shot(source_action=True)
        self.assertFalse(pc.is_action_shot(est, "the crater rim sits quietly under the noon sun"))
        self.assertEqual(pc.forbidden_items(est, "", "the crater rim sits quietly under the noon sun"), [])
        self.assertTrue(pc.is_action_shot(_shot(source_action=True, action_mark=MARK), ""))

    def test_force_chain_replaces_motion(self):
        s = _shot(source_action=True, action_mark=MARK, action_and_performance={"force_chain_en": [
            "the beast's neck lowers first", "its jaws drop the last half metre", "its fangs clamp his forearm"]})
        out = pc.apply_action_rules({"camera": "Close-up", "motion": "old motion text"}, s)
        self.assertTrue(out["motion"].startswith("Force chain: the beast's neck lowers first, then its jaws drop"))
        self.assertNotIn("old motion", out["motion"])


class CastLockTests(unittest.TestCase):
    def test_trigger_rules(self):
        self.assertTrue(pc.cast_lock_wanted({"shots": []}, 3))
        self.assertFalse(pc.cast_lock_wanted({"shots": []}, 2))
        self.assertTrue(pc.cast_lock_wanted({"metadata": {"cast_lock": True}, "shots": []}, 1))
        self.assertFalse(pc.cast_lock_wanted({"metadata": {"cast_lock": False}, "shots": []}, 5))
        gone = {"shots": [{"spatial_blocking": {"absent_objects_en": ["the shattered lamp"]}}]}
        self.assertTrue(pc.cast_lock_wanted(gone, 1))
        self.assertEqual(pc.absent_objects_en({"metadata": {"absent_objects": ["石燈", "the old cart"]}, "shots": []}),
                         ["the old cart"])

    def test_text(self):
        txt = pc.cast_environment_lock(["A", "B", "C"], ["the white beast"], False, ["the cart"])
        self.assertIn("Cast rule: exactly three people, A, B and C, and exactly one creature, the white beast;", txt)
        self.assertIn("Environment lock: stay in this one location from <Picture 1>, with only the objects already in it; not in frame: the cart.", txt)
        self.assertNotIn("Cast rule", pc.cast_environment_lock(["A", "B", "C"], [], True, []))


class CompileIntegrationTests(RemixProject):
    def _layer2(self):
        doc = fx.layer2_doc()
        sh2 = doc["shots"][1]
        sh2["source_action"] = True
        sh2["action_mark"] = {"text": "【動作】葉薇珊停步，賴一心指向地面。"}
        return doc

    def test_law_once_lock_auto_and_authoring_clean(self):
        self.make()
        seg = self.compile()
        prompt = seg["h3_prompt"]
        self.assertEqual(prompt.count("Camera law:"), 1)
        self.assertIn("Cast rule: exactly three people, Shen Luonian, Lai Yixin and Ye Weishan;", prompt)
        # 總則與鎖放在介紹句之後、第 1 鏡鏡頭句之前
        self.assertLess(prompt.index("<Video 3> is"), prompt.index("Camera law:"))
        self.assertLess(prompt.index("Camera law:"), prompt.index("The shot opens on"))
        self.assertIn("a real camera 4 m away, lens at eye height, optical axis level", prompt)
        res = prompt_authoring.audit_segment(prompt, seg["shots"], seg["segment_id"])
        self.assertEqual(res["errors"], [])

    def test_action_shot_chain_forbidden_and_w50(self):
        doc = self._layer2()
        self.make(layer2=doc)
        seg = self.compile()
        self.assertIn("Forbidden: no self-levitating, no unmotivated displacement, no repeating the same action.",
                      seg["h3_prompt"])
        res = prompt_authoring.audit_segment(seg["h3_prompt"], seg["shots"], seg["segment_id"])
        self.assertEqual(res["errors"], [])
        self.assertTrue(any(w.startswith("[W50") for w in res["warnings"]))

        doc2 = copy.deepcopy(doc)
        doc2["shots"][1]["action_and_performance"]["force_chain_en"] = (
            "first Ye Weishan's foot plants beside Lai Yixin, then her weight settles onto it as she stops, "
            "then Lai Yixin's free left arm swings down to point at the ground between them")
        doc2["metadata"]["cast_lock"] = False
        doc2["metadata"]["camera_law"] = False
        self.make(layer2=doc2)
        seg2 = self.compile(layer2=doc2)
        p2 = seg2["h3_prompt"]
        self.assertIn("Motion: Force chain: first Ye Weishan's foot plants", p2)
        self.assertNotIn("Cast rule", p2)
        self.assertNotIn("Camera law", p2)
        res2 = prompt_authoring.audit_segment(p2, seg2["shots"], seg2["segment_id"])
        self.assertEqual(res2["errors"], [])
        self.assertFalse(any(w.startswith("[W50") for w in res2["warnings"]))

    def test_new_text_has_a_budget(self):
        """新增文字要有預算：總則 ≤300、每鏡機位句 ≤130、Forbidden 句 ≤220、人數＋環境鎖 ≤420 字元。"""
        self.assertLessEqual(len(pc.CAMERA_LAW_EN), 300)
        self.assertLessEqual(len(pc.derive_rig("Low-angle side close-up at ground level", "約 12.5m")), 130)
        longest = pc.forbidden_sentence(pc.DEFAULT_INSERT_FORBIDDEN + pc.DEFAULT_ACTION_FORBIDDEN)
        self.assertLessEqual(len(longest), 220)
        lock = pc.cast_environment_lock(["the island guide", "the straw-hat actress", "the black-haired actress"],
                                        [], False, [])
        self.assertLessEqual(len(lock), 420)
        self.make()
        doc_off = fx.layer2_doc()
        doc_off["metadata"].update({"camera_law": False, "cast_lock": False})
        self.make(layer2=doc_off)
        off = self.compile(layer2=doc_off)["h3_prompt"]
        self.make()
        on = self.compile()["h3_prompt"]
        self.assertLessEqual(len(on) - len(off), 300 + 420 + 2 * 130)


class SubmitEndpointTests(unittest.TestCase):
    def test_decision_default_local_and_hosted(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(decisions.submit_endpoint(root), "local")
            self.assertEqual(audit.resolve_submit_endpoint(root), "local")
            decisions.decide(root, "submit_endpoint", "hosted", "這批改送平台 API")
            self.assertEqual(decisions.submit_endpoint(root), "hosted")
            self.assertEqual(audit.resolve_submit_endpoint(root), "hosted")
            self.assertEqual(audit.resolve_submit_endpoint(root, "local"), "local")  # CLI 參數優先
            self.assertEqual(decisions.parse_value("submit_endpoint", "家機"), "local")
            data = decisions.load(root)
            data["decisions"][-1]["value"] = "cloud"
            self.assertTrue(any("submit_endpoint" in e for e in decisions.validate(data)))

    def test_local_long_prompt_passes_compile_lint(self):
        prompt = "detailed_description: " + " ".join(["word"] * 10) + "x" * 7300
        self.assertFalse(any("字元超過上限" in e for e in audit.lint_h3_prompt(prompt, 15.0)["errors"]))
        self.assertTrue(any("字元超過上限" in e
                            for e in audit.lint_h3_prompt(prompt, 15.0, submit_endpoint="hosted")["errors"]))


if __name__ == "__main__":
    unittest.main()
