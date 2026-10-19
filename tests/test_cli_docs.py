import unittest
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import init_project


class GeneratedFlowHintTests(unittest.TestCase):
    def test_generated_commands_match_real_cli_help(self):
        project = ROOT / "tmp-flow-hint-project"
        hint = init_project.flow_hint(project)
        commands = re.findall(r'python "([^"]+\.py)"([^\r\n]*)', hint)
        self.assertTrue(commands, "flow_hint should contain executable CLI commands")

        for script_text, argument_text in commands:
            script = Path(script_text)
            self.assertTrue(script.is_file(), f"CLI script missing: {script}")
            result = subprocess.run(
                [sys.executable, str(script), "--help"],
                cwd=ROOT,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            supported = set(re.findall(r"(?<!\w)--[a-zA-Z][a-zA-Z0-9-]*", result.stdout or ""))
            used = set(re.findall(r"(?<!\w)--[a-zA-Z][a-zA-Z0-9-]*", argument_text))
            self.assertFalse(used - supported, f"{script.name} uses unsupported flags: {used - supported}")

        self.assertIn("只要文字劇本或分鏡，可交付 draft", hint)
        self.assertIn("已提供的 brief、模型、參數沿用，不重問", hint)
        self.assertIn("review/project-state.json", hint)
        self.assertIn("--skip-stage-gate` 只供 dry-run", hint)

    def test_guidance_states_narration_and_effective_timeline_limits(self):
        hint = init_project.flow_hint(ROOT / "project")
        self.assertIn("由編譯後 segments 檢查並匯出實際時間線", hint)
        self.assertNotIn("--narration", hint)

    def test_full_path_has_review_and_approval_commands_for_stages_zero_to_three(self):
        hint = init_project.flow_hint(ROOT / "project")
        commands = re.findall(r'python "([^\"]+\.py)"([^\r\n]*)', hint)
        review_args = [args for script, args in commands if Path(script).name == "build_stage_review.py"]
        review_stages = {
            int(match.group(1))
            for args in review_args
            if (match := re.search(r"(?:^|\s)--stage\s+(\d+)(?:\s|$)", args))
        }
        approved_stages = {
            int(match.group(1))
            for args in review_args
            if (match := re.search(r"(?:^|\s)--approve-stage\s+(\d+)(?:\s|$)", args))
        }
        self.assertTrue(set(range(4)).issubset(review_stages))
        self.assertTrue(set(range(4)).issubset(approved_stages))
        self.assertIn("Set-Location -LiteralPath", hint)
        self.assertNotIn("cd /d", hint)
        self.assertIn("不得代替使用者記錄核准", hint)


if __name__ == "__main__":
    unittest.main()
