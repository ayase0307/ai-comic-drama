"""階段文件狀態卡與修訂紀錄（references/document-standard.md）。"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT / "scripts", ROOT / "scripts" / "adapt", ROOT / "scripts" / "storyboard"):
    sys.path.insert(0, str(extra))

import doc_card  # noqa: E402
from validate_structure import parse_and_validate_script  # noqa: E402

SCRIPT = (ROOT / "tests" / "fixtures" / "audit_fogport" / "script-ep01.md").read_text(encoding="utf-8")
T = "2026-10-27 22:40"
BODY1 = "# 分鏡" + chr(10) * 2 + "| 段 |" + chr(10)
BODY2 = "# 分鏡" + chr(10) * 2 + "| 段 | 鏡 |" + chr(10)


class DocCardTests(unittest.TestCase):
    def test_stamp_new_card_then_update_bumps_version_and_logs(self):
        text = doc_card.stamp(SCRIPT, title="霧港・階段 3 劇本・第 01 集", status="等你核准",
                              summary="林澈收到不屬於自己的信", when=T)
        card = doc_card.parse(text)["card"]
        self.assertEqual((card["status"], card["version"], card["change"]), ("等你核准", 1, "初稿"))
        text = doc_card.stamp(text, title="x", change="1-1 場縮短台詞", by="使用者：「太長」",
                              decisions=["刪回憶嗎？ 建議：接受；或：保留"], when="2026-10-28 09:00")
        doc = doc_card.parse(text)
        self.assertEqual(doc["card"]["version"], 2)
        self.assertEqual(doc["card"]["title"], "霧港・階段 3 劇本・第 01 集", "舊標題保留")
        self.assertEqual(doc["card"]["decisions"][0],
                         {"question": "刪回憶嗎？", "recommend": "接受", "alternatives": ["保留"]})
        self.assertEqual([r["version"] for r in doc["log"]], ["v2", "v1"])
        self.assertEqual(doc["body"].strip(), SCRIPT.strip(), "本體一字不動")

    def test_status_only_update_does_not_bump_version(self):
        text = doc_card.stamp(SCRIPT, title="t", summary="s", when=T)
        text = doc_card.stamp(text, title="t", status="已核准", when=T)
        doc = doc_card.parse(text)
        self.assertEqual((doc["card"]["version"], len(doc["log"])), (1, 1))

    def test_resolve_moves_decision_into_log(self):
        text = doc_card.stamp(SCRIPT, title="t", summary="s", decisions=["A？ 建議：好", "B？ 建議：不"], when=T)
        text = doc_card.resolve(text, 1, "好", "就這樣", when=T)
        doc = doc_card.parse(text)
        self.assertEqual([d["question"] for d in doc["card"]["decisions"]], ["B？"])
        self.assertIn("決定：A？ → 好", doc["log"][0]["change"])
        self.assertIn("就這樣", doc["log"][0]["by"])

    def test_frame_does_not_change_script_parsing(self):
        framed = doc_card.stamp(SCRIPT, title="t", summary="s", change="初稿", when=T)
        a, b = parse_and_validate_script(SCRIPT), parse_and_validate_script(framed)
        self.assertEqual(b["errors"], [], b["errors"])
        self.assertEqual(len(a["scenes"]), len(b["scenes"]))
        self.assertEqual([w for w in b["warnings"] if "ORPHAN" in w], [])

    def test_rejects_bad_status_and_too_many_decisions(self):
        with self.assertRaises(ValueError):
            doc_card.stamp(SCRIPT, title="t", summary="s", status="好了")
        with self.assertRaises(ValueError):
            doc_card.stamp(SCRIPT, title="t", summary="s", decisions=["a", "b", "c", "d"])

    def test_regenerate_keeps_card_and_marks_approved_as_changed(self):
        text = doc_card.stamp("# 分鏡\n\nold", title="t", summary="s", status="已核准", when=T)
        same = doc_card.regenerate(text, "# 分鏡\n\nold", title="t", summary="s", when="2026-10-29 10:00")
        self.assertEqual(same, text, "本體沒變就不動")
        new = doc_card.regenerate(text, "# 分鏡\n\nnew", title="t", summary="s", when="2026-10-29 10:00")
        doc = doc_card.parse(new)
        self.assertEqual((doc["card"]["status"], doc["card"]["version"]), ("已變更待重審", 2))
        self.assertTrue(new.startswith("# 分鏡\n\n> **t**"))

    def test_check_and_decisions_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "project.md").write_text("# 定調\n\n內容", encoding="utf-8")
            (root / "script-ep01.md").write_text(
                doc_card.stamp(SCRIPT, title="t", summary="s", decisions=["A？ 建議：好；或：不好"]), encoding="utf-8")
            self.assertEqual(len(doc_card.check(root)), 1)
            found = doc_card.doc_decisions(root)
            self.assertEqual((found[0]["stage"], found[0]["path"], found[0]["recommend"]), (3, "script-ep01.md", "好"))

    def test_cli_stamp_and_show(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "script-ep02.md"
            path.write_text(SCRIPT, encoding="utf-8")
            self.assertEqual(doc_card.main(["stamp", str(path), "--stage", "3", "--summary", "一句話"]), 0)
            card = doc_card.parse(path.read_text(encoding="utf-8"))["card"]
            self.assertTrue(card["title"].endswith("階段 3 劇本・第 02 集"))

    def test_write_generated_keeps_card_and_only_bumps_on_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "storyboard-ep01.md"
            doc_card.write_generated(path, BODY1, stage=4, summary="1 段", by="gen")
            first = path.read_text(encoding="utf-8")
            doc_card.write_generated(path, BODY1, stage=4, summary="1 段", by="gen")
            self.assertEqual(path.read_text(encoding="utf-8"), first, "本體沒變就不動")
            path.write_text(doc_card.stamp(first, title="x", status="已核准"), encoding="utf-8")
            doc_card.write_generated(path, BODY2, stage=4, summary="1 段", by="gen")
            card = doc_card.parse(path.read_text(encoding="utf-8"))["card"]
            self.assertEqual((card["status"], card["version"]), ("已變更待重審", 2))


if __name__ == "__main__":
    unittest.main()
