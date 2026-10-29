"""dialogue_policy 定案必須真正進到編譯：④ 對應 external，①②③ 與空值沿用預設，無法辨識的值明確報錯。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))

import decisions  # noqa: E402
import next_step  # noqa: E402
import compile_layer2_to_h3 as compiler  # noqa: E402

UNRECOGNIZED = "只留重點句（自由文字）"


def _write_decision(root: Path, value: str) -> None:
    entry = {"id": "dialogue_policy", "rule": "測試用台詞政策", "value": value, "stages": [3, 5, 7],
             "source": {"quote": "測試原話", "date": "2026-10-25"}}
    (root / "decisions.json").write_text(
        json.dumps({"schema_version": 1, "decisions": [entry]}, ensure_ascii=False), encoding="utf-8")


def _policy(value: str):
    return decisions.narration_policy_of({"decisions": [{"id": "dialogue_policy", "value": value}]})


class NarrationPolicyOfTests(unittest.TestCase):
    def test_undecided_returns_none(self):
        self.assertIsNone(decisions.narration_policy_of(decisions.empty_decisions()))

    def test_blank_value_is_treated_as_undecided(self):
        self.assertIsNone(_policy(""))
        self.assertIsNone(_policy("   "))

    def test_each_compiler_policy_name_maps_to_itself(self):
        for name in decisions.NARRATION_POLICY_NAMES:
            self.assertEqual(_policy(name), name)

    def test_choice_4_pure_narration_maps_to_external(self):
        self.assertEqual(_policy("④"), "external")
        self.assertEqual(_policy("④ 無台詞純旁白"), "external")

    def test_choices_1_2_3_do_not_change_compilation(self):
        for value in ("①", "②", "③", "② 只留重點句", "③ 影視化改寫"):
            self.assertIsNone(_policy(value), value)

    def test_unrecognized_value_raises_explicitly(self):
        with self.assertRaises(ValueError) as ctx:
            _policy(UNRECOGNIZED)
        self.assertIn("無法辨識", str(ctx.exception))


class ResolveNarrationPolicyTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_flag_and_no_decision_uses_default(self):
        self.assertEqual(compiler.resolve_narration_policy(None, self.root), compiler.DEFAULT_NARRATION_POLICY)

    def test_neutral_choice_uses_default(self):
        _write_decision(self.root, "②")
        self.assertEqual(compiler.resolve_narration_policy(None, self.root), compiler.DEFAULT_NARRATION_POLICY)

    def test_choice_4_is_used_when_flag_omitted(self):
        _write_decision(self.root, "④")
        self.assertEqual(compiler.resolve_narration_policy(None, self.root), "external")

    def test_decision_name_is_used_when_flag_omitted(self):
        _write_decision(self.root, "external")
        self.assertEqual(compiler.resolve_narration_policy(None, self.root), "external")

    def test_matching_flag_and_decision_is_accepted(self):
        _write_decision(self.root, "h3-native")
        self.assertEqual(compiler.resolve_narration_policy("h3-native", self.root), "h3-native")

    def test_explicit_flag_is_accepted_with_neutral_choice(self):
        _write_decision(self.root, "①")
        self.assertEqual(compiler.resolve_narration_policy("external", self.root), "external")

    def test_conflicting_flag_and_decision_raises(self):
        _write_decision(self.root, "external")
        with self.assertRaises(ValueError) as ctx:
            compiler.resolve_narration_policy("short-offscreen-h3", self.root)
        self.assertIn("衝突", str(ctx.exception))

    def test_choice_4_conflicts_with_default_flag(self):
        _write_decision(self.root, "④")
        with self.assertRaises(ValueError):
            compiler.resolve_narration_policy("short-offscreen-h3", self.root)

    def test_unrecognized_decision_raises_instead_of_falling_back(self):
        _write_decision(self.root, UNRECOGNIZED)
        with self.assertRaises(ValueError):
            compiler.resolve_narration_policy(None, self.root)


class Stage5NextStepTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_choice_4_compile_command_carries_external(self):
        _write_decision(self.root, "④")
        cmd, _ = next_step.stage5_producer(self.root, [])
        self.assertIn("--narration-policy external", cmd)

    def test_policy_name_compile_command_carries_flag(self):
        _write_decision(self.root, "h3-native")
        cmd, _ = next_step.stage5_producer(self.root, [])
        self.assertIn("--narration-policy h3-native", cmd)

    def test_neutral_choice_still_prints_compile_command_without_flag(self):
        _write_decision(self.root, "②")
        cmd, _ = next_step.stage5_producer(self.root, [])
        self.assertIn("compile --layer2", cmd)
        self.assertNotIn("--narration-policy", cmd)

    def test_without_decision_has_no_flag(self):
        cmd, _ = next_step.stage5_producer(self.root, [])
        self.assertNotIn("--narration-policy", cmd)

    def test_unrecognized_decision_points_to_decide_instead_of_compile(self):
        _write_decision(self.root, UNRECOGNIZED)
        cmd, action = next_step.stage5_producer(self.root, [])
        self.assertIn("decide dialogue_policy", cmd)
        self.assertNotIn("compile", cmd)
        self.assertIn("無法辨識", action)


if __name__ == "__main__":
    unittest.main()
