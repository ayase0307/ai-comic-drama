import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNC = ROOT / "scripts" / "adapt" / "sync_script.py"

SCRIPT_V1 = """第01集｜測試

1-1 書房 晨/內
人物：甲、乙、丙
甲：第一句。
乙：第二句。
丙：第三句。
甲：第四句。
"""

SCRIPT_V2 = """第01集｜測試

1-1 書房 晨/內
人物：甲、乙、丙
甲：第一句。
丙：第三句。
甲：第四句。
"""


class SyncSpeakerShiftTest(unittest.TestCase):
    def test_deleting_a_line_keeps_speakers(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "adapt").mkdir()
            (d / "adapt" / "bible.json").write_text(json.dumps({"characters": [
                {"character_id": "C-a", "canonical_name": "甲"},
                {"character_id": "C-b", "canonical_name": "乙"},
                {"character_id": "C-c", "canonical_name": "丙"},
            ]}, ensure_ascii=False), encoding="utf-8")
            script = d / "script-ep01.md"
            handoff = d / "handoff-ep01.json"
            for text in (SCRIPT_V1, SCRIPT_V2):
                script.write_text(text, encoding="utf-8")
                subprocess.run([sys.executable, str(SYNC), "--handoff", str(handoff), "--script", str(script),
                                "--episode", "EP01"], check=True, capture_output=True, cwd=d)
            data = json.loads(handoff.read_text(encoding="utf-8"))
            got = [(x["speaker"], x["text"]) for x in data["episodes"][0]["scenes"][0]["dialogue"]]
            self.assertEqual(got, [("C-a", "第一句。"), ("C-c", "第三句。"), ("C-a", "第四句。")])


if __name__ == "__main__":
    unittest.main()
