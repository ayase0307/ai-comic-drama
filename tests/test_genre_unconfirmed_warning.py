import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "adapt" / "estimate_duration.py"
NOVEL = "第一章 開始\n" + "「你好啊。」他說。\n" * 30


def run(root: Path, *extra):
    f = root / "source" / "ch.txt"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(NOVEL, encoding="utf-8")
    # Windows 預設用 cp950 解碼子程序輸出，中文會炸；強制 UTF-8。
    return subprocess.run([sys.executable, str(SCRIPT), "--novel", "--novel-file", str(f), "--json", *extra],
                          capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})


class GenreUnconfirmedTest(unittest.TestCase):
    def make(self, genre_line):
        d = Path(tempfile.mkdtemp())
        (d / "project.md").write_text(f"- genre_mode：{genre_line}\n", encoding="utf-8")
        (d / "adapt").mkdir()
        (d / "adapt" / "source.json").write_text(json.dumps({"genre_mode": "healing_literary"}), encoding="utf-8")
        return d

    def test_placeholder_warns(self):
        r = run(self.make("<xuanhuan_revenge | healing_literary>"))
        self.assertIn("尚未定案", r.stderr)
        self.assertTrue(json.loads(r.stdout)["genre_unconfirmed"])

    def test_decided_no_warning(self):
        r = run(self.make("wuxia_action"))
        self.assertNotIn("尚未定案", r.stderr)
        res = json.loads(r.stdout)
        self.assertEqual(res["genre_mode"], "wuxia_action")
        self.assertNotIn("genre_unconfirmed", res)

    def test_explicit_genre_no_warning(self):
        r = run(self.make("<a | b>"), "--genre", "wuxia_action")
        self.assertNotIn("尚未定案", r.stderr)


if __name__ == "__main__":
    unittest.main()
