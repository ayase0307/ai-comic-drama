import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))

import skill_version  # noqa: E402


class VersionSourceTests(unittest.TestCase):
    def test_version_file_is_semver(self):
        skill_version.parse(skill_version.skill_version())

    def test_skill_md_version_matches(self):
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        m = re.search(r"^version:\s*(\S+)\s*$", text.split("---")[1], re.M)
        self.assertIsNotNone(m, "SKILL.md 標頭缺 version")
        self.assertEqual(m.group(1), skill_version.skill_version())

    def test_changelog_has_current_version(self):
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn(f"## [{skill_version.skill_version()}]", text)
        self.assertIn("## [未發布]", text)

    def test_schema_table_matches_modules(self):
        import decisions
        import deps
        import project_state as ps
        self.assertEqual(skill_version.SCHEMA_VERSIONS["decisions"], decisions.SCHEMA_VERSION)
        self.assertEqual(skill_version.SCHEMA_VERSIONS["deps"], deps.SCHEMA_VERSION)
        self.assertEqual(skill_version.SCHEMA_VERSIONS["project_state"], ps.initial_state()["schema_version"])


class ProjectStampTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="版本 章 "))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _init(self):
        root = self.tmp / "proj"
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "init_project.py"), str(root), "--title", "測試"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
        self.assertEqual(r.returncode, 0, r.stderr)
        return root

    def _state(self, root):
        return json.loads((root / "review" / "project-state.json").read_text(encoding="utf-8"))

    def test_init_stamps_project(self):
        root = self._init()
        stamp = self._state(root)["skill_version"]
        self.assertEqual(stamp["skill"], skill_version.skill_version())
        self.assertEqual(stamp["schemas"], skill_version.SCHEMA_VERSIONS)
        self.assertIsNone(skill_version.check_project(self._state(root)))

    def test_older_stamp_warns_and_accept_clears(self):
        import project_state as ps
        import next_step
        root = self._init()
        state = ps.load_state(root)
        state["skill_version"] = {"skill": "0.1.0", "schemas": dict(skill_version.SCHEMA_VERSIONS)}
        ps.save_state(root, state)
        notice = next_step.plan(root)["version_notice"]
        self.assertIsNotNone(notice)
        self.assertEqual(notice["project"], "0.1.0")
        self.assertIn("h3d version --root . --accept", notice["message"])
        self.assertTrue(any(c.startswith(f"[{skill_version.skill_version()}]") for c in notice["changes"]))
        self.assertIn("版本：", next_step.render(next_step.plan(root)))
        self.assertEqual(skill_version.main(["--root", str(root), "--accept"]), 0)
        self.assertIsNone(next_step.plan(root)["version_notice"])
        self.assertTrue(ps.state_integrity(root))

    def test_schema_change_is_warn(self):
        state = {"skill_version": {"skill": skill_version.skill_version(),
                                   "schemas": {**skill_version.SCHEMA_VERSIONS, "deps": 1}}}
        notice = skill_version.check_project(state)
        self.assertEqual(notice["level"], "warn")
        self.assertIn("deps 1→", notice["message"])

    def test_missing_stamp_is_info(self):
        notice = skill_version.check_project({})
        self.assertEqual(notice["level"], "info")

    def test_newer_project_asks_pull(self):
        notice = skill_version.check_project({"skill_version": {"skill": "99.0.0"}})
        self.assertIn("git pull", notice["message"])


class CliTests(unittest.TestCase):
    def test_h3d_version_flag(self):
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "h3d.py"), "--version"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(skill_version.skill_version(), r.stdout)

    def test_h3d_version_subcommand_json(self):
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "h3d.py"), "version", "--json"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["skill"], skill_version.skill_version())


if __name__ == "__main__":
    unittest.main()
