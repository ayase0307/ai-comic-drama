import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "adapt"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))
import estimate_duration as ed  # noqa: E402

SCRIPT = """第1集｜測試

1-1 舊屋 日/內
△ 沈洛年站在窗邊。
沈洛年：你來了。
沈洛年（V.O.）：我其實一直都在等這一天到來。
"""


class EstimateVoTests(unittest.TestCase):
    def test_voiceover_not_counted_as_h3_speech(self):
        r = ed.estimate_script_duration(SCRIPT, genre_mode="drama", h3_mode=True)
        self.assertGreater(r["voiceover_chars_excluded"], 0)
        self.assertEqual(r["h3_speech_seconds"], round(ed.count_spoken_chars("你來了。") / 4.0, 1))


if __name__ == "__main__":
    unittest.main()
