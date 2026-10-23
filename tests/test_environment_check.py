import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_environment


class EnvironmentCheckTests(unittest.TestCase):
    def test_report_is_layered_and_does_not_treat_jsonschema_as_a_dependency(self):
        with patch.object(check_environment, "_command_version", return_value={"available": False, "version": None}), \
             patch.object(check_environment, "_package_version", return_value={"available": False, "version": None}):
            report = check_environment.build_report()
        self.assertEqual([item["name"] for item in report["capabilities"]], [
            "企劃與文本改編", "構圖與圖片檔檢查", "免生圖 SVG 構圖分鏡總覽圖（選用）", "影片片段技術審查", "影片組裝與交付驗證",
        ])
        self.assertNotIn("jsonschema", report["dependencies"])
        self.assertEqual(report["generation"]["status"], "not_checked")
        self.assertIn("未連線", report["generation"]["note"])

    def test_json_cli_emits_parseable_offline_report(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_environment.py"), "--json"],
                                cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertIn("capabilities", report)
        self.assertIn("no network", report["inspection"])

    def test_json_cli_writes_utf8_chinese_without_python_utf8_environment(self):
        env = os.environ.copy()
        env.pop("PYTHONUTF8", None)
        env["PYTHONIOENCODING"] = "cp950"
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_environment.py"), "--json"],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        stdout = result.stdout.decode("utf-8", "strict")
        report = json.loads(stdout)
        self.assertIn("企劃與文本改編", stdout)
        self.assertEqual(report["capabilities"][0]["name"], "企劃與文本改編")

    def test_offline_runner_reemits_utf8_chinese_and_emoji_from_cp950_parent(self):
        env = os.environ.copy()
        env.pop("PYTHONUTF8", None)
        env["PYTHONIOENCODING"] = "cp950"
        runner = ROOT / "scripts" / "run_offline_checks.py"
        child = "import sys; sys.path.insert(0, r'{}'); import run_offline_checks; run_offline_checks.run('stdout smoke', [sys.executable, '-c', \"print('檢查⚠️完成')\"])".format(
            str(ROOT / "scripts")
        )
        result = subprocess.run(
            [sys.executable, "-c", child], cwd=ROOT, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=env, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        stdout = result.stdout.decode("utf-8", "strict")
        self.assertIn("檢查⚠️完成", stdout)


if __name__ == "__main__":
    unittest.main()
