"""Eian 文章對照（2026-11-05·四線「監督」）：要求帳本與監督查核包（build_requirements_ledger.py）。

- 帳本：decisions.json 每條定案 → R01…（要求／定案值／使用者原話／適用階段）；inbox 待決卡 → P01…；
  dict 定案值渲染成 JSON 字串；--quotes 摘錄全文內嵌。
- --stage N／--all：查核包帶 project-state.json 各階段審核快照的產出檔（二進位列 skipped 不複製；
  --all 只收 approved）；包內只有 requirements.md＋files/＋manifest.json——結論檔不准進包。
- --inputs：手動查核對象（相對路徑在包內保持原樣）。
- 沒有 decisions.json／快照沒有產出／--stage 與 --all 同給 → exit 2。
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT / "scripts"),):
    if p not in sys.path:
        sys.path.insert(0, p)

import build_requirements_ledger as rl  # noqa: E402


def _make_project(root: Path) -> None:
    (root / "decisions.json").write_text(json.dumps({
        "schema_version": 1,
        "decisions": [
            {
                "id": "style_anchor", "rule": "風格錨句逐字", "value": "ST-04 Huanyu H8: matte poreless skin",
                "source": {"quote": "不是 glossy，改成霧面", "date": "2026-11-03", "by": "user"},
                "stages": [4, 5, 6],
            },
            {
                "id": "delivery_scope", "rule": "交付終點", "value": {"end_stage": 7},
                "source": {"quote": "到成片", "date": "2026-11-03", "by": "user"},
                "stages": [0, 7],
            },
        ],
    }, ensure_ascii=False), encoding="utf-8")
    (root / "review").mkdir()
    (root / "review" / "inbox.json").write_text(json.dumps({
        "schema_version": 1,
        "cards": [
            {"id": "D6-decide-acceptance_policy", "kind": "decision", "stage": 6,
             "title": "驗收政策還沒定案", "recommendation": "只有多出人才重跑",
             "blocking": 1, "if_ignored": "階段 6 不能往下"},
            {"id": "N-通知卡", "kind": "notice", "stage": 6, "title": "不是決策卡"},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    (root / "script-ep01.md").write_text("# EP01 劇本\n", encoding="utf-8")
    (root / "segments-ep01.json").write_text('{"segments": []}', encoding="utf-8")
    (root / "assets.md").write_text("# 資產\n", encoding="utf-8")
    (root / "images").mkdir()
    (root / "images" / "sheet.png").write_bytes(b"\x89PNG fake")
    (root / "review" / "project-state.json").write_text(json.dumps({
        "current_stage": 5,
        "stages": {
            "stage-2": {"status": "approved",
                        "review_snapshot": {"artifacts": [{"path": "assets.md"},
                                                           {"path": "images/sheet.png"}]}},
            "stage-3": {"status": "approved",
                        "review_snapshot": {"artifacts": [{"path": "script-ep01.md"}]}},
            "stage-5": {"status": "approved",
                        "review_snapshot": {"artifacts": [{"path": "segments-ep01.json"}]}},
            "stage-6": {"status": "in_progress", "review_snapshot": {"artifacts": []}},
        },
    }, ensure_ascii=False), encoding="utf-8")


class LedgerTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.root = Path(self.tmp.name)
        _make_project(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_ledger_only_renders_decisions_and_pending(self):
        ledger = rl.build(self.root, None, False, [], [])
        text = ledger.read_text(encoding="utf-8")
        self.assertEqual(ledger, self.root / "review" / "supervision" / "requirements.md")
        self.assertIn("### R01 style_anchor（適用階段：4, 5, 6）", text)
        self.assertIn("- 要求：風格錨句逐字", text)
        self.assertIn("- 定案值：ST-04 Huanyu H8: matte poreless skin", text)
        self.assertIn("「不是 glossy，改成霧面」", text)
        self.assertIn("### R02 delivery_scope", text)
        self.assertIn("- 定案值：{\"end_stage\": 7}", text)  # dict 值 → JSON 字串
        self.assertIn("### P01 D6-decide-acceptance_policy（階段 6・擋下一步）", text)
        self.assertNotIn("N-通知卡", text)  # 只收決策卡
        self.assertIn("主 agent 不准手改本檔", text)

    def test_ledger_requires_decisions_json(self):
        (self.root / "decisions.json").unlink()
        with self.assertRaises(SystemExit) as ctx:
            rl.build(self.root, None, False, [], [])
        self.assertEqual(ctx.exception.code, 2)

    def test_quotes_embedded_verbatim(self):
        (self.root / "notes.md").write_text("使用者說：旁白少一點。", encoding="utf-8")
        ledger = rl.build(self.root, None, False, [], ["notes.md"])
        text = ledger.read_text(encoding="utf-8")
        self.assertIn("### 摘錄：`notes.md`", text)
        self.assertIn("使用者說：旁白少一點。", text)

    def test_quote_file_missing_exits_2(self):
        with self.assertRaises(SystemExit) as ctx:
            rl.build(self.root, None, False, [], ["nope.md"])
        self.assertEqual(ctx.exception.code, 2)


class BundleTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.root = Path(self.tmp.name)
        _make_project(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def _bundle_names(self, bundle: Path) -> list[str]:
        return sorted(p.relative_to(bundle).as_posix() for p in bundle.rglob("*") if p.is_file())

    def test_stage_bundle_copies_snapshot_artifacts_only(self):
        bundle = rl.build(self.root, 5, False, [], [])
        self.assertEqual(bundle, self.root / "review" / "supervision" / "check-stage5")
        # 包內只有帳本快照＋產出檔＋manifest——結論檔（verdicts／審核頁／QA）不准進包
        self.assertEqual(self._bundle_names(bundle),
                         ["files/segments-ep01.json", "manifest.json", "requirements.md"])
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["targets"], ["segments-ep01.json"])
        self.assertEqual(manifest["stage"], 5)

    def test_stage_bundle_skips_binary_artifacts(self):
        bundle = rl.build(self.root, 2, False, [], [])
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["targets"], ["assets.md"])
        self.assertEqual(manifest["skipped_binary"], ["images/sheet.png"])
        self.assertFalse((bundle / "files" / "images" / "sheet.png").exists())

    def test_all_bundle_takes_approved_stages_only(self):
        bundle = rl.build(self.root, None, True, [], [])
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["stage"], "all")
        self.assertEqual(manifest["targets"],
                         ["assets.md", "script-ep01.md", "segments-ep01.json"])
        self.assertIn("files/script-ep01.md", self._bundle_names(bundle))

    def test_stage_without_snapshot_artifacts_exits_2(self):
        with self.assertRaises(SystemExit) as ctx:
            rl.build(self.root, 6, False, [], [])
        self.assertEqual(ctx.exception.code, 2)

    def test_inputs_mode_copies_relpath(self):
        bundle = rl.build(self.root, None, False, ["script-ep01.md"], [])
        self.assertTrue((bundle / "files" / "script-ep01.md").is_file())
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["manual_inputs"], ["script-ep01.md"])
        self.assertEqual(manifest["stage"], "inputs")

    def test_stage_and_all_mutually_exclusive(self):
        with self.assertRaises(SystemExit) as ctx:
            rl.build(self.root, 3, True, [], [])  # 直接呼叫也擋：兩個範圍同時給
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
