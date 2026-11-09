# -*- coding: utf-8 -*-
"""Windows 代碼頁（cp950）下，pipe 子程序必須吐 UTF-8 並以原本的結束碼結束。

comic-forge-lab 用 `python -B` 抓 stdout。繁中 Windows 的 pipe 預設是 cp950 + strict：
`h3d decide` 印 ✅ 或全形括號 `［` 會 UnicodeEncodeError，結束碼變 1，但定案已經寫進檔。
`h3d status --json` 維持 cp950，`h3d next --json` 又因為途中 import 被改成 UTF-8。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def _run(args, root: Path):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "cp950"
    return subprocess.run(
        [PY, "-B", *args],
        capture_output=True,
        env=env,
        cwd=str(root),
    )


class Cp950PipeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="漫畫專案_")
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_decide_list_exits_0_and_stdout_is_utf8(self):
        proc = _run([str(ROOT / "scripts" / "h3d.py"), "decide", "--list", "--root", str(self.root)], self.root)
        self.assertNotIn(b"UnicodeEncodeError", proc.stderr)
        text = proc.stdout.decode("utf-8")
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertIn("尚無定案", text)
        # 定案說明裡的全形括號不在 cp950，以前會在印到一半時炸掉。
        self.assertIn("［", text)

    def test_decide_write_exits_0_after_saving(self):
        proc = _run([
            str(ROOT / "scripts" / "h3d.py"), "decide", "aspect_ratio", "16:9",
            "--quote", "比例用十六比九", "--root", str(self.root),
        ], self.root)
        self.assertNotIn(b"UnicodeEncodeError", proc.stderr)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        text = proc.stdout.decode("utf-8")
        self.assertIn("已記錄定案", text)
        saved = json.loads((self.root / "decisions.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["decisions"][0]["value"], "16:9")
        self.assertEqual(saved["decisions"][0]["source"]["quote"], "比例用十六比九")

    def test_status_json_uses_utf8_for_chinese_paths(self):
        proc = _run([str(ROOT / "scripts" / "h3d.py"), "status", "--json", "--root", str(self.root)], self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        payload = json.loads(proc.stdout.decode("utf-8"))
        self.assertIn("漫畫專案_", payload["root"])

    def test_stage_content_check_does_not_traceback(self):
        proc = _run([
            str(ROOT / "scripts" / "stage_content_checks.py"), "--root", str(self.root), "--stage", "0",
        ], self.root)
        self.assertNotIn(b"UnicodeEncodeError", proc.stderr)
        self.assertEqual(proc.returncode, 1)
        text = proc.stdout.decode("utf-8")
        self.assertTrue(text.strip(), text)

    def test_init_project_stdout_is_utf8(self):
        dest = self.root / "霧港"
        proc = _run([str(ROOT / "scripts" / "init_project.py"), str(dest), "--title", "霧港"], self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        text = proc.stdout.decode("utf-8")
        self.assertIn("霧港", text)
        self.assertTrue((dest / "project.md").is_file())


if __name__ == "__main__":
    unittest.main()
