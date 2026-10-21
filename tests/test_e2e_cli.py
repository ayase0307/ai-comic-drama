"""端到端 CLI 測試：真的用子程序跑 compile → deps → catalog。

這一支是「技能能不能被別人跑起來」的守門員：單元測試只證明函式對，
這裡證明**入口、參數、檔案產物、退出碼**在乾淨目錄下也對。
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


def run(args, cwd):
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    return subprocess.run([PY, *[str(a) for a in args]], cwd=str(cwd),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env)


def minimal_layer2():
    def shot(sid, start, end, size, focal, dist, action, expression):
        return {
            "shot_id": sid, "start_time": start, "end_time": end, "duration": end - start,
            "shot_size": size,
            "camera_optics": {"focal_length_mm": focal, "subject_distance_m": dist,
                              "composition_start": "subject on the left third",
                              "camera_movement": "static"},
            "action_and_performance": {"action_stages": [action],
                                       "observable_expression": expression,
                                       "background_idle_life": "", "micro_physics_tail": ""},
            "dialogue_and_audio": {"has_dialogue": False, "speaker": "",
                                   "line_verbatim": "", "lips_closed_lock": True,
                                   "foley_and_ambience": "quiet room tone"},
        }

    return {
        "project_id": "E2E", "scene_id": "SC01", "segment_id": "EP01-S01-a",
        "metadata": {"aspect_ratio": "16:9", "target_duration_sec": 7.0,
                     "lighting_lock_line": "Warm daylight from the west window."},
        "style_lock": {
            "anchor": "Semi-realistic 3D donghua CG, warm daylight palette",
            "negative": "no photorealism, no live-action skin texture",
            "lighting_lock_line": "Warm daylight from the west window.",
            "continuity_anchors": {
                "lighting": "Warm daylight from the west window.",
                "axis": "camera stays on the east side of the room",
                "blocking": "Mira stands beside the table",
                "texture": "smooth painted surfaces with soft fabric folds",
            },
        },
        "shots": [
            shot("SH01", 0.0, 3.5, "MS", 35, 2.0,
                 "Mira raises one hand", "her brows draw together and her jaw tightens"),
            shot("SH02", 3.5, 7.0, "CU", 50, 1.5,
                 "Mira lowers her hand", "her jaw loosens and her shoulders drop"),
        ],
    }


class EndToEndCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(dir=ROOT))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "layer2").mkdir()
        self.layer2 = self.tmp / "layer2" / "layer2-EP01-S01-a.json"
        self.layer2.write_text(json.dumps(minimal_layer2(), ensure_ascii=False, indent=2),
                               encoding="utf-8")
        self.segments = self.tmp / "segments-ep01.json"

    def test_compile_then_deps_then_catalog(self):
        compiled = run([
            ROOT / "scripts" / "storyboard" / "compile_layer2_to_h3.py",
            "--layer2", self.layer2, "--episode", "EP01",
            "--output-segments", self.segments, "--project-root", self.tmp,
            "--skip-stage-gate",
        ], cwd=ROOT)
        self.assertEqual(compiled.returncode, 0, compiled.stderr[-2000:])
        payload = json.loads(self.segments.read_text(encoding="utf-8"))
        segments = payload if isinstance(payload, list) else payload["segments"]
        meta = segments[0]["metadata"]
        self.assertEqual((meta["frames"] - 5) % 17, 0, "編譯產物必須帶合法量子")
        self.assertIn("cut_markers", meta)

        recorded = run([ROOT / "scripts" / "h3d.py", "deps", "--root", self.tmp, "--record"], cwd=ROOT)
        self.assertEqual(recorded.returncode, 0, recorded.stderr[-1000:])
        self.assertTrue((self.tmp / ".h3d-deps.json").is_file())

        status = run([ROOT / "scripts" / "h3d.py", "deps", "--root", self.tmp, "--status"], cwd=ROOT)
        self.assertEqual(status.returncode, 0, status.stderr[-1000:])
        self.assertIn("依賴帳本", status.stdout)

        prompt_file = self.tmp / "one-prompt.txt"
        prompt_file.write_text(segments[0]["h3_prompt"], encoding="utf-8")
        catalog = run([ROOT / "scripts" / "h3d.py", "catalog", "--check", prompt_file], cwd=ROOT)
        self.assertEqual(catalog.returncode, 0, catalog.stdout[-1000:] + catalog.stderr[-1000:])

    def test_compile_requires_approval_without_skip_flag(self):
        blocked = run([
            ROOT / "scripts" / "storyboard" / "compile_layer2_to_h3.py",
            "--layer2", self.layer2, "--episode", "EP01",
            "--output-segments", self.segments, "--project-root", self.tmp,
        ], cwd=ROOT)
        self.assertNotEqual(blocked.returncode, 0, "沒有 stage-4 核准時不得默默編譯")
        self.assertFalse(self.segments.exists())


if __name__ == "__main__":
    unittest.main()
