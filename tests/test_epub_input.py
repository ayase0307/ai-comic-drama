"""P1-11：extract_chapter.py 直接吃 .epub（標準庫 zipfile＋html.parser，不再要操作員自己找 pandoc）。"""
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "adapt" / "extract_chapter.py"

CHAPTER_1 = """<html><head><title>c1</title></head><body>
<h1>第一章 蛙仙石</h1>
<p>沈洛年站在蛙仙石前，聽見那個無聲的問題。</p>
<p>「更多。」他說。</p>
<script>var ignored = 1;</script>
</body></html>"""

CHAPTER_2 = """<html><body>
<h2>第二章 後巷</h2>
<p>回到學校後巷，黃蟲在地上蠕動。</p>
</body></html>"""

CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""

OPF = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <manifest>
    <item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/>
    <item id="c2" href="ch2.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="c1"/><itemref idref="c2"/></spine>
</package>"""


def make_epub(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", CONTAINER)
        zf.writestr("OEBPS/content.opf", OPF)
        zf.writestr("OEBPS/ch1.xhtml", CHAPTER_1)
        zf.writestr("OEBPS/ch2.xhtml", CHAPTER_2)


def run(*args):
    env = dict({k: v for k, v in __import__("os").environ.items()}, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=env)


class EpubInputTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.epub = self.root / "novel.epub"
        make_epub(self.epub)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def test_list_shows_both_chapters(self):
        out = run("--input", self.epub, "--list").stdout
        self.assertIn("第一章", out)
        self.assertIn("第二章", out)

    def test_extract_chapter_two(self):
        out = run("--input", self.epub, "--chapter", "2").stdout
        self.assertIn("黃蟲", out)
        self.assertNotIn("蛙仙石前", out)

    def test_extract_json_reports_source(self):
        out = run("--input", self.epub, "--chapter", "1", "--json").stdout
        data = json.loads(out)
        self.assertTrue(data, "JSON 輸出不可為空")

    def test_script_and_style_are_dropped(self):
        out = run("--input", self.epub, "--chapter", "1").stdout
        self.assertNotIn("ignored", out)


if __name__ == "__main__":
    unittest.main()
