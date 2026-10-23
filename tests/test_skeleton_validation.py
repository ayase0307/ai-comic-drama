import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))
sys.path.insert(0, str(ROOT / "scripts" / "craft"))
import validate_storyboard as vs  # noqa: E402
import mccloud_review  # noqa: E402


class SkeletonValidationTest(unittest.TestCase):
    def test_wide_codes(self):
        for c in ("ELS", "LS", "MLS"):
            self.assertTrue(mccloud_review.is_wide(c))
        self.assertFalse(mccloud_review.is_wide("CU"))

    def _data(self):
        import ast
        src = (ROOT / "scripts/storyboard/validate_storyboard.py").read_text(encoding="utf-8").replace("\r\n", "\n")
        i = src.index("valid_case = {")
        j = src.index("\n    }\n", i) + 6
        return ast.literal_eval(src[i + len("valid_case = "):j].strip())

    def test_placeholder_asset_refs_warn(self):
        d = self._data()
        d["asset_refs"] = {"scene_id": "S-item1", "characters": [{"id": "C-item2", "costume_id": "TODO"}]}
        r = vs.validate_storyboard_data(d)
        self.assertTrue(any("佔位符" in w for w in r["warnings"]))

    def test_lips_lock_only_for_visible_faces(self):
        d = self._data()
        for sh in d["shots"]:
            sh["dialogue_and_audio"] = {"has_dialogue": False, "lips_closed_lock": False}
            sh["character_ids"] = []
        r = vs.validate_storyboard_data(d)
        self.assertFalse(any("閉唇鎖提醒" in w for w in r["warnings"]))


if __name__ == "__main__":
    unittest.main()
