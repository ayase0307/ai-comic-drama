"""svg_storyboard_grid：免生圖構圖工具的端對端測試（需要選用依賴 numpy、resvg-py）。"""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "storyboard" / "svg_storyboard_grid.py"
EXAMPLE = ROOT / "examples" / "svg-grid-minimal"
sys.path.insert(0, str(ROOT / "scripts"))

HAS_DEPS = all(importlib.util.find_spec(m) for m in ("numpy", "resvg_py", "PIL"))


@unittest.skipUnless(HAS_DEPS, "需要 numpy、resvg-py、Pillow")
class SvgStoryboardGridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / "tmp").mkdir(exist_ok=True)
        cls.tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        cls.project = Path(cls.tmp.name)
        shutil.copytree(EXAMPLE / "layer2", cls.project / "layer2")
        cls.first = cls._run()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def _run(cls, *extra):
        return subprocess.run([sys.executable, str(SCRIPT), "--root", str(cls.project), *extra],
                              cwd=ROOT, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=600)

    def _layer2(self):
        return json.loads((self.project / "layer2" / "layer2-EP01-S02-a.json").read_text(encoding="utf-8"))

    def test_zero_config_render_and_write_back(self):
        self.assertEqual(self.first.returncode, 0, self.first.stderr)
        self.assertIn("API 呼叫 0 次", self.first.stdout)
        self.assertNotIn("⚠ 方向", self.first.stdout)  # 畫左／畫右與文字一致
        data = self._layer2()
        self.assertEqual(data["grid_preview_file"], "images/grid-EP01-S02-a.png")
        self.assertTrue((self.project / data["grid_preview_file"]).is_file())
        import project_state as ps
        for shot in data["shots"]:
            panel = self.project / shot["sketch_file"]
            self.assertTrue(panel.is_file(), shot["shot_id"])
            self.assertEqual(shot["sketch_sha256"], ps.sha256_file(panel).removeprefix("sha256:"))
            self.assertEqual(shot["sketch_generation"]["backend"], "svg-rig")
            self.assertEqual(shot["sketch_generation"]["api_calls"], 0)
        self.assertEqual([p["shot_id"] for p in data["storyboard_panels"]], [s["shot_id"] for s in data["shots"]])

    def test_stage4_gate_accepts_rendered_panels(self):
        import project_state as ps
        matched, errors = ps.stage4_artifacts(self.project)
        self.assertEqual(errors, [])
        self.assertGreaterEqual(len(matched), len(self._layer2()["shots"]))

    def test_locked_shot_is_not_redrawn(self):
        data = self._layer2()
        data["shots"][0]["sketch_status"] = "locked"
        before = data["shots"][0]["sketch_sha256"]
        path = self.project / "layer2" / "layer2-EP01-S02-a.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        result = self._run("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("鎖定，略過 EP01-S02-a-SH01", result.stdout)
        self.assertNotIn("[dry-run] EP01-S02-a-SH01", result.stdout)
        self.assertEqual(self._layer2()["shots"][0]["sketch_sha256"], before)


@unittest.skipUnless(HAS_DEPS, "需要 numpy、resvg-py、Pillow")
class SvgRigGeneralityTests(unittest.TestCase):
    def test_engine_has_no_project_specific_names(self):
        text = SCRIPT.read_text(encoding="utf-8") + (SCRIPT.parent / "svg_rig_actions.json").read_text(encoding="utf-8")
        for word in ("陳硯", "呂懷素", "葉停雲", "宋硯秋", "遺忘課", "林小雨", "周澤"):
            self.assertNotIn(word, text)

    def test_names_inferred_from_layer2_text(self):
        import importlib
        spec = importlib.util.spec_from_file_location("svg_grid_mod", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        files = [str(p) for p in (EXAMPLE / "layer2").glob("layer2-*.json")]
        shots = [s for f in files for s in json.loads(Path(f).read_text(encoding="utf-8"))["shots"]]
        mod.infer_names(files, shots)
        self.assertEqual(mod.CHARS["C-lin"]["name"], "林小雨")
        self.assertEqual(mod.CHARS["C-zhou"]["name"], "周澤")


if __name__ == "__main__":
    unittest.main()
