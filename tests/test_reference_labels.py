import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))
import compile_layer2_to_h3 as C  # noqa: E402
import audit_refs_and_segments as A  # noqa: E402


class ReferenceLabelTests(unittest.TestCase):
    def test_speaker_ids_align_with_subject_numbers(self):
        ids = {"a": "S1", "b": "S2", "c": "S3"}
        self.assertEqual(C._align_speaker_ids(ids, ["b", "x", "c"]), {"b": "S1", "c": "S3", "a": "S4"})

    def test_on_screen_sentence_groups_and_modes(self):
        subs = [(1, "a", 2), (2, "b", 3), (3, "c", 4)]
        s = C._on_screen_sentence({"a": "face", "b": "back", "c": "back"}, subs)
        self.assertIn("<Subject 1>: face visible, from <Picture 2>", s)
        self.assertIn("<Subject 2>, <Subject 3>: back to camera", s)
        self.assertEqual(C._on_screen_sentence({}, subs), "")
        self.assertIn("only the right hand, face out of frame",
                      C._on_screen_sentence({"a": "part:the right hand"}, subs[:1]))
        with self.assertRaises(ValueError):
            C._on_screen_sentence({"a": "bogus"}, subs)

    def test_show_is_an_allowed_shot_override(self):
        self.assertIn("show", C.SHOW_MODES and C.SHOT_OVERRIDE_KEYS)

    def test_audit_source_has_consistency_and_onscreen_exclusion(self):
        src = (ROOT / "scripts/storyboard/audit_refs_and_segments.py").read_text(encoding="utf-8")
        self.assertIn("說話者代號不一致", src)
        self.assertIn("On screen:", src)


if __name__ == "__main__":
    unittest.main()
