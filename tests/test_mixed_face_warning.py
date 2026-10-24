import sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))
import validate_storyboard as v

SRC = (ROOT / "scripts" / "storyboard" / "validate_storyboard.py").read_text(encoding="utf-8")

class T(unittest.TestCase):
    def test_check_present_with_ack(self):
        self.assertIn("同段多說話人露臉", SRC)
        self.assertIn("accepted_mixed_face", SRC)
        self.assertTrue(hasattr(v, "count_speech_chars"))
