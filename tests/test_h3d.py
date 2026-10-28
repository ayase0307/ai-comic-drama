"""h3d 單一入口：路由與組合查詢的測試（不重複實作，只驗轉呼叫）。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import h3d

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class H3dTests(unittest.TestCase):
    def test_list_prints_all_commands(self):
        with mock.patch("sys.stdout") as out:
            code = h3d.main(["--list"])
        self.assertEqual(code, 0)
        printed = "".join(call.args[0] for call in out.write.call_args_list)
        for command in ("compile", "audit", "qa", "submit", "collect", "resume",
                        "deps", "catalog", "doctor", "assemble", "status"):
            self.assertIn(command, printed)

    def test_unknown_command_returns_2(self):
        with mock.patch("sys.stderr"):
            self.assertEqual(h3d.main(["nope"]), 2)

    def test_sketch_removed_prints_codex_replacement_and_exits_2(self):
        import contextlib, io
        err = io.StringIO()
        with contextlib.redirect_stderr(err), mock.patch("sys.stdout"):
            code = h3d.main(["sketch", "--root", "proj", "--episode", "EP04"])
        self.assertEqual(code, 2)
        text = err.getvalue()
        self.assertIn("SVG 構圖已移除，改用 Codex 分鏡：", text)
        self.assertIn("codex_storyboard_panels.py", text)
        self.assertIn("--root proj --episode EP04", text)
        self.assertIn("--model ", text)
        self.assertNotIn("sketch", h3d.MODULE_FOR, "sketch 不再路由到任何模組")

    def test_catalog_routes_to_failure_catalog(self):
        with mock.patch("sys.stdout"):
            self.assertEqual(h3d.main(["catalog", "--list"]), 0)

    def test_catalog_check_propagates_exit_code(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            bad = Path(td) / "bad.txt"
            bad.write_text("texture: matte red light with no defined edge.", encoding="utf-8")
            with mock.patch("sys.stdout"):
                code = h3d.main(["catalog", "--check", str(bad)])
        self.assertEqual(code, 1, "enforce=error 條目必須讓子命令回非 0")

    def test_deps_record_and_status(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            root = Path(td)
            write_json(root / "layer2" / "layer2-EP01-S01.json",
                       {"segment_id": "EP01-S01", "shots": [{"shot_id": "SH01"}]})
            write_json(root / "segments-ep01.json",
                       [{"segment_id": "EP01-S01", "h3_prompt": "prompt", "metadata": {}}])
            with mock.patch("sys.stdout"):
                self.assertEqual(h3d.main(["deps", "--root", str(root), "--record"]), 0)
            self.assertTrue((root / ".h3d-deps.json").is_file())
            with mock.patch("sys.stdout"):
                self.assertEqual(h3d.main(["deps", "--root", str(root), "--status"]), 0)

    def test_status_combines_sections(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            root = Path(td)
            write_json(root / "review" / "project-state.json",
                       {"stages": {"stage-5": {"status": "approved"}}})
            write_json(root / "videos" / "_fv-job-ledger.json",
                       {"jobs": [{"id": "J1", "status": "downloaded"}]})
            with mock.patch("sys.stdout") as out:
                code = h3d.main(["status", "--root", str(root)])
            printed = "".join(call.args[0] for call in out.write.call_args_list)
        self.assertEqual(code, 0)
        for section in ("階段門禁", "依賴帳本", "送件帳本", "失敗目錄"):
            self.assertIn(section, printed)
        self.assertIn("stage-5", printed)
        self.assertIn("downloaded=1", printed)

    def test_status_json_is_parsable(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            captured = []
            with mock.patch("sys.stdout") as out:
                out.write.side_effect = lambda text: captured.append(text)
                h3d.main(["status", "--root", td, "--json"])
            payload = json.loads("".join(captured))
        self.assertEqual(payload["root"], str(Path(td).resolve()))
        self.assertIn("deps", payload)
        self.assertIn("catalog", payload)

    def test_collect_implies_flag(self):
        with mock.patch("sys.stdout"), mock.patch.object(h3d, "_invoke", return_value=0) as invoke:
            h3d.main(["collect", "--output-dir", "videos"])
        argv = invoke.call_args.args[1]
        self.assertEqual(argv[0], "--collect")
        self.assertIn("--output-dir", argv)

    def test_ack_implies_flag_and_validates_id(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td, mock.patch("sys.stderr"):
            code = h3d.main(["ack", "F-NOT-EXIST", "--root", td])
        self.assertEqual(code, 2, "未知 id 應由 failure_catalog 回 2")

    def test_resume_implies_flag(self):
        with mock.patch("sys.stdout"), mock.patch.object(h3d, "_invoke", return_value=0) as invoke:
            h3d.main(["resume", "--segments", "s.json"])
        self.assertEqual(invoke.call_args.args[1][0], "--resume")


if __name__ == "__main__":
    unittest.main()
