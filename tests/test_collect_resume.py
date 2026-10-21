"""collect / resume（I6）：中斷後把已完成的工作收回來，且不重複送件。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.storyboard import submit_h3_segments as submit

API = "https://api.example/freevideo/agent/v1"


class CollectTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(dir=Path(__file__).resolve().parents[1]))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.root, ignore_errors=True))
        self.out = self.root / "videos"
        self.out.mkdir(parents=True, exist_ok=True)
        self.ledger = self.out / "_fv-job-ledger.json"

    def _write_ledger(self, jobs, project=None, scope=API):
        payload = {"api_scope": scope, "jobs": jobs}
        if project is not None:
            payload["project"] = project
        else:
            payload["project"] = str(self.root.resolve())
        self.ledger.write_text(json.dumps(payload), encoding="utf-8")

    def _fake_api(self, mapping):
        calls = []

        def fake(api_url, token, method, path, body=None, timeout=600):
            calls.append((method, path))
            for job_id, payload in mapping.items():
                if path.startswith(f"/jobs/{job_id}"):
                    return payload
            raise AssertionError(f"未預期的 API 呼叫：{method} {path}")

        return fake, calls

    @staticmethod
    def _download(token, api_url, url, out_path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"mp4")

    def test_collect_downloads_completed_and_reports_running(self):
        self._write_ledger([
            {"id": "J1", "segment_id": "EP01-S01", "status": "succeeded", "frames": 277},
            {"id": "J2", "segment_id": "EP01-S02", "status": "waiting"},
        ])
        mapping = {
            "J1": {"job": {"id": "J1", "status": "succeeded",
                           "plan": {"geometry": {"frames": 277}},
                           "result": {"video": {"url": "/library/a.mp4"}}}},
            "J2": {"job": {"id": "J2", "status": "running"}},
        }
        fake, calls = self._fake_api(mapping)
        with mock.patch.object(submit, "call_api", side_effect=fake), \
             mock.patch.object(submit, "download_file", side_effect=self._download), \
             mock.patch.object(submit, "probe_video_duration", return_value=277 / 24.0):
            summary = submit.collect_jobs(API, "token", self.ledger, self.out)
        self.assertEqual(summary["downloaded"], 1)
        self.assertEqual(summary["still_running"], 1)
        self.assertTrue((self.out / "EP01-S01.mp4").exists())
        self.assertFalse(any(method == "POST" for method, _ in calls), "collect 不得送新件")
        ledger = json.loads(self.ledger.read_text(encoding="utf-8"))
        statuses = {job["id"]: job["status"] for job in ledger["jobs"]}
        self.assertEqual(statuses["J1"], "downloaded")

    def test_failed_in_ledger_but_succeeded_remotely_is_recovered(self):
        # 本地記 failed（worker_exit／輪詢例外）不代表遠端失敗，必須重查。
        self._write_ledger([
            {"id": "J1", "segment_id": "EP01-S01", "status": "failed", "frames": 277},
        ])
        mapping = {"J1": {"job": {"id": "J1", "status": "succeeded",
                                  "plan": {"geometry": {"frames": 277}},
                                  "result": {"video": {"url": "/library/a.mp4"}}}}}
        fake, _ = self._fake_api(mapping)
        with mock.patch.object(submit, "call_api", side_effect=fake), \
             mock.patch.object(submit, "download_file", side_effect=self._download), \
             mock.patch.object(submit, "probe_video_duration", return_value=277 / 24.0):
            summary = submit.collect_jobs(API, "token", self.ledger, self.out)
        self.assertEqual(summary["downloaded"], 1)
        self.assertTrue((self.out / "EP01-S01.mp4").exists())

    def test_collect_refuses_drifted_frames(self):
        self._write_ledger([
            {"id": "J1", "segment_id": "EP01-S01", "status": "succeeded", "frames": 277},
        ])
        mapping = {"J1": {"job": {"id": "J1", "status": "succeeded",
                                  "plan": {"geometry": {"frames": 294}},
                                  "result": {"video": {"url": "/library/a.mp4"}}}}}
        fake, _ = self._fake_api(mapping)
        with mock.patch.object(submit, "call_api", side_effect=fake), \
             mock.patch.object(submit, "download_file") as download:
            summary = submit.collect_jobs(API, "token", self.ledger, self.out)
        self.assertEqual(summary["drift"], 1)
        download.assert_not_called()

    def test_unverifiable_length_is_quarantined_not_downloaded(self):
        self._write_ledger([
            {"id": "J1", "segment_id": "EP01-S01", "status": "succeeded", "frames": 277},
        ])
        mapping = {"J1": {"job": {"id": "J1", "status": "succeeded",
                                  "plan": {"geometry": {"frames": 277}},
                                  "result": {"video": {"url": "/library/a.mp4"}}}}}
        fake, _ = self._fake_api(mapping)
        with mock.patch.object(submit, "call_api", side_effect=fake), \
             mock.patch.object(submit, "download_file", side_effect=self._download), \
             mock.patch.object(submit, "probe_video_duration", return_value=None):
            summary = submit.collect_jobs(API, "token", self.ledger, self.out)
        self.assertEqual(summary["unverified"], 1)
        self.assertEqual(summary["failed"], 1)
        self.assertFalse((self.out / "EP01-S01.mp4").exists())
        self.assertTrue((self.out / "EP01-S01.unverified.mp4").exists())
        ledger = json.loads(self.ledger.read_text(encoding="utf-8"))
        self.assertEqual(ledger["jobs"][0]["status"], "duration_unverified")

    def test_scope_mismatch_aborts_without_calls(self):
        self._write_ledger([{"id": "J1", "segment_id": "EP01-S01", "status": "succeeded"}],
                           scope="https://other.example/v1")
        with mock.patch.object(submit, "call_api") as api:
            summary = submit.collect_jobs(API, "token", self.ledger, self.out)
        api.assert_not_called()
        self.assertEqual(summary["aborted"], 1)

    def test_segment_filter_limits_collection(self):
        self._write_ledger([
            {"id": "J1", "segment_id": "EP01-S01", "status": "succeeded", "frames": 277},
            {"id": "J9", "segment_id": "EP07-S42", "status": "succeeded", "frames": 277},
        ])
        mapping = {"J1": {"job": {"id": "J1", "status": "running"}}}
        fake, calls = self._fake_api(mapping)
        with mock.patch.object(submit, "call_api", side_effect=fake):
            summary = submit.collect_jobs(API, "token", self.ledger, self.out,
                                          only=["EP01-S01"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(summary["still_running"], 1)

    def test_collect_skips_existing_files(self):
        self._write_ledger([{"id": "J1", "segment_id": "EP01-S01", "status": "succeeded"}])
        (self.out / "EP01-S01.mp4").write_bytes(b"already")
        with mock.patch.object(submit, "call_api") as api:
            summary = submit.collect_jobs(API, "token", self.ledger, self.out)
        api.assert_not_called()
        self.assertEqual(summary["skipped"], 1)

    def test_collect_without_ledger_is_a_noop(self):
        with mock.patch.object(submit, "call_api") as api:
            summary = submit.collect_jobs(API, "token", self.ledger, self.out)
        api.assert_not_called()
        self.assertEqual(summary["downloaded"], 0)

    def test_missing_project_aborts(self):
        self.ledger.write_text(json.dumps({"api_scope": API, "jobs": [
            {"id": "J1", "segment_id": "EP01-S01", "status": "succeeded"},
        ]}), encoding="utf-8")
        with mock.patch.object(submit, "call_api") as api:
            summary = submit.collect_jobs(API, "token", self.ledger, self.out)
        api.assert_not_called()
        self.assertEqual(summary["aborted"], 1)

    def test_cli_collect_returns_nonzero_when_api_unreachable(self):
        self._write_ledger([{"id": "J1", "segment_id": "EP01-S01", "status": "succeeded"}])
        with mock.patch.object(submit, "find_token", return_value="token"), \
             mock.patch.object(submit, "call_api", side_effect=RuntimeError("503")):
            code = submit.main(["--collect", "--api-url", API, "--output-dir", str(self.out)])
        self.assertEqual(code, 1)

    def test_cli_collect_does_not_require_segments(self):
        self._write_ledger([])
        with mock.patch.object(submit, "find_token", return_value="token"):
            code = submit.main(["--collect", "--api-url", API, "--output-dir", str(self.out)])
        self.assertEqual(code, 0)


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(dir=Path(__file__).resolve().parents[1]))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.root, ignore_errors=True))
        self.out = self.root / "videos"
        self.out.mkdir(parents=True, exist_ok=True)
        self.segments = self.root / "segments-ep01.json"
        self.segments.write_text(json.dumps([{
            "segment_id": "EP01-S01", "prompt": "offline prompt", "reference_images": [],
            "metadata": {"frames": 277, "target_duration_sec": 277 / 24.0},
        }]), encoding="utf-8")
        (self.out / "_fv-job-ledger.json").write_text(json.dumps({
            "project": str(self.root.resolve()), "api_scope": API,
            "jobs": [{"id": "J1", "segment_id": "EP01-S01", "status": "waiting"}],
        }), encoding="utf-8")

    def test_resume_does_not_resubmit_a_live_segment(self):
        calls = []

        def fake_api(api_url, token, method, path, body=None, timeout=600):
            calls.append((method, path))
            if path.startswith("/jobs/J1"):
                return {"job": {"id": "J1", "status": "running"}}
            raise AssertionError(f"不該送新件：{method} {path}")

        with mock.patch.object(submit, "find_token", return_value="token"), \
             mock.patch.object(submit, "verify_stage5_gate", return_value=True), \
             mock.patch.object(submit, "get_gpu_vram", return_value=None), \
             mock.patch.object(submit, "audit_segment_prompts", return_value=(True, [])), \
             mock.patch.object(submit, "call_api", side_effect=fake_api):
            code = submit.main([
                "--resume", "--segments", str(self.segments), "--output-dir", str(self.out),
                "--root-dir", str(self.root), "--api-url", API,
            ])
        self.assertEqual(code, 0)
        self.assertFalse(any(method == "POST" for method, _ in calls), calls)


if __name__ == "__main__":
    unittest.main()
