import sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))
SRC = (ROOT / "scripts" / "storyboard" / "validate_storyboard.py").read_text(encoding="utf-8")

class T(unittest.TestCase):
    def test_warning_and_ack_present(self):
        self.assertIn("不可逆狀態仍附場景母版", SRC)
        self.assertIn("scene_master_disabled", SRC)
        self.assertIn("continuity_handshake", SRC)

if __name__ == "__main__":
    unittest.main()
