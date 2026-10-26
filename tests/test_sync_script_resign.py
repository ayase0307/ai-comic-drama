import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNC = ROOT / "scripts" / "adapt" / "sync_script.py"
V1 = "第01集｜測試\n\n1-1 書房 晨/內\n人物：甲\n甲：第一句。\n"
V2 = "第01集｜測試\n\n1-1 書房 晨/內\n人物：甲\n甲：改過的句子。\n"


def run(d, *extra):
    return subprocess.run([sys.executable, str(SYNC), "--handoff", str(d / "handoff-ep01.json"),
                           "--script", str(d / "script-ep01.md"), "--episode", "EP01", *extra],
                          capture_output=True, text=True, cwd=d)


class ResignTest(unittest.TestCase):
    def test_resign_keeps_approved_locked(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "script-ep01.md").write_text(V1, encoding="utf-8")
            self.assertEqual(run(d).returncode, 0)
            sid = json.loads((d / "handoff-ep01.json").read_text(encoding="utf-8"))["episodes"][0]["scenes"][0]["scene_id"]
            subprocess.run([sys.executable, str(SYNC), "--handoff", str(d / "handoff-ep01.json"),
                            "--scene", sid, "--set-status", "approved"], check=True, capture_output=True, cwd=d)
            (d / "script-ep01.md").write_text(V2, encoding="utf-8")
            self.assertNotEqual(run(d).returncode, 0)  # 沒帶旗標仍被擋
            r = run(d, "--resign")
            self.assertEqual(r.returncode, 0, r.stderr)
            sc = json.loads((d / "handoff-ep01.json").read_text(encoding="utf-8"))["episodes"][0]["scenes"][0]
            self.assertEqual(sc["review"]["review_status"], "approved")
            self.assertTrue(sc["review"]["locked"])
            self.assertIn("改過的句子", json.dumps(sc, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
