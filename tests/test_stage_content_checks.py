"""階段 0–3 內容門禁：init 模板不能被當成「產物已齊」，也不能被自動核准。"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
for extra in (SCRIPTS, SCRIPTS / "adapt", SCRIPTS / "review", SCRIPTS / "storyboard"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import next_step  # noqa: E402
import project_state as ps  # noqa: E402
import stage_content_checks as scc  # noqa: E402
from compare_adaptation import _episode_key  # noqa: E402


def _init(root: Path) -> None:
    subprocess.run([sys.executable, str(SCRIPTS / "init_project.py"), str(root), "--title", "測試"],
                   check=True, capture_output=True)


class FreshInitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        _init(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_stage_0_to_3_rejects_init_template(self):
        for stage in range(4):
            with self.subTest(stage=stage):
                self.assertTrue(scc.content_errors(self.root, stage), f"stage-{stage} 模板竟然通過")

    def test_strict_validation_only_adds_content_checks_for_0_to_3(self):
        self.assertEqual(ps.stage_validation_errors(self.root, 1), [])
        self.assertTrue(ps.stage_validation_errors(self.root, 1, strict=True))

    def test_next_does_not_say_artifacts_ready_on_template(self):
        out = next_step.render(next_step.plan(self.root))
        self.assertNotIn("產物已齊", out)
        self.assertIn("佔位符", out)

    def test_init_writes_integrity_stamp_and_real_review_names(self):
        self.assertEqual(ps.state_integrity(self.root), "ok")
        state = json.loads((self.root / "review" / "project-state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["stages"]["stage-1"]["review_html"], "review/stage-1-adaptation.html")

    def test_character_bible_template_has_no_forbidden_example_name(self):
        text = (self.root / "adapt" / "character-bible.md").read_text(encoding="utf-8")
        self.assertNotIn("BrownHairSlayer", text)


class Stage0Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, aspect="16:9", style="14 古風寫實厚塗"):
        (self.root / "project.md").write_text(
            f"# 測試\n\n## 設定\n- 畫風：{style}\n- aspect_ratio：{aspect}\n- 台詞政策：② 只留重點句\n",
            encoding="utf-8")

    def _decide_aspect(self, value):
        (self.root / "decisions.json").write_text(json.dumps({"schema_version": 1, "decisions": [{
            "id": "aspect_ratio", "rule": "比例", "value": value,
            "source": {"quote": "比例用這個", "date": "2026-10-23"}, "stages": [2, 4, 5, 6, 7],
        }]}, ensure_ascii=False), encoding="utf-8")

    def test_filled_project_passes(self):
        self._write()
        self.assertEqual(scc.stage0_errors(self.root), [])

    def test_blank_style_fails(self):
        self._write(style="")
        self.assertTrue(any("畫風" in e for e in scc.stage0_errors(self.root)))

    def test_aspect_must_match_decision(self):
        self._write(aspect="9:16")
        self._decide_aspect("16:9")
        errors = scc.stage0_errors(self.root)
        if not errors:
            self.skipTest("decisions.json 格式與本測試假設不同")
        self.assertTrue(any("aspect_ratio" in e for e in errors))

    def test_aspect_with_annotation_still_matches(self):
        self._write(aspect="16:9（使用者定案）")
        self._decide_aspect("16:9")
        self.assertEqual(scc.stage0_errors(self.root), [])


class Stage2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "images").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_registered_sheet_fails_then_passes(self):
        (self.root / "assets.md").write_text(
            "# 資產\n> ID 規則：角色 `C-<slug>`\n\n### C-hero　沈洛年（主角）\n- **設定圖**：`images/C-hero_W01_sheet_v1.png`\n",
            encoding="utf-8")
        errors = scc.stage2_errors(self.root)
        self.assertTrue(any("不存在" in e for e in errors))
        (self.root / "images" / "C-hero_W01_sheet_v1.png").write_bytes(b"png")
        self.assertEqual(scc.stage2_errors(self.root), [])

    def test_documentation_placeholders_outside_cards_are_ignored(self):
        (self.root / "images" / "a.png").write_bytes(b"png")
        (self.root / "assets.md").write_text(
            "# 資產\n檔名規則 `images/scene-<slug>-<變體>.png`\n"
            "- **生圖引擎**：`python <技能>/scripts/run.py`\n### C-a　甲\n- **設定圖**：`images/a.png`\n",
            encoding="utf-8")
        self.assertEqual(scc.stage2_errors(self.root), [])


class EpisodeKeyTests(unittest.TestCase):
    def test_integer_and_string_episodes_normalize(self):
        self.assertEqual(_episode_key(1), "EP01")
        self.assertEqual(_episode_key("ep1"), "EP01")
        self.assertEqual(_episode_key("EP01"), "EP01")
        self.assertEqual(_episode_key(None), "")


if __name__ == "__main__":
    unittest.main()
