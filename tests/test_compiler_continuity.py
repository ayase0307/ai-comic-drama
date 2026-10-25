"""#133 #138 #139：段間終態帶入、相鄰段姿勢矛盾、無文字句、同場光線鎖。"""
import copy
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))

import compile_layer2_to_h3 as compiler  # noqa: E402
import continuity_lint  # noqa: E402

from tests import test_h3_compiler as _h3  # noqa: E402


class _Base(_h3.H3CompilerRegressionTests):
    """借用既有編譯器 fixture；不重跑父類別的測試。"""


for _name in [n for n in dir(_h3.H3CompilerRegressionTests) if n.startswith("test_")]:
    setattr(_Base, _name, None)


class ContinuityLintUnitTests(unittest.TestCase):
    def test_previous_segment_map_stays_within_scene_and_sorts_suffix(self):
        prev = continuity_lint.previous_segment_map([
            ("EP01-S02-b", "S02"), ("EP01-S02-a", "S02"), ("EP01-S02-aa", "S02"),
            ("EP01-S02-z", "S02"), ("EP01-S03-a", "S03"),
        ])
        self.assertEqual(prev["EP01-S02-b"], "EP01-S02-a")
        self.assertEqual(prev["EP01-S02-aa"], "EP01-S02-z")  # aa 排在 z 之後
        self.assertNotIn("EP01-S03-a", prev)  # 跨場景不帶入
        self.assertNotIn("EP01-S02-a", prev)

    def test_english_end_state_skips_chinese(self):
        self.assertEqual(continuity_lint.english_end_state({"planned_final_state": {"米拉": "坐著"}}), {})
        self.assertEqual(
            continuity_lint.english_end_state({"planned_final_state": {"米拉": "坐著"},
                                               "planned_final_state_en": {"Mira": "sits slumped"}}),
            {"Mira": "sits slumped"})

    def test_carry_sentence_is_positive(self):
        text = continuity_lint.carry_sentence({"Shen": "lies on his back, pinned under the rock."})
        self.assertIn("Starting state carried over from the previous segment: Shen lies on his back", text)
        self.assertNotRegex(text, r"\b(no|not|never)\b")

    def test_no_lettering_triggers(self):
        self.assertTrue(continuity_lint.needs_no_lettering("navy blazer with a shield crest"))
        self.assertTrue(continuity_lint.needs_no_lettering("a yellow taxi stops"))
        self.assertTrue(continuity_lint.needs_no_lettering("a mottled concrete wall"))
        self.assertFalse(continuity_lint.needs_no_lettering("a quiet room with a west-facing window"))

    def _seg(self, sid, first_shot, end_state=None, scene="S02", lock="warm dusk light"):
        return {
            "segment_id": sid, "scene_id": scene,
            "h3_prompt": f"detailed_description:\nheader\n[Shot 1] {first_shot}\n[Shot 2] later.\n\noverall_soundscape:\n",
            "segment_end_state": end_state,
            "metadata": {"lighting_lock_line": lock},
        }

    def test_posture_contradiction_warns_unless_rise_is_written(self):
        a = self._seg("EP01-S02-c", "x", {"planned_final_state_en": {"Shen": "lies sprawled on the ground"}})
        b = self._seg("EP01-S02-d", "MS of Shen. Shen stands by the wall and looks up.")
        res = continuity_lint.lint_adjacent([a, b])
        self.assertTrue(any("[C2" in w and "EP01-S02-d" in w for w in res["warnings"]), res)
        b_ok = self._seg("EP01-S02-d", "MS of Shen. Shen pushes himself up from the ground and stands.")
        res = continuity_lint.lint_adjacent([a, b_ok])
        self.assertFalse(any("[C2" in w for w in res["warnings"]), res)

    def test_carry_sentence_itself_does_not_count_as_first_shot_posture(self):
        a = self._seg("EP01-S02-c", "x", {"planned_final_state_en": {"Shen": "stands at the rail"}})
        b = self._seg("EP01-S02-d", "MS. Starting state carried over from the previous segment: Shen lies flat. Shen sits up.")
        self.assertEqual(continuity_lint.lint_adjacent([a, b])["warnings"], [])

    def test_missing_previous_end_state_warns(self):
        a = self._seg("EP01-S02-c", "x", None)
        b = self._seg("EP01-S02-d", "Shen looks up.")
        res = continuity_lint.lint_adjacent([a, b])
        self.assertTrue(any("[C1" in w for w in res["warnings"]), res)

    def test_split_lighting_lock_within_scene_warns(self):
        st = {"planned_final_state_en": {"Shen": "crouches"}}
        a = self._seg("EP03-S02-a", "x", st, scene="ALLEY", lock="warm golden dusk")
        b = self._seg("EP03-S02-b", "Shen crouches.", st, scene="ALLEY", lock="neutral white daylight")
        c = self._seg("EP03-S03-a", "x", st, scene="ROOF", lock="neutral white daylight")
        res = continuity_lint.lint_adjacent([a, b, c])
        c3 = [w for w in res["warnings"] if "[C3" in w]
        self.assertEqual(len(c3), 1, res)
        self.assertIn("ALLEY", c3[0])


