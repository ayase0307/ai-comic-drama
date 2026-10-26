import json, pathlib, subprocess, sys, tempfile, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "storyboard" / "export_asset_prompts.py"
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))
sys.path.insert(0, str(ROOT / "scripts"))
import export_asset_prompts as eap

ASSETS = """# 資產聖經
## 風格錨點
- **style_index**：`14`
## 角色
### C-hero　英雄（主角）
```text
adult man, black hair, red robe
```
## 場景
### S-hall　講堂
```text
wooden hall, morning light
```
"""


def _proj(tmp, engine=None):
    (tmp / "assets.md").write_text(ASSETS, encoding="utf-8")
    if engine:
        (tmp / "decisions.json").write_text(
            json.dumps({"decisions": [{"id": "design_engine", "value": engine}]}), encoding="utf-8")
    return tmp


def _run(tmp):
    return subprocess.run([sys.executable, str(SCRIPT), "--assets-md", str(tmp / "assets.md"), "--no-gate"],
                          capture_output=True, text=True)


class GrokManifestTest(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_resolve_engine_order(self):
        self.assertEqual(eap.resolve_engine(None, self.tmp)["engine"], "codex")
        _proj(self.tmp, "grok_generate_image")
        self.assertEqual(eap.resolve_engine(None, self.tmp), {"engine": "grok", "source": "decisions.json"})
        self.assertEqual(eap.resolve_engine("codex", self.tmp)["engine"], "codex")

    def test_grok_writes_manifest(self):
        _proj(self.tmp, "grok")
        out = _run(self.tmp)
        self.assertEqual(out.returncode, 0, out.stderr)
        m = json.loads((self.tmp / "images" / "grok-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((m["engine"], m["count"]), ("grok", 2))
        first = m["items"][0]
        self.assertEqual((first["id"], first["type"], first["aspect_ratio"]), ("C-hero", "character", "16:9"))
        self.assertTrue(first["output_path"].startswith("images/") and first["prompt"])
        self.assertIsInstance(first["reference_images"], list)
        self.assertTrue((self.tmp / "images" / "grok-manifest.md").exists())

    def test_codex_writes_no_manifest(self):
        _proj(self.tmp)
        self.assertEqual(_run(self.tmp).returncode, 0)
        self.assertFalse((self.tmp / "images" / "grok-manifest.json").exists())


if __name__ == "__main__":
    unittest.main()


class ExtrasCardTest(unittest.TestCase):
    def test_extras_card_is_parsed(self):
        text = "### EXTRAS-crowd　群演\n- **設定板描述**：`八名成年女子，素服`\n- **設定圖**：`images/extras-crowd.png`\n"
        items = eap.parse_card_assets(text)
        self.assertEqual([(a["type"], a["filename"]) for a in items], [("extras", "extras-crowd.png")])
