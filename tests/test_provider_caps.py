"""Provider 能力表校驗（I4）：measured 才硬擋，未驗證的只警告。"""
import tempfile
import unittest
from pathlib import Path

from scripts.storyboard import h3_spec, provider_caps


class CapabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.caps = provider_caps.load_caps()

    def test_default_caps_load_and_describe(self):
        text = provider_caps.describe(self.caps)
        self.assertIn("17n+5", text)
        self.assertIn("fps", text)

    def test_caps_match_h3_spec_constants(self):
        self.assertEqual(provider_caps.consistency_warnings(self.caps), [])

    def test_frames_outside_range_only_warns_because_source_is_docs(self):
        verdict = provider_caps.validate_segment({}, self.caps, frames=400)
        self.assertFalse(verdict["errors"])
        self.assertTrue(any("400" in item for item in verdict["warnings"]))

    def test_known_aspects_are_not_blocked(self):
        # layer2 schema 與 verify 都支援這些比例，caps 不可誤擋
        for aspect in ("16:9", "9:16", "2.39:1", "1:1", "4:3"):
            verdict = provider_caps.validate_segment({}, self.caps, aspect=aspect)
            self.assertEqual(verdict["errors"], [], aspect)

    def test_unknown_aspect_warns(self):
        verdict = provider_caps.validate_segment({}, self.caps, aspect="3:2")
        self.assertFalse(verdict["errors"])
        self.assertTrue(any("3:2" in item for item in verdict["warnings"]))

    def test_docs_backed_reference_limit_only_warns(self):
        verdict = provider_caps.validate_segment({}, self.caps, reference_count=9)
        self.assertFalse(verdict["errors"])
        self.assertTrue(verdict["warnings"])

    def test_assumed_audio_limit_only_warns(self):
        verdict = provider_caps.validate_segment({}, self.caps, audio_count=3)
        self.assertFalse(verdict["errors"])
        self.assertTrue(any("音訊" in item for item in verdict["warnings"]))

    def test_assumed_lora_limit_only_warns(self):
        verdict = provider_caps.validate_segment({}, self.caps, lora_count=9)
        self.assertFalse(verdict["errors"])
        self.assertTrue(verdict["warnings"])

    def test_measured_field_is_hard_blocked(self):
        caps = dict(self.caps)
        caps["aspects"] = {"value": ["16:9"], "source": "measured"}
        verdict = provider_caps.validate_segment({}, caps, aspect="9:16")
        self.assertTrue(verdict["errors"])

    def test_consistency_check_catches_drift(self):
        caps = dict(self.caps)
        caps["frames"] = {"min": 100, "max": 400, "source": "docs"}
        problems = provider_caps.consistency_warnings(caps)
        self.assertTrue(any("min" in item for item in problems))
        self.assertTrue(any("max" in item for item in problems))

    def test_missing_caps_file_is_a_capability_error(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            with self.assertRaises(provider_caps.CapabilityError):
                provider_caps.load_caps("nope", Path(td))

    def test_malformed_caps_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            path = Path(td) / "bad.json"
            path.write_text("{oops", encoding="utf-8")
            with self.assertRaises(provider_caps.CapabilityError):
                provider_caps.load_caps("bad", Path(td))


if __name__ == "__main__":
    unittest.main()