class ShotLintTests(unittest.TestCase):
    def _c(self, shot):
        return [{"segment_id": "A", "h3_prompt": f"detailed_description:\n[Shot 1] {shot}\n\noverall:"}]

    def test_multi_action_and_missing_end_state(self):
        w = continuity_lint.lint_shots(self._c("MS (50mm, 2m) of Shen, as the camera holds. He turns, then runs, then jumps. Blocking: a road."))["warnings"]
        self.assertTrue(any("[S1" in x for x in w) and any("[S2" in x for x in w), w)

    def test_clean_action_shot(self):
        w = continuity_lint.lint_shots(self._c("MS (50mm, 2m) of Shen. He runs, then ends crouched at the rail. Blocking: a road."))["warnings"]
        self.assertEqual(w, [])

    def test_dialogue_shot_rules(self):
        bad = continuity_lint.lint_shots(self._c("MS (50mm, 2m) of Shen, as the camera dollies in. Shen is the visible speaking character: <d>hi</d>"))["warnings"]
        self.assertEqual(sorted(x.split("[")[1][:2] for x in bad), ["S3", "S4", "S5"], bad)
        ok = continuity_lint.lint_shots(self._c("CU (85mm, 1.2m) of Shen, as the camera holds a static shot. Shen is the visible speaking character: <d>hi</d> Blocking: the background behind him is empty."))["warnings"]
        self.assertEqual(ok, [])


class CompilerContinuityTests(_Base):
    def test_previous_end_state_is_injected_into_first_shot_only(self):
        compiled = compiler.compile_segment_h3(
            copy.deepcopy(self.segment()), registry=self.registry, auto_lora=False,
            previous_end_state={"planned_final_state_en": {"Mira": "sits slumped against the door"}},
        )
        prompt = compiled["h3_prompt"]
        shot1 = prompt.split("[Shot 1]")[1].split("[Shot 2]")[0]
        self.assertIn("Starting state carried over from the previous segment: Mira sits slumped against the door.", shot1)
        self.assertEqual(prompt.count("Starting state carried over"), 1)
        self.assertTrue(compiled["metadata"].get("carried_end_state"))

    def test_chinese_previous_end_state_is_not_written_and_noted(self):
        compiled = compiler.compile_segment_h3(
            copy.deepcopy(self.segment()), registry=self.registry, auto_lora=False,
            previous_end_state={"planned_final_state": {"米拉": "癱坐"}},
        )
        self.assertNotIn("Starting state carried over", compiled["h3_prompt"])
        self.assertTrue(any("沒有英文終態" in n for n in compiled["compile_notes"]))

    def test_no_previous_state_keeps_prompt_unchanged(self):
        base = self.compile()
        self.assertNotIn("Starting state carried over", base["h3_prompt"])
        self.assertNotIn("carried_end_state", base["metadata"])

    def test_no_lettering_sentence_added_only_for_trigger_words(self):
        plain = self.compile()
        self.assertNotIn("no lettering", plain["h3_prompt"])
        self.assertEqual(plain["metadata"]["lighting_lock_line"].lower().startswith("blue moonlight"), True)
        data = self.segment()
        self.registry.characters["C-MIRA"]["desc_en"] = "Mira, short black hair, navy blazer with a shield crest"
        crest = self.compile(data)
        header = crest["h3_prompt"].split("detailed_description:\n")[1].split("[Shot 1]")[0]
        self.assertIn("with no lettering, no logos and no graffiti", header)
        self.assertTrue(crest["metadata"].get("no_lettering_added"))
        data["metadata"]["allow_lettering"] = True
        allowed = self.compile(data)
        self.assertNotIn("no lettering", allowed["h3_prompt"])

    def test_cli_carries_end_state_from_sibling_layer2_and_check_warns(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            first = self.five_part_segment()
            first["segment_id"] = "EP01-S01-a"
            first["segment_end_state"] = {"planned_final_state_en": {"Mira": "lies on the floor beside the table"}}
            second = self.five_part_segment()
            second["segment_id"] = "EP01-S01-b"
            second["shots"][0]["action_and_performance"]["five_part_en"]["motion"] = (
                "First Mira stands beside the table, then she walks to the window, as the curtain sways, "
                "finally she stops with one hand on the sill.")
            (root / "layer2-EP01-S01-a.json").write_text(json.dumps(first, ensure_ascii=False), encoding="utf-8")
            (root / "layer2-EP01-S01-b.json").write_text(json.dumps(second, ensure_ascii=False), encoding="utf-8")
            out = root / "segments.json"
            argv = [
                "compile_layer2_to_h3.py", "--layer2", str(root / "layer2-EP01-S01-b.json"), "--skip-stage-gate",
                "--project-root", str(root), "--output-segments", str(out), "--check", "--no-auto-lora",
            ]
            buf = StringIO()
            with patch.object(sys, "argv", argv), redirect_stdout(buf), redirect_stderr(buf):
                status = compiler.main()
            self.assertEqual(status, 0, buf.getvalue())
            seg = json.loads(out.read_text(encoding="utf-8"))["segments"][0]
            self.assertIn("Mira lies on the floor beside the table", seg["h3_prompt"])
            self.assertIn("[C2: 段間姿勢矛盾]", buf.getvalue())

            argv.insert(-1, "--no-carry-end-state")
            buf = StringIO()
            with patch.object(sys, "argv", argv), redirect_stdout(buf), redirect_stderr(buf):
                status = compiler.main()
            self.assertEqual(status, 0, buf.getvalue())
            seg = json.loads(out.read_text(encoding="utf-8"))["segments"][0]
            self.assertNotIn("Starting state carried over", seg["h3_prompt"])


if __name__ == "__main__":
    unittest.main()


class FutureBlockingAnchorTests(unittest.TestCase):
    def test_regex_flags_future_words(self):
        self.assertTrue(continuity_lint.FUTURE_BLOCKING_RE.search("later both stand at the guardrail"))
        self.assertFalse(continuity_lint.FUTURE_BLOCKING_RE.search("two figures stand apart at the rail"))
