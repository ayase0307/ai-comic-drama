"""h3d verdict --prefill：階段 6 逐段結論的預填草稿（只預填、不代簽）。"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))

import decisions  # noqa: E402
import verdicts  # noqa: E402

QUOTE = "照預填走，有問題的段我再逐段看"


def qa_item(sid, passed=True, issues=None, sheet=None):
    item = {"segment_id": sid, "passed": passed, "issues": issues or []}
    if sheet:
        item["contact_sheet_file"] = str(sheet)
    return item


class VerdictPrefillTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "videos" / "qa").mkdir(parents=True)
        self.sheet = self.root / "videos" / "qa" / "tile.jpg"
        self.sheet.write_bytes(b"jpg")

    def _qa_report(self, results, expected=None):
        path = self.root / "videos" / "qa-report.json"
        path.write_text(json.dumps({"expected_segments": expected or [], "results": results},
                                   ensure_ascii=False), encoding="utf-8")

    def _prefill_file(self):
        return json.loads((self.root / "review" / "verdict-prefill.json").read_text(encoding="utf-8"))

    def _verdicts_file(self):
        return json.loads((self.root / "review" / "verdicts.json").read_text(encoding="utf-8"))

    def test_prefill_draft_from_qa_and_recorded_verdicts(self):
        decisions.decide(self.root, "acceptance_policy", "recommended", "照建議")
        # 有結論的段：E-SOFT 是 agent 判 warn（含技術 QA 的低彩度代碼）
        verdicts.set_verdict(self.root, "E-SOFT", "warn", "低彩度場景，可接受",
                             ["videos/qa/tile.jpg"], issues=["low_chroma"])
        self._qa_report(
            [qa_item("E-HARD", False, ["DURATION_MISMATCH: 實際比預期長 0.7s"], self.sheet),
             qa_item("E-SOFT", False, ["STYLE_BLEED_GRAYSCALE: 彩度過低"], self.sheet)],
            expected=["E-HARD", "E-SOFT", "E-NOQA"],
        )
        draft = verdicts.build_prefill(self.root)

        self.assertTrue(draft["policy_decided"])
        self.assertEqual(draft["note"], "預填草稿，不是結論；--apply 前不會寫進 verdicts.json")
        self.assertTrue(draft["generated_at"])
        rows = {row["segment_id"]: row for row in draft["prefill"]}

        hard = rows["E-HARD"]
        self.assertEqual(hard["verdict"], "fail")
        self.assertEqual(hard["basis"], "qa")
        self.assertIn("DURATION_MISMATCH", hard["reason"])
        self.assertEqual(hard["issues"], [])           # 硬錯誤原文不是政策代碼
        self.assertEqual(hard["evidence"], ["videos/qa/tile.jpg"])

        soft = rows["E-SOFT"]
        self.assertEqual(soft["verdict"], "warn")
        self.assertEqual(soft["basis"], "recorded")
        self.assertEqual(soft["issues"], ["low_chroma"])
        self.assertEqual(soft["evidence"], ["videos/qa/tile.jpg"])

        self.assertEqual(self._prefill_file(), draft)

    def test_apply_writes_user_verdicts_with_quote_and_keeps_user_decisions(self):
        decisions.decide(self.root, "acceptance_policy", "recommended", "照建議")
        # 使用者已判過的段：--apply 不覆寫
        verdicts.set_verdict(self.root, "E-USER", "pass", "導演看過，過",
                             ["videos/qa/tile.jpg"], decided_by="user")
        self._qa_report([qa_item("E-HARD", False, ["DURATION_MISMATCH: 差 0.7s"], self.sheet),
                         qa_item("E-USER", True, [], self.sheet)],
                        expected=["E-HARD", "E-USER"])

        written, skipped = verdicts.apply_prefill(self.root, QUOTE)

        self.assertEqual(written, ["E-HARD"])
        self.assertEqual([sid for sid, _ in skipped], ["E-USER"])
        data = self._verdicts_file()
        self.assertEqual(verdicts.validate(data), [])
        hard = data["segments"]["E-HARD"]
        self.assertEqual(hard["decided_by"], "user")
        self.assertEqual(hard["verdict"], "fail")
        self.assertTrue(hard["reason"].startswith("[預填] "))
        self.assertIn(QUOTE, hard["reason"])
        self.assertNotIn("video_sha256", hard)        # 沒有影片檔就不綁 hash
        user = data["segments"]["E-USER"]
        self.assertEqual(user["reason"], "導演看過，過")
        self.assertEqual(user["verdict"], "pass")

    def test_prefill_skips_segments_without_qa_or_verdict(self):
        decisions.decide(self.root, "acceptance_policy", "recommended", "照建議")
        self._qa_report([qa_item("E-OK", True, ["STYLE_BLEED_GRAYSCALE: 偏灰"], self.sheet)],
                        expected=["E-OK", "E-NOQA"])
        draft = verdicts.build_prefill(self.root)
        self.assertEqual([row["segment_id"] for row in draft["prefill"]], [])
        self.assertEqual(draft["skipped_unreviewed"], 2)

    def test_policy_not_decided_is_flagged(self):
        self._qa_report([qa_item("E-HARD", False, ["ASPECT_RATIO_MISMATCH: 9:16 ≠ 16:9"], self.sheet)],
                        expected=["E-HARD"])
        draft = verdicts.build_prefill(self.root)
        self.assertFalse(draft["policy_decided"])
        self.assertEqual(draft["prefill"][0]["verdict"], "fail")

    def test_cli_prefill_prints_table_and_apply_requires_quote(self):
        self._qa_report([qa_item("E-HARD", False, ["DURATION_MISMATCH: 差 0.7s"], self.sheet)],
                        expected=["E-HARD"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(verdicts.main(["--prefill", "--root", str(self.root)]), 0)
        text = out.getvalue()
        self.assertIn("❌ E-HARD：", text)
        self.assertIn("驗收政策尚未定案，預填依建議值；先 h3d decide acceptance_policy", text)
        self.assertFalse((self.root / "review" / "verdicts.json").exists())

        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            verdicts.main(["--prefill", "--apply", "--root", str(self.root)])


if __name__ == "__main__":
    unittest.main()
