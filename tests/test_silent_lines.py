import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "voice"))
import voice_align  # noqa: E402


class SilentLinesTest(unittest.TestCase):
    lines = {"S1": [{"text": "歡迎來到遺忘島"}, {"text": "請跟緊我們的導遊"}], "S2": [{"text": "沒有轉寫的段落"}]}
    asr = {"S1": [{"start": 0, "end": 2, "text": "歡迎來到遺忘島"}]}

    def test_flags_unheard_line(self):
        out = voice_align.silent_lines({}, self.lines, self.asr)
        self.assertEqual([(o["segment"], o["line"]) for o in out], [("S1", "請跟緊我們的導遊")])

    def test_voiced_line_and_missing_asr_skipped(self):
        man = {"k": {"segment": "S1", "line": "請跟緊我們的導遊"}}
        self.assertEqual(voice_align.silent_lines(man, self.lines, self.asr), [])


if __name__ == "__main__":
    unittest.main()
