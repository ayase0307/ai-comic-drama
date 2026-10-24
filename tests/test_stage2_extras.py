import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_stage_review as bsr  # noqa: E402


class Stage2ExtrasTest(unittest.TestCase):
    def test_extras_cards_are_collected_separately_from_creatures(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "assets.md").write_text(
                "## 角色\n\n### CREATURE-bug　甲蟲（異獸）\n- **設定圖**：`images/creature-bug.png`\n\n"
                "### EXTRAS-crowd　弟子群（群演）\n- **設定圖**：`images/extras-crowd.png`\n\n## 場景\n",
                encoding="utf-8")
            self.assertEqual([c["id"] for c in bsr.collect_creatures(root)], ["CREATURE-bug"])
            extras = bsr.collect_creatures(root, "EXTRAS")
            self.assertEqual([(c["id"], c["name"], c["image"]) for c in extras],
                             [("EXTRAS-crowd", "弟子群", "images/extras-crowd.png")])


if __name__ == "__main__":
    unittest.main()
