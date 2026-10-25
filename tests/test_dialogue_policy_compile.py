"""dialogue_policy 定案必須真正進到編譯：next_step 指令帶 --narration-policy，編譯器對衝突／對不上的值報錯。"""
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


def _write_decision(root: Path, value: str) -> None:
    entry = {"id": "dialogue_policy", "rule": "測試用台詞政策", "value": value, "stages": [3, 5, 7],
             "source": {"quote": "測試原話", "date": "2026-10-25"}}
    (root / "decisions.json").write_text(
        json.dumps({"schema_version": 1, "decisions": [entry]}, ensure_ascii=False), encoding="utf-8")


class NarrationPolicyOfTests(unittest.TestCase):
    def test_undecided_returns_none(self):
        self.assertIsNone(decisions.narration_policy_of(decisions.empty_decisions()))

    def test_blank_value_is_treated_as_undecided(self):
        data = {"decisions": [{"id": "dialogue_policy", "value": ""}]}
        self.assertIsNone(decisions.narration_policy_of(data))

    def test_each_compiler_policy_name_maps_to_itself(self):
        for name in decisions.NARRATION_POLICY_NAMES:
            data = {"decisions": [{"id": "dialogue_policy", "value": name}]}
            self.assertEqual(decisions.narration_policy_of(data), name)

    def test_unmapped_chinese_option_raises_explicitly(self):
        data = {"decisions": [{"id": "dialogue_policy", "value": "②"}]}
        with self.assertRaises(ValueError) as ctx:
            decisions.narration_policy_of(data)
        self.assertIn("無法對應", str(ctx.exception))


class ResolveNarrationPolicyTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_flag_and_no_decision_uses_default(self):
        self.assertEqual(compiler.resolve_narration_policy(None, self.root), compiler.DEFAULT_NARRATION_POLICY)

    def test_decision_is_used_when_flag_omitted(self):
        _write_decision(self.root, "external")
        self.assertEqual(compiler.resolve_narration_policy(None, self.root), "external")

    def test_matching_flag_and_decision_is_accepted(self):
        _write_decision(self.root, "h3-native")
        self.assertEqual(compiler.resolve_narration_policy("h3-native", self.root), "h3-native")

    def test_conflicting_flag_and_decision_raises(self):
        _write_decision(self.root, "external")
        with self.assertRaises(ValueError) as ctx:
            compiler.resolve_narration_policy("short-offscreen-h3", self.root)
        self.assertIn("衝突", str(ctx.exception))

    def test_unmapped_decision_raises_instead_of_falling_back(self):
        _write_decision(self.root, "④")
        with self.assertRaises(ValueError):
            compiler.resolve_narration_policy(None, self.root)


class Stage5NextStepTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_next_compile_command_carries_decided_policy(self):
        _write_decision(self.root, "external")
        cmd, _ = next_step.stage5_producer(self.root, [])
        self.assertIn("--narration-policy external", cmd)

    def test_next_compile_command_without_decision_has_no_flag(self):
        cmd, _ = next_step.stage5_producer(self.root, [])
        self.assertNotIn("--narration-policy", cmd)

    def test_unmapped_decision_points_to_decide_instead_of_compile(self):
        _write_decision(self.root, "②")
        cmd, action = next_step.stage5_producer(self.root, [])
        self.assertIn("decide dialogue_policy", cmd)
        self.assertNotIn("compile", cmd)
        self.assertIn("無法對應", action)


if __name__ == "__main__":
    unittest.main()
