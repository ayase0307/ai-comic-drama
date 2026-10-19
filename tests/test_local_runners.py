"""Offline regressions for local image runners and asset prompt export."""

import contextlib
import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from scripts.storyboard import export_asset_prompts as exporter
from scripts.storyboard import qwen_storyboard_grid as qwen
from scripts.storyboard import run_codex_asset_gen as codex_runner


class LocalRunnerSafetyTests(unittest.TestCase):
    def test_importing_qwen_module_keeps_process_stdout_and_stderr_open(self):
        root = Path(__file__).resolve().parents[1]
        child = subprocess.run(
            [sys.executable, "-c", (
                "import scripts.storyboard.qwen_storyboard_grid; "
                "import scripts.storyboard.verify_video_shot; "
                "print('stdout-ok'); import sys; print('stderr-ok', file=sys.stderr)"
            )],
            cwd=root, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertIn("stdout-ok", child.stdout)
        self.assertIn("stderr-ok", child.stderr)

    def _png(self, path: Path, color=(12, 34, 56)) -> None:
        # Deterministic enough image validation is irrelevant here; noise keeps
        # the PNG above the runner's historical 20 KiB acceptance threshold.
        Image.frombytes("RGB", (256, 256), os.urandom(256 * 256 * 3)).save(path, format="PNG")

    def test_codex_nonzero_exit_cannot_be_success_even_if_image_exists(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            target = {"filename": "hero.png", "aliases": []}

            class FailedProcess:
                returncode = 9

                def __init__(self, command, **kwargs):
                    LocalRunnerSafetyTests.command = command
                    work = Path(command[command.index("-C") + 1])
                    LocalRunnerSafetyTests._png_static(work / "hero.png")

                def communicate(self, timeout=None):
                    return "failed", ""

                def kill(self):
                    pass

            with mock.patch.object(codex_runner.shutil, "which", return_value="C:/codex.exe"), \
                 mock.patch.object(codex_runner.subprocess, "Popen", FailedProcess):
                self.assertFalse(codex_runner.generate_single_asset_codex(target, "prompt", root))
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", self.command)
            self.assertIn("--sandbox", self.command)
            self.assertIn("workspace-write", self.command)
            self.assertIn("--skip-git-repo-check", self.command)
            self.assertNotIn("--ignore-user-config", self.command)

    @staticmethod
    def _png_static(path: Path) -> None:
        Image.frombytes("RGB", (256, 256), os.urandom(256 * 256 * 3)).save(path, format="PNG")

    def test_codex_does_not_accept_old_alias_or_unrelated_png_as_this_run_output(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            old = root / "hero.png"
            self._png(old, color=(200, 20, 30))
            before = old.read_bytes()
            target = {"filename": "hero.png", "aliases": []}

            class NoOutputProcess:
                returncode = 0

                def __init__(self, command, **kwargs):
                    pass

                def communicate(self, timeout=None):
                    return "done", ""

                def kill(self):
                    pass

            with mock.patch.object(codex_runner.shutil, "which", return_value="C:/codex.exe"), \
                 mock.patch.object(codex_runner.subprocess, "Popen", NoOutputProcess):
                self.assertFalse(codex_runner.generate_single_asset_codex(target, "prompt", root))
            self.assertEqual(old.read_bytes(), before)

    def test_codex_success_replaces_existing_image_only_after_valid_new_png(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            destination = root / "hero.png"
            self._png(destination, color=(200, 20, 30))
            previous = destination.read_bytes()

            class SuccessfulProcess:
                returncode = 0

                def __init__(self, command, **kwargs):
                    self.command = command
                    LocalRunnerSafetyTests.command = command
                    self._work = Path(command[command.index("-C") + 1])

                def communicate(self, timeout=None):
                    LocalRunnerSafetyTests._png_static(self._work / "hero.png")
                    return "ok", ""

                def kill(self):
                    pass

            with mock.patch.object(codex_runner.shutil, "which", return_value="C:/codex.exe"), \
                 mock.patch.object(codex_runner.subprocess, "Popen", SuccessfulProcess):
                self.assertTrue(codex_runner.generate_single_asset_codex(
                    {"filename": "hero.png"}, "prompt", root, model="local-model"
                ))
            self.assertNotEqual(destination.read_bytes(), previous)
            self.assertIn("local-model", self.command)

    def test_codex_asset_runner_uses_supplied_prompt_list_and_output_dir(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            prompts = root / "prompts.json"
            prompts.write_text(json.dumps([
                {"filename": "custom-scene.png", "full_prompt": "scene prompt"},
                {"filename": "C:\\assets\\prop:one.png", "full_prompt": "prop prompt"},
            ]), encoding="utf-8")
            generated = []

            def fake_generate(target, prompt, output_dir, **kwargs):
                generated.append((target["filename"], prompt, Path(output_dir), kwargs["model"]))
                return True

            with mock.patch.object(codex_runner, "resolve_codex_executable", return_value="codex.exe"), \
                 mock.patch.object(codex_runner, "validate_codex_cli"), \
                 mock.patch.object(codex_runner, "generate_single_asset_codex", side_effect=fake_generate), \
                 mock.patch.object(codex_runner.time, "sleep"):
                result = codex_runner.main([
                    "--prompts", str(prompts), "--output-dir", str(root / "images"), "--model", "test-model"
                ])
            self.assertEqual(result, 0)
            self.assertEqual([x[0] for x in generated], ["custom-scene.png", "C:\\assets\\prop:one.png"])
            self.assertTrue(all(x[2] == root / "images" for x in generated))
            self.assertTrue(all(x[3] == "test-model" for x in generated))

    def test_codex_asset_runner_rejects_sanitized_filename_collisions_before_generation(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            prompts = root / "prompts.json"
            prompts.write_text(json.dumps([
                {"filename": "same:name.png", "full_prompt": "one"},
                {"filename": "same name.png", "full_prompt": "two"},
            ]), encoding="utf-8")
            with mock.patch.object(codex_runner, "resolve_codex_executable", return_value="codex.exe"), \
                 mock.patch.object(codex_runner, "validate_codex_cli"), \
                 mock.patch.object(codex_runner, "generate_single_asset_codex") as generate:
                result = codex_runner.main(["--prompts", str(prompts), "--output-dir", str(root / "images")])
            self.assertEqual(result, 2)
            generate.assert_not_called()

    def test_qwen_dry_run_leaves_layer2_and_filesystem_unchanged(self):
        data = {
            "segment_id": "EP01-seg01",
            "shots": [{"shot_id": "SH01", "duration": 4, "review": {"review_status": "draft"}}],
        }
        original = copy.deepcopy(data)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            returned, hashes = qwen.process_storyboard_segment(
                client=mock.Mock(), layer2_data=data, out_dir=root,
                generate_all=True, dry_run=True,
            )
            self.assertEqual(returned, original)
            self.assertEqual(hashes, {})
            self.assertEqual(list(root.iterdir()), [])

    def test_qwen_dry_run_cli_preserves_layer2_bytes_and_creates_no_outputs(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=root) as td:
            work = Path(td)
            source = work / "layer2.json"
            raw = json.dumps({"segment_id": "EP01-seg01", "shots": [{"shot_id": "SH01", "duration": 4}]},
                             ensure_ascii=False, indent=2).encode("utf-8")
            source.write_bytes(raw)
            output = work / "out"
            child = subprocess.run(
                [sys.executable, "scripts/storyboard/qwen_storyboard_grid.py", "--layer2", str(source),
                 "--out-dir", str(output), "--generate-all", "--dry-run"],
                cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
            )
            self.assertEqual(child.returncode, 0, child.stderr)
            self.assertEqual(source.read_bytes(), raw)
            self.assertFalse(output.exists())

    def test_qwen_dry_run_cli_rejects_locked_shot_without_image(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=root) as td:
            work = Path(td)
            source = work / "layer2.json"
            source.write_text(json.dumps({"segment_id": "EP01-seg01", "shots": [{
                "shot_id": "SH01", "duration": 4,
                "review": {"locked": True, "review_status": "approved"},
            }]}), encoding="utf-8")
            output = work / "not-created"
            child = subprocess.run(
                [sys.executable, "scripts/storyboard/qwen_storyboard_grid.py", "--layer2", str(source),
                 "--out-dir", str(output), "--generate-all", "--dry-run"],
                cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
            )
            self.assertNotEqual(child.returncode, 0)
            self.assertIn("缺少", child.stdout + child.stderr)
            self.assertFalse(output.exists())

    def test_locked_shot_without_panel_is_rejected_instead_of_regenerated(self):
        data = {"shots": [{"shot_id": "SH01", "review": {"locked": True, "review_status": "approved"}}]}
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            with self.assertRaisesRegex((ValueError, RuntimeError), "已核准/鎖定|缺少|重生"):
                qwen.process_storyboard_segment(
                    client=mock.Mock(), layer2_data=data, out_dir=Path(td),
                    generate_all=True,
                )

    def test_bible_json_without_assets_fails_with_explicit_assets_requirement(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            bible = Path(td) / "bible.json"
            bible.write_text("{}", encoding="utf-8")
            stdout, stderr = io.StringIO(), io.StringIO()
            with mock.patch("sys.argv", ["export_asset_prompts.py", "--bible-json", str(bible)]), \
                 contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as result:
                    exporter.main()
            self.assertNotEqual(result.exception.code, 0)
            self.assertIn("--bible-json 目前只用來尋找關聯的 assets.md，不直接解析資產", stderr.getvalue())
            self.assertIn("--assets-md", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()


