import io, pathlib, sys, tempfile, unittest, contextlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))
import export_asset_prompts as ex

CARD = """## 二、角色
### C-shen-luonian 沈洛年
- **設定板描述**：少年，黑短髮
- **W-shen-luonian-01**：便服 灰T恤
- **W-shen-luonian-02**：制服 深藍外套
### S-alley 後巷
- **固定描述片段**：narrow alley
"""
MIXED = """### C-a 甲
```text
a young man
```
### S-alley 後巷
- **固定描述片段**：narrow alley
"""

class T(unittest.TestCase):
    def test_wardrobe(self):
        a = ex.parse_card_assets(CARD)
        self.assertEqual(len(a), 4)
        w2 = [x for x in a if x["name"].startswith("W-shen-luonian-02")][0]
        self.assertIn("制服", w2["description"])
        self.assertEqual(w2["filename"], "wardrobe-shen-luonian-02.png")
    def test_mixed(self):
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / "assets.md"; f.write_text(MIXED, encoding="utf-8")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                r = ex.parse_assets_markdown(f)
        self.assertEqual(len(r), 2)
        self.assertIn("混用", err.getvalue())
