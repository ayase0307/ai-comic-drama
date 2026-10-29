"""docs/skill-roadmap.html 內嵌的路線資料要跟真實 CLI 對得上，避免流程改了圖沒跟著改。"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import decisions  # noqa: E402
import h3d  # noqa: E402

PAGE = ROOT / "docs" / "skill-roadmap.html"


def load_data():
    text = PAGE.read_text(encoding="utf-8")
    match = re.search(r'<script type="application/json" id="roadmap-data">(.*?)</script>', text, re.S)
    return json.loads(match.group(1))


class SkillRoadmapTests(unittest.TestCase):
    def setUp(self):
        self.data = load_data()

    def test_version_matches_skill(self):
        self.assertEqual(self.data["version"], (ROOT / "VERSION").read_text(encoding="utf-8").strip())

    def test_all_eight_stages_in_order(self):
        self.assertEqual([s["n"] for s in self.data["stages"]], list(range(8)))
        for stage in self.data["stages"]:
            self.assertTrue(stage["steps"] and stage["human"] and stage["files"] and stage["gates"], stage["name"])

    def test_every_h3d_subcommand_is_listed_and_none_invented(self):
        listed = {c[0] for c in self.data["commands"]}
        self.assertEqual(listed, set(h3d.COMMANDS))

    def test_referenced_scripts_and_commands_exist(self):
        for stage in self.data["stages"]:
            for step in stage["steps"]:
                for path in re.findall(r"scripts/[\w/]+\.py", step["cmd"]):
                    self.assertTrue((ROOT / path).is_file(), f"階段 {stage['n']} 引用不存在的腳本 {path}")
                for sub in re.findall(r"h3d (\w+)", step["cmd"]):
                    self.assertIn(sub, h3d.COMMANDS, f"階段 {stage['n']} 引用不存在的 h3d {sub}")

    def test_always_human_stages_are_marked(self):
        pinned = {s["n"] for s in self.data["stages"] if "user" in s["pins"]}
        self.assertTrue(set(decisions.NEVER_AUTO_STAGES) <= pinned)

    def test_delivery_scopes_match_presets(self):
        scopes = {s["id"]: s["end"] for s in self.data["scopes"]}
        self.assertEqual(scopes, {k: v["end_stage"] for k, v in decisions.DELIVERY_PRESETS.items()})


if __name__ == "__main__":
    unittest.main()
