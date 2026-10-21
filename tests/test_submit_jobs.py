"""Offline security regressions for submit job ownership and transport."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.request import Request
from urllib.parse import urlparse

from scripts.storyboard import submit_h3_segments as submit


class SubmitJobSafetyTests(unittest.TestCase):
    def test_relative_download_uses_api_url_base_and_only_same_origin_bearer(self):
        observed = []

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                return b"video"

        class Opener:
            def open(self, request, timeout=None):
                observed.append(request)
                return Response()

        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            destination = Path(td) / "clip.mp4"
            with mock.patch.object(submit.urllib.request, "build_opener", return_value=Opener()):
                submit.download_file(
                    "secret-token", "https://media.example/freevideo/agent/v1",
                    "files/out.mp4", destination,
                )
            req = observed[-1]
            self.assertEqual(req.full_url, "https://media.example/freevideo/agent/v1/files/out.mp4")
            self.assertEqual(req.get_header("Authorization"), "Bearer secret-token")
            self.assertEqual(destination.read_bytes(), b"video")

    def test_cross_origin_download_never_receives_bearer_token(self):
        observed = []

        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b"video"

        class Opener:
            def open(self, request, timeout=None):
                observed.append(request)
                return Response()

        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td, mock.patch.object(
            submit.urllib.request, "build_opener", return_value=Opener()
        ):
            submit.download_file("secret-token", "https://media.example/freevideo/agent/v1",
                                 "https://cdn.example/out.mp4", Path(td) / "clip.mp4")
        self.assertIsNone(observed[0].get_header("Authorization"))

    def test_redirect_handler_keeps_auth_for_same_origin_redirect(self):
        handler = submit.SameOriginRedirectHandler()
        request = Request("https://media.example/v1/start", headers={"Authorization": "Bearer secret"})
        redirected = handler.redirect_request(
            request, None, 302, "Found", {}, "https://media.example/v1/files/result.mp4"
        )
        self.assertIsNotNone(redirected)
        self.assertEqual(redirected.get_header("Authorization"), "Bearer secret")

    def test_redirect_handler_drops_or_rejects_cross_origin_auth(self):
        handler = submit.SameOriginRedirectHandler()
        request = Request("https://media.example/v1/start", headers={"Authorization": "Bearer secret"})
        redirected = handler.redirect_request(
            request, None, 302, "Found", {}, "https://cdn.example/files/result.mp4"
        )
        self.assertTrue(
            redirected is None or redirected.get_header("Authorization") is None,
            "cross-origin redirects must be rejected or have Authorization stripped",
        )

    def test_api_requests_also_install_scoped_redirect_handler(self):
        installed = []

        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b"{}"

        class Opener:
            def open(self, request, timeout=None): return Response()

        def build_opener(*handlers):
            installed.extend(handlers)
            return Opener()

        with mock.patch.object(submit.urllib.request, "build_opener", side_effect=build_opener):
            submit.call_api("https://media.example/freevideo/agent/v1", "secret", "GET", "/jobs")
        self.assertTrue(any(isinstance(handler, submit.SameOriginRedirectHandler) for handler in installed))

    def test_cancel_only_ids_recorded_in_local_ledger(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            ledger = Path(td) / "jobs.json"
            ledger.write_text(json.dumps({
                "project": str(Path(td).resolve()),
                "api_scope": "http://127.0.0.1:8189/freevideo/agent/v1",
                "jobs": [{"id": "owned-job", "batch_id": "batch-1"}],
            }), encoding="utf-8")
            calls = []

            def fake_api(api_url, token, method, path, body=None, timeout=600):
                calls.append((method, path))
                if method == "GET":
                    return {"jobs": [
                        {"id": "owned-job", "status": "running", "spec": {"ref": "seg-one"}},
                        {"id": "foreign-job", "status": "running", "spec": {"ref": "seg-foreign"}},
                    ]}
                return {}

            with mock.patch.object(submit, "call_api", side_effect=fake_api):
                submit.cancel_stale_jobs(
                    "http://127.0.0.1:8189/freevideo/agent/v1", "token", ledger_path=ledger
                )
            self.assertIn(("POST", "/jobs/owned-job/cancel"), calls)
            self.assertNotIn(("POST", "/jobs/foreign-job/cancel"), calls)

    def test_empty_or_missing_ledger_never_cancels_server_jobs(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            calls = []

            def fake_api(api_url, token, method, path, body=None, timeout=600):
                calls.append((method, path))
                return {"jobs": [{"id": "foreign", "status": "running", "spec": {"ref": "seg-x"}}]}

            with mock.patch.object(submit, "call_api", side_effect=fake_api):
                submit.cancel_stale_jobs(
                    "http://127.0.0.1:8189/freevideo/agent/v1", "token",
                    ledger_path=Path(td) / "missing-ledger.json",
                )
            self.assertFalse(any(method == "POST" for method, _ in calls))

    def test_reference_cache_is_scoped_to_api_url(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            image = root / "ref.png"
            image.write_bytes(b"local-reference-image")
            cache_path = root / "cache.json"
            api_calls = []

            def fake_call_api(api_url, token, method, path, body=None, timeout=600):
                api_calls.append(api_url)
                return {"file": f"remote-{len(api_calls)}"}

            with mock.patch.object(submit, "call_api", side_effect=fake_call_api):
                cache = {}
                first = submit.upload_reference_image(
                    "https://api-a.example/freevideo/agent/v1", "token", image, cache, cache_path
                )
                # A cache populated by API A must not make API B reuse API A's file ID.
                second = submit.upload_reference_image(
                    "https://api-b.example/freevideo/agent/v1", "token", image, cache, cache_path
                )
            self.assertEqual(first, "remote-1")
            self.assertEqual(second, "remote-2")
            self.assertEqual(api_calls, [
                "https://api-a.example/freevideo/agent/v1",
                "https://api-b.example/freevideo/agent/v1",
            ])

    def test_poll_timeout_returns_failure_and_keeps_job_in_scoped_ledger(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            segments = root / "segments-ep01.json"
            segments.write_text(json.dumps([{
                "segment_id": sid, "prompt": "offline prompt", "reference_images": [],
                "metadata": {"frames": 124, "target_duration_sec": 124 / 24.0},
            } for sid in ("EP01-seg01", "EP01-seg02")]), encoding="utf-8")
            out_dir = root / "videos"
            calls = []

            def fake_api(api_url, token, method, path, body=None, timeout=600):
                calls.append((method, path))
                if method == "POST":
                    return {"job": {"id": "owned-timeout", "status": "waiting"}}
                return {"job": {"id": "owned-timeout", "status": "waiting"}}

            with mock.patch.object(submit, "find_token", return_value="local-test-token"), \
                 mock.patch.object(submit, "verify_stage5_gate", return_value=True), \
                 mock.patch.object(submit, "get_gpu_vram", return_value=None), \
                 mock.patch.object(submit, "audit_segment_prompts", return_value=(True, [])), \
                 mock.patch.object(submit, "call_api", side_effect=fake_api), \
                 mock.patch.object(submit.time, "sleep"), \
                 mock.patch.object(submit.time, "monotonic", side_effect=[0.0, 2.0]):
                result = submit.main([
                    "--segments", str(segments), "--output-dir", str(out_dir), "--root-dir", str(root),
                    "--api-url", "https://api.example/freevideo/agent/v1", "--poll-timeout", "1",
                ])
            ledger = json.loads((out_dir / "_fv-job-ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(result, 1)
            self.assertEqual(ledger["project"], str(root.resolve()))
            self.assertEqual(ledger["api_scope"], "https://api.example/freevideo/agent/v1")
            self.assertEqual(ledger["jobs"][0]["id"], "owned-timeout")
            self.assertEqual(ledger["jobs"][0]["segment_id"], "EP01-seg01")
            self.assertEqual(ledger["jobs"][0]["status"], "timeout")
            self.assertFalse(any(path.endswith("/cancel") for _, path in calls))
            self.assertEqual(sum(method == "POST" and path == "/jobs" for method, path in calls), 1)

    def test_poll_interruption_stops_batch_and_preserves_job(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            segments = root / "segments-ep01.json"
            segments.write_text(json.dumps([{
                "segment_id": sid, "prompt": "offline prompt", "reference_images": [],
                "metadata": {"frames": 124, "target_duration_sec": 124 / 24.0},
            } for sid in ("EP01-seg01", "EP01-seg02")]), encoding="utf-8")
            out_dir = root / "videos"
            calls = []

            def fake_api(api_url, token, method, path, body=None, timeout=600):
                calls.append((method, path))
                if method == "POST":
                    return {"job": {"id": "owned-interrupted", "status": "waiting"}}
                return {"job": {"id": "owned-interrupted", "status": "waiting"}}

            with mock.patch.object(submit, "find_token", return_value="test-token"), \
                 mock.patch.object(submit, "verify_stage5_gate", return_value=True), \
                 mock.patch.object(submit, "get_gpu_vram", return_value=None), \
                 mock.patch.object(submit, "audit_segment_prompts", return_value=(True, [])), \
                 mock.patch.object(submit, "call_api", side_effect=fake_api), \
                 mock.patch.object(submit.time, "sleep", side_effect=KeyboardInterrupt), \
                 mock.patch.object(submit.time, "monotonic", return_value=0.0):
                result = submit.main([
                    "--segments", str(segments), "--output-dir", str(out_dir), "--root-dir", str(root),
                    "--api-url", "https://api.example/freevideo/agent/v1", "--poll-timeout", "30",
                ])
            ledger = json.loads((out_dir / "_fv-job-ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(result, 1)
            self.assertEqual(ledger["jobs"][0]["id"], "owned-interrupted")
            self.assertEqual(ledger["jobs"][0]["status"], "interrupted")
            self.assertEqual(sum(method == "POST" and path == "/jobs" for method, path in calls), 1)
            self.assertFalse(any(path.endswith("/cancel") for _, path in calls))

    def test_cancel_does_not_use_ledger_from_different_api_scope(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            ledger_path = Path(td) / "jobs.json"
            ledger_path.write_text(json.dumps({
                "project": str(Path(td).resolve()),
                "api_scope": "https://api-a.example/v1",
                "jobs": [{"id": "owned"}],
            }), encoding="utf-8")
            with mock.patch.object(submit, "call_api") as call_api:
                submit.cancel_stale_jobs("https://api-b.example/v1", "token", ledger_path,
                                         Path(td))
            call_api.assert_not_called()

    def test_empty_prompt_fails_audit(self):
        passed, errors = submit.audit_segment_prompts([{"segment_id": "EP01-seg01", "seconds": 4}])
        self.assertFalse(passed)
        self.assertTrue(any("prompt" in error.lower() for error in errors))

    def test_missing_prompt_audit_dependency_fails_closed(self):
        with mock.patch.object(submit, "audit_refs_and_subjects", None), \
             mock.patch.object(submit, "lint_h3_prompt", None):
            passed, errors = submit.audit_segment_prompts([
                {"segment_id": "EP01-seg01", "prompt": "A valid nonempty prompt", "seconds": 4}
            ])
        self.assertFalse(passed)
        self.assertTrue(errors)


class SegmentFrameResolutionTests(unittest.TestCase):
    """送件時長必須由影格數反推，不可沿用量化後四捨五入的秒數。"""

    def test_prefers_metadata_frames(self):
        frames, source = submit.resolve_segment_frames(
            {"segment_id": "S1", "metadata": {"frames": 277, "effective_duration_sec": 11.542}}
        )
        self.assertEqual(frames, 277)
        self.assertEqual(source, "metadata.frames")

    def test_rejects_non_quantum_frames(self):
        with self.assertRaises(ValueError):
            submit.resolve_segment_frames({"segment_id": "S1", "metadata": {"frames": 280}})

    def test_falls_back_to_effective_duration_without_drift(self):
        # 舊 segments 沒有 frames；effective 11.542 必須回推成 277，而不是 294。
        frames, source = submit.resolve_segment_frames(
            {"segment_id": "S1", "metadata": {"effective_duration_sec": 11.542}}
        )
        self.assertEqual(frames, 277)
        self.assertEqual(source, "metadata.effective_duration_sec")

    def test_effective_fallback_never_loses_a_quantum(self):
        # review 抓到的反向漂移：6.583 是 158 幀的四捨五入值，
        # 用 floor 會變 141（少 17 幀），必須用最近量子吸附。
        cases = {6.583: 158, 8.708: 209, 10.833: 260, 12.958: 311,
                 15.083: 362, 11.542: 277, 5.167: 124}
        for effective, expected in cases.items():
            frames, _ = submit.resolve_segment_frames(
                {"segment_id": "S1", "metadata": {"effective_duration_sec": effective}}
            )
            self.assertEqual(frames, expected, f"{effective}s 應為 {expected} 幀")

    def test_exact_effective_field_wins_over_rounded(self):
        frames, _ = submit.resolve_segment_frames(
            {"segment_id": "S1",
             "metadata": {"effective_duration_sec": 6.583,
                          "effective_duration_sec_exact": 158 / 24.0}}
        )
        self.assertEqual(frames, 158)

    def test_dialogue_segments_use_ceil(self):
        frames, _ = submit.resolve_segment_frames(
            {"segment_id": "S1",
             "metadata": {"target_duration_sec": 7.0, "rounding_mode": "floor",
                          "rounding_reason": "dialogue-preserving"}}
        )
        self.assertEqual(frames, 175)

    def test_plain_segments_use_floor(self):
        frames, _ = submit.resolve_segment_frames(
            {"segment_id": "S1", "metadata": {"target_duration_sec": 7.0, "rounding_mode": "floor"}}
        )
        self.assertEqual(frames, 158)

    def test_wire_seconds_is_exact_quantum(self):
        frames, _ = submit.resolve_segment_frames({"metadata": {"frames": 362}})
        self.assertEqual(submit.h3_spec.wire_seconds(frames), 362 / 24.0)
        self.assertEqual(submit.h3_spec.wire_seconds(frames) * 24.0, 362.0)

    def test_missing_duration_is_an_error(self):
        with self.assertRaises(ValueError):
            submit.resolve_segment_frames({"segment_id": "S1", "metadata": {}})

    def test_declared_frames_reads_known_paths(self):
        self.assertEqual(submit.declared_frames({"spec": {"frames": 277}}), 277)
        self.assertEqual(submit.declared_frames({"plan": {"geometry": {"frames": 294}}}), 294)
        self.assertEqual(submit.declared_frames({"spec": {"geometry": {"frames": 158}}}), 158)
        self.assertIsNone(submit.declared_frames({"job": {"id": "x"}}))
        self.assertIsNone(submit.declared_frames({"spec": {"frames": 0}}))

    def test_declared_frames_parses_numeric_string(self):
        self.assertEqual(submit.declared_frames({"spec": {"frames": "294"}}), 294)
        self.assertEqual(submit.declared_frames({"spec": {"frames": 277.0}}), 277)

    def test_declared_frames_rejects_ambiguous_values(self):
        # 讀不到 ≠ 通過：小數、布林、負數、垃圾字串一律 None
        for value in (277.5, True, -294, "abc", "", None, {}):
            self.assertIsNone(submit.declared_frames({"spec": {"frames": value}}), repr(value))


class DurationDriftBranchTests(unittest.TestCase):
    """drift 分支：取消、記帳、不下載、rc=1；以及取消失敗仍要記帳。"""

    def _run_batch(self, job_response, cancel_side_effect=None, frames=277):
        root = Path(tempfile.mkdtemp(dir=Path(__file__).resolve().parents[1]))
        self.addCleanup(lambda: __import__("shutil").rmtree(root, ignore_errors=True))
        segments = root / "segments.json"
        segments.write_text(json.dumps([{
            "segment_id": "EP01-S01", "prompt": "offline prompt", "reference_images": [],
            "metadata": {"frames": frames, "target_duration_sec": frames / 24.0},
        }]), encoding="utf-8")
        out_dir = root / "videos"
        calls = []

        def fake_api(api_url, token, method, path, body=None, timeout=600):
            calls.append((method, path))
            if method == "POST" and path == "/jobs":
                return job_response
            if method == "POST" and path.endswith("/cancel"):
                if cancel_side_effect:
                    raise cancel_side_effect
                return {}
            return {"job": {"id": "drift-1", "status": "waiting"}}

        with mock.patch.object(submit, "find_token", return_value="test-token"), \
             mock.patch.object(submit, "verify_stage5_gate", return_value=True), \
             mock.patch.object(submit, "get_gpu_vram", return_value=None), \
             mock.patch.object(submit, "audit_segment_prompts", return_value=(True, [])), \
             mock.patch.object(submit, "call_api", side_effect=fake_api):
            result = submit.main([
                "--segments", str(segments), "--output-dir", str(out_dir), "--root-dir", str(root),
                "--api-url", "https://api.example/freevideo/agent/v1",
            ])
        ledger = json.loads((out_dir / "_fv-job-ledger.json").read_text(encoding="utf-8"))
        return result, calls, ledger, out_dir

    def test_drift_on_create_cancels_and_never_downloads(self):
        result, calls, ledger, out_dir = self._run_batch(
            {"job": {"id": "drift-1", "status": "waiting", "spec": {"frames": 294}}}
        )
        self.assertEqual(result, 1)
        self.assertTrue(any(path.endswith("/cancel") for _, path in calls), calls)
        self.assertEqual(ledger["jobs"][0]["status"], "duration_drift")
        self.assertFalse((out_dir / "EP01-S01.mp4").exists())

    def test_drift_still_recorded_when_cancel_fails(self):
        result, calls, ledger, out_dir = self._run_batch(
            {"job": {"id": "drift-1", "status": "waiting", "spec": {"frames": 294}}},
            cancel_side_effect=RuntimeError("503"),
        )
        self.assertEqual(result, 1)
        self.assertEqual(ledger["jobs"][0]["status"], "duration_drift")
        self.assertFalse((out_dir / "EP01-S01.mp4").exists())

    def test_out_of_range_segment_is_not_submitted(self):
        with self.assertRaises(SystemExit):
            self._run_batch(
                {"job": {"id": "drift-1", "status": "waiting", "spec": {"frames": 379}}},
                frames=379,
            )


class TerminalDurationAssertionTests(unittest.TestCase):
    """終態斷言：建立任務當下沒有 geometry 是常態，不能因此放行。"""

    def _run(self, terminal_job, probe_seconds=None, frames=277):
        root = Path(tempfile.mkdtemp(dir=Path(__file__).resolve().parents[1]))
        self.addCleanup(lambda: __import__("shutil").rmtree(root, ignore_errors=True))
        segments = root / "segments.json"
        segments.write_text(json.dumps([{
            "segment_id": "EP01-S01", "prompt": "offline prompt", "reference_images": [],
            "metadata": {"frames": frames, "target_duration_sec": frames / 24.0},
        }]), encoding="utf-8")
        out_dir = root / "videos"
        calls, downloads = [], []
        poll_state = {"first": True}

        def fake_api(api_url, token, method, path, body=None, timeout=600):
            calls.append((method, path))
            if method == "POST" and path == "/jobs":
                return {"job": {"id": "J1", "status": "waiting"}}  # 正常：沒有 geometry
            if method == "GET" and path.startswith("/jobs/J1"):
                if poll_state["first"]:
                    poll_state["first"] = False
                    return {"job": {"id": "J1", "status": "waiting"}}
                return terminal_job
            return {}

        def fake_download(token, api_url, url, out_path):
            downloads.append((url, out_path.name))
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(b"fake-mp4")

        with mock.patch.object(submit, "find_token", return_value="test-token"), \
             mock.patch.object(submit, "verify_stage5_gate", return_value=True), \
             mock.patch.object(submit, "get_gpu_vram", return_value=None), \
             mock.patch.object(submit, "audit_segment_prompts", return_value=(True, [])), \
             mock.patch.object(submit, "call_api", side_effect=fake_api), \
             mock.patch.object(submit, "download_file", side_effect=fake_download), \
             mock.patch.object(submit, "probe_video_duration", return_value=probe_seconds), \
             mock.patch.object(submit.time, "sleep", return_value=None), \
             mock.patch.object(submit.time, "monotonic", return_value=0.0):
            result = submit.main([
                "--segments", str(segments), "--output-dir", str(out_dir), "--root-dir", str(root),
                "--api-url", "https://api.example/freevideo/agent/v1",
            ])
        ledger = json.loads((out_dir / "_fv-job-ledger.json").read_text(encoding="utf-8"))
        return result, ledger, downloads, out_dir

    def test_terminal_drift_detected_after_create_blocks_download(self):
        result, ledger, downloads, out_dir = self._run(
            {"job": {"id": "J1", "status": "succeeded",
                     "plan": {"geometry": {"frames": 294}},
                     "result": {"video": {"url": "/library/x.mp4"}}}}
        )
        self.assertEqual(result, 1)
        self.assertEqual(downloads, [])
        self.assertEqual(ledger["jobs"][0]["status"], "duration_drift")

    def test_matching_frames_downloads_and_records_assertion(self):
        result, ledger, downloads, out_dir = self._run(
            {"job": {"id": "J1", "status": "succeeded",
                     "plan": {"geometry": {"frames": 277}},
                     "result": {"video": {"url": "/library/x.mp4"}}}},
            probe_seconds=277 / 24.0,
        )
        self.assertEqual(result, 0)
        self.assertEqual(len(downloads), 1)
        self.assertEqual(ledger["jobs"][0]["status"], "downloaded")
        self.assertTrue(ledger["jobs"][0].get("duration_asserted"))

    def test_file_level_drift_is_quarantined(self):
        result, ledger, downloads, out_dir = self._run(
            {"job": {"id": "J1", "status": "succeeded",
                     "plan": {"geometry": {"frames": 277}},
                     "result": {"video": {"url": "/library/x.mp4"}}}},
            probe_seconds=277 / 24.0 + 0.5,  # 檔案多出半秒
        )
        self.assertEqual(result, 1)
        self.assertEqual(ledger["jobs"][0]["status"], "duration_drift")
        self.assertTrue((out_dir / "EP01-S01.drift.mp4").exists())
        self.assertFalse((out_dir / "EP01-S01.mp4").exists())


if __name__ == "__main__":
    unittest.main()


