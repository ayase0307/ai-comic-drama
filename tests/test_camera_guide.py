import re, sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))
import camera_moves


PLANNED_15B = set()


class CameraGuideTests(unittest.TestCase):
    def test_guide_presets_exist(self):
        text = (ROOT / "references" / "camera-moves-guide.md").read_text(encoding="utf-8")
        for name in set(re.findall(r"\b[a-z]+(?:_[a-z0-9]+)+\b", text)):
            if name in ("move_preset", "camera_optics", "move_lint", "shot_intent", "choice_why"):
                continue
            if name in PLANNED_15B:  # 15b 補 preset 前，指南先列名
                continue
            self.assertIn(name, camera_moves.PRESETS, name)

    def test_skill_links_guide(self):
        self.assertIn("camera-moves-guide.md", (ROOT / "SKILL.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
