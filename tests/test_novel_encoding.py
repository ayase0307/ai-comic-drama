# -*- coding: utf-8 -*-
"""小說原稿編碼自動判斷：UTF-16／Big5／GB18030／UTF-8 BOM 都要讀得出章節。"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "adapt"))

import novel_text  # noqa: E402

SAMPLE = "## 第一集\n\n### 第一章 蘇醒\n\n「這是哪裡？」他問。\n狐狸精笑了。\n"


class NovelEncoding(unittest.TestCase):
    def test_detect_and_decode(self):
        for enc, expect in (("utf-16", "utf-16"), ("utf-8-sig", "utf-8-sig"),
                            ("utf-8", "utf-8"), ("cp950", "cp950"), ("gb18030", "gb18030")):
            data = SAMPLE.encode(enc)
            if enc == "gb18030":
                # 簡體字才會讓 cp950 解失敗
                data = SAMPLE.replace("裡", "里").replace("蘇醒", "苏醒").encode(enc)
            with self.subTest(enc=enc):
                got = novel_text.detect_encoding(data)
                if enc == "gb18030":
                    self.assertIn(got, ("gb18030",))
                else:
                    self.assertEqual(got, expect)

    def test_crlf_normalized(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "n.txt"
            p.write_bytes(SAMPLE.replace("\n", "\r\n").encode("utf-16"))
            text, enc = novel_text.read_novel_text(p)
            self.assertEqual(enc, "utf-16")
            self.assertNotIn("\r", text)
            self.assertIn("第一章 蘇醒", text)

    def test_extract_chapter_lists_utf16_and_big5(self):
        for enc in ("utf-16", "cp950"):
            with self.subTest(enc=enc), tempfile.TemporaryDirectory() as d:
                p = Path(d) / "n.txt"
                p.write_bytes(SAMPLE.replace("\n", "\r\n").encode(enc))
                r = subprocess.run([sys.executable, str(ROOT / "scripts/adapt/extract_chapter.py"),
                                    "--input", str(p), "--list", "--json"],
                                   capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn("蘇醒", r.stdout)

    def test_estimate_duration_novel_reads_big5(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "n.txt"
            p.write_bytes(SAMPLE.encode("cp950"))
            r = subprocess.run([sys.executable, str(ROOT / "scripts/adapt/estimate_duration.py"),
                                "--novel", "--novel-file", str(p), "--json"],
                               capture_output=True, text=True, encoding="utf-8")
            self.assertNotIn("UnicodeDecodeError", r.stderr)
            self.assertIn("{", r.stdout)


if __name__ == "__main__":
    unittest.main()
