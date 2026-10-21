"""doctor 自檢的結構性測試（不連外網、不呼叫生成端點）。"""
import json
import unittest
from pathlib import Path

from scripts import doctor

ROOT = Path(__file__).resolve().parents[1]


class DoctorReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = doctor.build_report(ROOT)

    def test_report_is_json_serializable(self):
        json.dumps(self.report, ensure_ascii=False)

    def test_required_sections(self):
        for key in ("tools", "gpu", "services", "ffmpeg_vsync", "disk", "verdict", "scope"):
            self.assertIn(key, self.report)

    def test_tool_status_is_known(self):
        for name, info in self.report["tools"].items():
            self.assertIn(info["status"], ("ready", "missing", "unknown"), name)

    def test_services_are_tri_state_not_fake_pass(self):
        for name, info in self.report["services"].items():
            self.assertIn(info["status"], ("ready", "closed", "unknown"), name)
            self.assertIn(info.get("listening"), (True, False, None), name)

    def test_gpu_is_not_claimed_when_unknown(self):
        gpu = self.report["gpu"]
        self.assertIn(gpu["status"], ("ready", "unknown"))
        if gpu["status"] == "unknown":
            self.assertNotIn("free_mb", gpu)

    def test_verdict_lists_are_lists(self):
        for key in ("ready", "warn", "blocked"):
            self.assertIsInstance(self.report["verdict"][key], list)

    def test_report_does_not_write_into_the_workspace(self):
        before = sorted(p.name for p in ROOT.iterdir())
        doctor.build_report(ROOT)
        after = sorted(p.name for p in ROOT.iterdir())
        self.assertEqual(before, after, "doctor 不得在專案根目錄產生檔案")

    def test_ffmpeg_vsync_is_tri_state(self):
        info = self.report["ffmpeg_vsync"]
        self.assertIn(info["status"], ("ready", "unknown"))
        self.assertIn(info.get("accepts_vsync"), (True, False, None))

    def test_tool_states_are_tri_state(self):
        for name, info in self.report["tools"].items():
            self.assertIn(info["status"], ("ready", "missing", "unknown"), name)


if __name__ == "__main__":
    unittest.main()
